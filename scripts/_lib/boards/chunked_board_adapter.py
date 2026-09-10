#!/usr/bin/env python3
r"""
固定 50 任务分卷看板 Adapter (Chunked Board Adapter - CCP V2.0 工业级基石)
基于固定 50 任务物理分卷 YAML 文件 (docs/D04-研发过程/D01-任务/tasks_XXXX_YYYY.yaml) 的单一事实源看板实现。

设计要点：
1. 统一契约：list_records / get_record / update_record / create_record / append_remarks，
   与 OfflineBoardAdapter / WeeklyBoardAdapter 完全同构。
2. 架构模式：固定 50 任务物理分卷 (Git SSOT) + O(1) 算术物理寻址：
   chunk_idx = (seq - 1) // 50
   start_id = chunk_idx * 50 + 1, end_id = (chunk_idx + 1) * 50
   tasks_XXXX_YYYY.yaml
3. 历史全量可读与原位更新：
   不做冷封阻断，全量分卷历史数据始终保持公开可读；任务在原分卷内就地原子流转更新，仅在建新卡时按 50 序号容量顺延新卷。
4. 并发安全：
   - 全局发号锁 (.lock_seq_generator.lock)：毫秒级短锁，内建死亡 PID 与 60s 超时破锁自愈；
   - 分卷文件锁 (.lock_tasks_XXXX_YYYY.lock)：业务流转排他写锁，保证单卷写原子性；
   - 独立 YAML 原子写内核 (_atomic_yaml_write)：临时文件 + os.replace 原子替换。
5. 原生支持 CCP 防御性契约载荷：
   原生结构化持久化 contract (前置断言、接口契约、边界、白名单)、return_contract (四件套回执)、tier 等字段。
"""
import os
import re
import sys
import time
import yaml
import json
import tempfile
import subprocess
import getpass
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

if __package__ in (None, ""):
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _scripts_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
    if _scripts_root not in sys.path:
        sys.path.insert(0, _scripts_root)

import paths
from enums import TaskStatus, normalize_role
from _lib.core import file_lock


_TASK_ID_RE = re.compile(r"^T(\d+)$")
_NODE_ID_RE = re.compile(r"\b(T\d+)-N?(\d+)\b")
_CHUNK_FILENAME_RE = re.compile(r"^tasks_(\d{4})_(\d{4})\.(?:yaml|yml)$")

KANBAN_FIELD_MAP = {
    "task_id": "id",
    "wbs_id": "wbs",
    "task_name": "name",
    "status": "status",
    "assignee": "assignee",
    "handler": "handler",
    "creator": "creator",
    "creator_role": "creator_role",
    "operator": "operator",
    "operator_name": "operator",
    "owner": "owner",
    "priority": "priority",
    "estimated_hours": "est_hours",
    "actual_hours": "act_hours",
    "start_time": "start_date",
    "end_time": "end_date",
    "created_date": "start_date",
    "stage": "stage",
    "workpackage": "wp",
    "pretask": "pretask",
    "process_desc": "process",
    "remarks": "remarks",
    "attachment": "attachment",
    "target": "target",
    "acceptance_criteria": "acceptance_criteria",
    "requirement_id": "requirement_id",
    "artifacts": "artifacts",
    "handover_context": "handover_context",
    "contract": "contract",
    "return_contract": "return_contract",
    "tier": "tier",
}

KANBAN_NATIVE_FIELDS = {
    "id", "name", "stage", "wp", "wbs", "pretask", "assignee", "handler",
    "creator", "creator_role", "operator", "owner", "status", "priority", "est_hours", "act_hours",
    "start_date", "end_date", "remarks", "process", "attachment",
    "target", "acceptance_criteria", "requirement_id", "artifacts", "handover_context",
    "contract", "return_contract", "tier",
    "_source_file"
}


def sanitize_comment(comment: str, max_len: int = 500) -> str:
    """清洗说明内容，去除换行符，限制最大长度防止存储膨胀"""
    if not comment:
        return ""
    clean = " ".join(str(comment).replace("\r", " ").replace("\n", " ").split()).strip()
    if len(clean) > max_len:
        clean = clean[:max_len] + "... (详见产出报告)"
    return clean


def get_current_os_user() -> str:
    """自动获取当前操作者名称"""
    try:
        git_user = subprocess.check_output(
            ["git", "config", "user.name"],
            stderr=subprocess.DEVNULL, timeout=1
        ).decode("utf-8").strip()
        if git_user:
            return git_user
    except Exception:
        pass
    try:
        return getpass.getuser()
    except Exception:
        return "system"


class ChunkedBoardAdapter:
    """固定 50 任务物理分卷看板适配器 (CCP V2.0 单一事实源)"""

    CHUNK_SIZE = 50

    def __init__(self, tasks_dir: Optional[str] = None, field_map: Optional[Dict[str, str]] = None,
                 locks_dir: Optional[str] = None, chunk_size: int = 50):
        """
        初始化固定分卷看板存储适配器。

        参数:
            tasks_dir (str, optional): 分卷 YAML 存放目录，缺省为 docs/D04-研发过程/D01-任务。
            field_map (dict, optional): 字段映射配置。
            locks_dir (str, optional): 互斥锁文件存放目录，缺省为 user_data/locks。
            chunk_size (int): 单卷任务容量，固定为 50。
        """
        self.tasks_dir = os.path.abspath(tasks_dir or paths.tasks_dir())
        os.makedirs(self.tasks_dir, exist_ok=True)
        self.locks_dir = os.path.abspath(locks_dir or paths.locks_dir())
        os.makedirs(self.locks_dir, exist_ok=True)
        self.chunk_size = chunk_size or self.CHUNK_SIZE

        self.seq_lock_file = os.path.join(self.locks_dir, ".lock_seq_generator.lock")
        self.field_map = field_map or {}
        self._val_to_key = {v: k for k, v in self.field_map.items()}

    # ------------------------------------------------------------------
    # O(1) 算术物理寻址核心
    # ------------------------------------------------------------------
    def get_chunk_range(self, seq: int) -> Tuple[int, int]:
        """依据任务绝对序号计算分卷区间：(seq - 1) // 50"""
        if seq < 1:
            seq = 1
        chunk_idx = (seq - 1) // self.chunk_size
        start_id = chunk_idx * self.chunk_size + 1
        end_id = (chunk_idx + 1) * self.chunk_size
        return start_id, end_id

    def get_chunk_filename(self, seq: int) -> str:
        """获取任务序号对应的物理分卷文件名 tasks_XXXX_YYYY.yaml"""
        start_id, end_id = self.get_chunk_range(seq)
        return f"tasks_{start_id:04d}_{end_id:04d}.yaml"

    def get_chunk_filepath(self, seq: int) -> str:
        """获取任务序号对应的物理分卷绝对路径"""
        return os.path.join(self.tasks_dir, self.get_chunk_filename(seq))

    def _chunk_lock_file(self, start_id: int, end_id: int) -> str:
        """获取指定分卷文件的并发互斥锁路径"""
        return os.path.join(self.locks_dir, f".lock_tasks_{start_id:04d}_{end_id:04d}.lock")

    # ------------------------------------------------------------------
    # 独立 YAML 原子写内核
    # ------------------------------------------------------------------
    def _atomic_yaml_write(self, target_yaml: str, payload_data: dict) -> bool:
        """临时文件 + os.replace 原子覆写 YAML 文件，失败自动销毁临时文件"""
        target_dir = os.path.dirname(os.path.abspath(target_yaml))
        os.makedirs(target_dir, exist_ok=True)
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".chunked_tmp_", suffix=".yaml")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(payload_data, f, allow_unicode=True, sort_keys=False, indent=2)
            os.replace(tmp_path, target_yaml)
            return True
        except Exception as e:
            sys.stderr.write(f"[FATAL ChunkedBoardAdapter._atomic_yaml_write] 写入失败 {target_yaml}: {e}\n")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def _read_yaml_file(self, yaml_path: str) -> Dict[str, Any]:
        """读取分卷 YAML 文件，若不存在返回默认空结构"""
        if not os.path.exists(yaml_path):
            return {"metadata": {}, "tasks": []}
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                if not isinstance(data.get("tasks"), list):
                    data["tasks"] = []
                if not isinstance(data.get("metadata"), dict):
                    data["metadata"] = {}
                return data
        except Exception as e:
            sys.stderr.write(f"[WARN] 读取分卷 YAML 异常 {yaml_path}: {e}\n")
        return {"metadata": {}, "tasks": []}

    # ------------------------------------------------------------------
    # 全局发号锁与僵尸锁自愈
    # ------------------------------------------------------------------
    def _acquire_seq_lock_with_recovery(self, timeout: float = 3.0):
        """获取发号排他短锁，内建死亡 PID 与 60s 超时破锁自愈机制"""
        start_t = time.time()
        while True:
            try:
                handle = file_lock.acquire_lock(self.seq_lock_file, blocking=False, timeout=0.0)
                return handle
            except Exception:
                if os.path.exists(self.seq_lock_file):
                    try:
                        st = os.stat(self.seq_lock_file)
                        age = time.time() - st.st_mtime
                        with open(self.seq_lock_file, "r", encoding="utf-8") as lf:
                            content = lf.read()
                        m_pid = re.search(r"pid=(\d+)", content)
                        is_dead = False
                        if m_pid:
                            pid = int(m_pid.group(1))
                            try:
                                os.kill(pid, 0)
                            except ProcessLookupError:
                                is_dead = True
                            except PermissionError:
                                is_dead = False
                            except Exception:
                                is_dead = False
                        if (is_dead and age > 5.0) or (age > 60.0):
                            sys.stderr.write(f"[WARN] 检测到僵尸锁 {self.seq_lock_file} (age={age:.1f}s, dead={is_dead})，强制执行破锁自愈\n")
                            try:
                                os.remove(self.seq_lock_file)
                            except Exception:
                                pass
                    except Exception:
                        pass

            if (time.time() - start_t) >= timeout:
                return file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=1.0)
            time.sleep(0.05)

    def _next_task_id(self) -> str:
        """在全局发号短锁内计算全局最大序号 T{max+1:04d}，带状态持久化与防重发号"""
        handle = self._acquire_seq_lock_with_recovery(timeout=5.0)
        try:
            max_num = 0
            state_file = os.path.join(self.locks_dir, ".seq_state.json")
            if os.path.exists(state_file):
                try:
                    with open(state_file, "r", encoding="utf-8") as sf:
                        s_data = json.load(sf)
                        max_num = int(s_data.get("max_seq", 0))
                except Exception:
                    pass

            file_max = 0
            if os.path.exists(self.tasks_dir):
                for fname in os.listdir(self.tasks_dir):
                    if (fname.endswith(".yaml") or fname.endswith(".yml")) and not fname.startswith("."):
                        fpath = os.path.join(self.tasks_dir, fname)
                        data = self._read_yaml_file(fpath)
                        for t in data.get("tasks", []):
                            m = _TASK_ID_RE.match(str(t.get("id", "")))
                            if m:
                                file_max = max(file_max, int(m.group(1)))
            max_num = max(max_num, file_max)

            next_num = max_num + 1
            try:
                tmp_sf = state_file + f".tmp.{os.getpid()}"
                with open(tmp_sf, "w", encoding="utf-8") as sf:
                    json.dump({"max_seq": next_num, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, sf)
                os.replace(tmp_sf, state_file)
            except Exception:
                pass

            return f"T{next_num:04d}"
        finally:
            if handle:
                file_lock.release_lock(handle)

    # ------------------------------------------------------------------
    # 实体转换与 CRUD 接口
    # ------------------------------------------------------------------
    def _translate(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """将入参字典规范化为看板统一字段"""
        translated = {}
        for k, v in fields.items():
            if k in KANBAN_FIELD_MAP:
                target_key = KANBAN_FIELD_MAP[k]
                translated[target_key] = v
            elif k in KANBAN_NATIVE_FIELDS:
                translated[k] = v
            elif k in self._val_to_key:
                orig_field = self._val_to_key[k]
                target_key = KANBAN_FIELD_MAP.get(orig_field, k)
                translated[target_key] = v
            else:
                translated[k] = v

        virtual_roles = {
            "严经理", "钱架构", "李开发", "马前端", "周审查", "章测试", "李文通", "吕改特",
            "pm", "arch", "dev", "frontend", "reviewer", "qa", "docs", "devops"
        }
        if "operator" in translated:
            op_val = str(translated["operator"]).strip()
            if not op_val or op_val.lower() in virtual_roles or op_val in virtual_roles:
                translated["operator"] = get_current_os_user() or "用户"

        return translated

    def create_record(self, fields: Dict[str, Any], chunk: Optional[str] = None) -> Optional[str]:
        """新建任务卡，依据序号 O(1) 持久化至固定 50 任务分卷 YAML"""
        trans = self._translate(fields)
        req_id = str(trans.get("id", "")).strip()
        if req_id:
            new_id = req_id
        else:
            new_id = self._next_task_id()

        m_id = _TASK_ID_RE.match(new_id)
        if m_id:
            seq_num = int(m_id.group(1))
        else:
            # 非标编号容错
            seq_num = 1

        start_id, end_id = self.get_chunk_range(seq_num)
        yaml_file = os.path.join(self.tasks_dir, f"tasks_{start_id:04d}_{end_id:04d}.yaml")
        chunk_lock = self._chunk_lock_file(start_id, end_id)

        with file_lock.acquire_lock(chunk_lock, blocking=True, timeout=5.0):
            data = self._read_yaml_file(yaml_file)
            meta = data.get("metadata", {})
            chunk_tag = f"tasks_{start_id:04d}_{end_id:04d}"
            meta["chunk_id"] = chunk_tag
            meta["start_seq"] = start_id
            meta["end_seq"] = end_id

            tasks = data.get("tasks", [])
            if any(str(c.get("id")) == new_id for c in tasks):
                sys.stderr.write(f"[ERROR] 任务编号 [{new_id}] 在分卷 {chunk_tag} 中已存在\n")
                return None

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            creator_raw = trans.get("creator")
            creator_clean = str(creator_raw).strip() if creator_raw is not None and str(creator_raw).strip() not in ("None", "null", "undefined") else ""
            creator = creator_clean or get_current_os_user()

            creator_role_raw = trans.get("creator_role") or trans.get("role") or "PM"
            creator_role = normalize_role(str(creator_role_raw).strip())

            operator_raw = trans.get("operator") or trans.get("operator_name")
            operator_clean = str(operator_raw).strip() if operator_raw is not None and str(operator_raw).strip() not in ("None", "null", "undefined") else ""
            operator = operator_clean or creator

            assignee = normalize_role(str(trans.get("assignee") or trans.get("owner") or "李开发").strip())
            handler = normalize_role(str(trans.get("handler") or assignee).strip())
            owner = normalize_role(str(trans.get("owner") or assignee).strip())

            raw_crit = trans.get("acceptance_criteria") or []
            if isinstance(raw_crit, str):
                crit_list = [c.strip() for c in re.split(r"[;\n；]", raw_crit) if c.strip()]
            elif isinstance(raw_crit, list):
                crit_list = []
                for item in raw_crit:
                    if isinstance(item, str):
                        crit_list.extend([c.strip() for c in re.split(r"[;\n；]", item) if c.strip()])
                    elif item:
                        crit_list.append(str(item).strip())
            else:
                crit_list = []

            tier = trans.get("tier")
            if not tier:
                task_type = str(trans.get("type") or trans.get("task_type") or "A").upper()
                contract = trans.get("contract") or {}
                has_strong_contract = bool(contract.get("interface_contract") or contract.get("preconditions"))
                try:
                    est_h = float(trans.get("est_hours") or 0.0)
                except (ValueError, TypeError):
                    est_h = 0.0

                if has_strong_contract or est_h > 4.0:
                    tier = "Tier-1"
                elif task_type in ("C", "D", "E") or (est_h > 0 and est_h <= 1.5 and not contract):
                    tier = "Tier-3"
                else:
                    tier = "Tier-2"

            card = {
                "id": new_id,
                "seq": seq_num,
                "tier": tier,
                "name": str(trans.get("name") or "").strip(),
                "stage": trans.get("stage") or "开发阶段",
                "wp": trans.get("wp") or "WP-默认",
                "wbs": trans.get("wbs") or "",
                "pretask": trans.get("pretask") or "",
                "assignee": assignee,
                "handler": handler,
                "creator": creator,
                "creator_role": creator_role,
                "operator": operator,
                "owner": owner,
                "status": trans.get("status") or "待开始",
                "priority": trans.get("priority") or "中",
                "est_hours": float(trans.get("est_hours", 0.0) or 0.0),
                "act_hours": float(trans.get("act_hours", 0.0) or 0.0),
                "start_date": trans.get("start_date") or now_str,
                "end_date": trans.get("end_date") or "",
                "remarks": trans.get("remarks") or "",
                "target": trans.get("target") or "",
                "acceptance_criteria": crit_list,
                "requirement_id": trans.get("requirement_id") or "",
                "artifacts": trans.get("artifacts") or {},
                "handover_context": trans.get("handover_context") or {},
                "process": trans.get("process") or f"[{new_id}-N01] [{now_str}] 建单并进入【{trans.get('status') or '待开始'}】 | 创建人: {creator} (创建角色: {creator_role}) | 负责角色: {assignee}"
            }

            if trans.get("contract"):
                card["contract"] = trans.get("contract")
            if trans.get("return_contract"):
                card["return_contract"] = trans.get("return_contract")

            tasks.append(card)
            data["tasks"] = tasks
            meta["updated_at"] = now_str
            meta["total_task_count"] = len(tasks)
            meta["active_task_count"] = len([t for t in tasks if t.get("status") not in ("已验收", "已取消")])
            data["metadata"] = meta

            if not self._atomic_yaml_write(yaml_file, data):
                return None

            return new_id

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """依据任务 ID 精准查询单条任务记录。首选 O(1) 算术物理命中分卷，未命中回退目录扫描。"""
        m_id = _TASK_ID_RE.match(str(record_id).strip())
        if m_id:
            seq_num = int(m_id.group(1))
            target_file = self.get_chunk_filepath(seq_num)
            if os.path.exists(target_file):
                data = self._read_yaml_file(target_file)
                for c in data.get("tasks", []):
                    if str(c.get("id")) == str(record_id):
                        card_copy = dict(c)
                        card_copy["_source_file"] = target_file
                        card_copy.setdefault("creator_role", "严经理")
                        card_copy.setdefault("operator", card_copy.get("creator") or "用户")
                        return {"record_id": c.get("id"), "fields": card_copy}

        # 回退扫描其他现有分卷
        if os.path.exists(self.tasks_dir):
            for fname in sorted(os.listdir(self.tasks_dir)):
                if (fname.endswith(".yaml") or fname.endswith(".yml")) and not fname.startswith("."):
                    fpath = os.path.join(self.tasks_dir, fname)
                    data = self._read_yaml_file(fpath)
                    for c in data.get("tasks", []):
                        if str(c.get("id")) == str(record_id):
                            card_copy = dict(c)
                            card_copy["_source_file"] = fpath
                            card_copy.setdefault("creator_role", "严经理")
                            card_copy.setdefault("operator", card_copy.get("creator") or "用户")
                            return {"record_id": c.get("id"), "fields": card_copy}
        return None

    def update_record(self, record_id: str, fields: Dict[str, Any], force_reopen: bool = False) -> bool:
        """在分卷互斥锁保护下，执行单条任务记录的原位就地更新"""
        rec = self.get_record(record_id)
        if not rec:
            sys.stderr.write(f"[ERROR] 找不到待更新的任务卡: {record_id}\n")
            return False

        yaml_file = rec["fields"].get("_source_file")
        if not yaml_file or not os.path.exists(yaml_file):
            sys.stderr.write(f"[ERROR] 任务卡归属源分卷文件缺失: {record_id}\n")
            return False

        fname = os.path.basename(yaml_file)
        m_chunk = _CHUNK_FILENAME_RE.match(fname)
        if m_chunk:
            start_id, end_id = int(m_chunk.group(1)), int(m_chunk.group(2))
            chunk_lock = self._chunk_lock_file(start_id, end_id)
        else:
            chunk_lock = os.path.join(self.locks_dir, f".lock_{fname}.lock")

        with file_lock.acquire_lock(chunk_lock, blocking=True, timeout=5.0):
            data = self._read_yaml_file(yaml_file)
            tasks = data.get("tasks", [])
            target_card = None
            for c in tasks:
                if str(c.get("id")) == str(record_id):
                    target_card = c
                    break

            if not target_card:
                return False

            trans = self._translate(fields)
            curr_st = target_card.get("status")
            new_st = trans.get("status")

            if curr_st in ("已验收", "已取消") and new_st and new_st != curr_st:
                if not force_reopen:
                    sys.stderr.write(f"[REJECT 终态防篡改] 任务 {record_id} 已处于【{curr_st}】，禁止修改！\n")
                    return False

            for k, v in trans.items():
                if k == "_source_file":
                    continue
                target_card[k] = v

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            active_cnt = len([t for t in tasks if t.get("status") not in ("已验收", "已取消")])
            meta = data.get("metadata", {})
            meta["updated_at"] = now_str
            meta["active_task_count"] = active_cnt
            meta["total_task_count"] = len(tasks)
            data["metadata"] = meta

            return self._atomic_yaml_write(yaml_file, data)

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None,
                     limit: int = 100, offset: int = 0, include_sealed: bool = True) -> List[Dict[str, Any]]:
        """跨分卷联合检索任务列表，支持条件过滤"""
        all_cards: List[Dict[str, Any]] = []

        if not os.path.exists(self.tasks_dir):
            return []

        chunk_files = sorted(
            [f for f in os.listdir(self.tasks_dir) if _CHUNK_FILENAME_RE.match(f)],
            reverse=True
        )

        seen_ids = set()
        for fname in chunk_files:
            fpath = os.path.join(self.tasks_dir, fname)
            data = self._read_yaml_file(fpath)
            for c in data.get("tasks", []):
                tid = str(c.get("id", ""))
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                card_item = dict(c)
                card_item["_source_file"] = fpath
                card_item.setdefault("creator_role", "严经理")
                card_item.setdefault("operator", card_item.get("creator") or "用户")
                all_cards.append(card_item)

        items = [{"record_id": c.get("id"), "fields": c} for c in all_cards]

        if filter_json:
            for cond in filter_json.get("conditions", []):
                field_name = str(cond.get("field_name", ""))
                operator = cond.get("operator", "is")
                values = [str(v) for v in (cond.get("value") or [])]
                kanban_field = KANBAN_FIELD_MAP.get(field_name, field_name)
                filtered = []
                for item in items:
                    cell = item["fields"].get(kanban_field)
                    cell_str = "" if cell is None else str(cell)
                    if operator in ("is", "isNot") and values:
                        hit = cell_str in values
                        if (operator == "is" and hit) or (operator == "isNot" and not hit):
                            filtered.append(item)
                    elif operator in ("contains", "doesNotContain") and values:
                        hit = values[0] in cell_str
                        if (operator == "contains" and hit) or (operator == "doesNotContain" and not hit):
                            filtered.append(item)
                    elif operator in ("isEmpty", "isNotEmpty"):
                        hit = not cell_str
                        if (operator == "isEmpty" and hit) or (operator == "isNotEmpty" and not hit):
                            filtered.append(item)
                items = filtered

        return items[offset:offset + limit]

    def append_remarks(self, record_id: str, remarks_field_name_or_text: str, new_text: Optional[str] = None) -> bool:
        """追加备注信息"""
        rec = self.get_record(record_id)
        if not rec:
            return False
        if new_text is not None:
            field_name = remarks_field_name_or_text or "remarks"
            append_text = str(new_text).strip()
        else:
            field_name = "remarks"
            append_text = str(remarks_field_name_or_text).strip()

        old_remarks = str(rec["fields"].get(field_name) or "").strip()
        if old_remarks:
            merged = f"{old_remarks} | {append_text}"
        else:
            merged = append_text
        return self.update_record(record_id, {field_name: merged})

    @staticmethod
    def _next_node_seq(process_text: Optional[str], task_id: str) -> int:
        """在锁内计算指定任务的下一个流程节点序号 (max+1)"""
        max_n = 0
        if process_text:
            for m in _NODE_ID_RE.finditer(str(process_text)):
                tid, n_str = m.group(1), m.group(2)
                if tid == task_id:
                    try:
                        max_n = max(max_n, int(n_str))
                    except ValueError:
                        pass
        return max_n + 1

    def append_process_node(self, record_id: str, role: str,
                            from_status: str, to_status: str,
                            operator: str = "", comment: str = "") -> Optional[str]:
        """向任务的 process 字段原子追加结构化流转节点。"""
        rec = self.get_record(record_id)
        if not rec:
            return None

        yaml_file = rec["fields"].get("_source_file")
        if not yaml_file or not os.path.exists(yaml_file):
            return None

        fname = os.path.basename(yaml_file)
        m_chunk = _CHUNK_FILENAME_RE.match(fname)
        if m_chunk:
            start_id, end_id = int(m_chunk.group(1)), int(m_chunk.group(2))
            chunk_lock = self._chunk_lock_file(start_id, end_id)
        else:
            chunk_lock = os.path.join(self.locks_dir, f".lock_{fname}.lock")

        with file_lock.acquire_lock(chunk_lock, blocking=True, timeout=5.0):
            data = self._read_yaml_file(yaml_file)
            tasks = data.get("tasks", [])
            for c in tasks:
                if str(c.get("id")) == str(record_id):
                    node_seq = self._next_node_seq(c.get("process"), str(record_id))
                    node_id = f"{record_id}-N{node_seq:02d}"
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    clean_comment = str(comment or "").strip()
                    effective_role = role or "用户"
                    effective_operator = operator or "用户"
                    line = f"[{node_id}]  [{ts}]  状态由【{from_status}】更新至【{to_status}】，角色: {effective_role}，操作人: {effective_operator}"
                    if clean_comment:
                        line += f"\n操作说明: {clean_comment}"
                    existing = c.get("process") or ""
                    c["process"] = f"{existing}\n{line}".strip() if existing else line

                    if self._atomic_yaml_write(yaml_file, data):
                        return node_id
                    return None
            return None

    def delete_record(self, record_id: str) -> bool:
        """从分卷 YAML 中物理删除指定任务卡"""
        rec = self.get_record(record_id)
        if not rec:
            return False

        yaml_file = rec["fields"].get("_source_file")
        if not yaml_file or not os.path.exists(yaml_file):
            return False

        fname = os.path.basename(yaml_file)
        m_chunk = _CHUNK_FILENAME_RE.match(fname)
        if m_chunk:
            start_id, end_id = int(m_chunk.group(1)), int(m_chunk.group(2))
            chunk_lock = self._chunk_lock_file(start_id, end_id)
        else:
            chunk_lock = os.path.join(self.locks_dir, f".lock_{fname}.lock")

        with file_lock.acquire_lock(chunk_lock, blocking=True, timeout=5.0):
            data = self._read_yaml_file(yaml_file)
            tasks = data.get("tasks", [])
            initial_count = len(tasks)
            remaining_tasks = [t for t in tasks if str(t.get("id")) != str(record_id)]
            if len(remaining_tasks) == initial_count:
                return False

            data["tasks"] = remaining_tasks
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            active_cnt = len([t for t in remaining_tasks if t.get("status") not in ("已验收", "已取消")])
            meta = data.get("metadata", {})
            meta["updated_at"] = now_str
            meta["total_task_count"] = len(remaining_tasks)
            meta["active_task_count"] = active_cnt
            data["metadata"] = meta

            return self._atomic_yaml_write(yaml_file, data)
