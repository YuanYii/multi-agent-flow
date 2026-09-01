#!/usr/bin/env python3
r"""
周口径看板 Adapter (Weekly Board Adapter)
基于自然周 YAML 文件 (docs/D04-研发过程/D01-任务/YYYY-Www.yaml) 的看板实现。

设计要点：
1. 统一契约：list_records / get_record / update_record / create_record / append_remarks，
   与 OfflineBoardAdapter 完全同构。
2. 架构模式：单周单文件 (Git SSOT) + 本地派生倒排索引与周冷封 (CQRS 加速模型)。
3. 并发安全：
   - 全局发号锁 (.lock_seq_generator.lock)：毫秒级短锁，内建死亡 PID 与 60s 超时破锁自愈；
   - 周文件锁 (.lock_{week}.lock)：业务流转排他写锁，保证单周写原子性；
   - 独立 YAML 原子写内核 (_atomic_yaml_write)：临时文件 + os.replace 原子替换，解耦 board_io.py。
4. 生命周期铁律：
   - 建卡定归属，原位就地更新，任务终身在创建周 YAML 内流转，严禁跨文件物理迁移；
   - 包含 target 与 acceptance_criteria 原生结构化持久化字段。
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
    "handover_context": "handover_context"
}

KANBAN_NATIVE_FIELDS = {
    "id", "name", "stage", "wp", "wbs", "pretask", "assignee", "handler",
    "creator", "creator_role", "operator", "owner", "status", "priority", "est_hours", "act_hours",
    "start_date", "end_date", "remarks", "process", "attachment",
    "target", "acceptance_criteria", "requirement_id", "artifacts", "handover_context",
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


class WeeklyBoardAdapter:
    """周口径看板适配器"""

    def __init__(self, tasks_dir: Optional[str] = None, field_map: Optional[Dict[str, str]] = None,
                 index_file: Optional[str] = None, locks_dir: Optional[str] = None):
        self.tasks_dir = os.path.abspath(tasks_dir or paths.tasks_dir())
        os.makedirs(self.tasks_dir, exist_ok=True)
        self.locks_dir = os.path.abspath(locks_dir or paths.locks_dir())
        os.makedirs(self.locks_dir, exist_ok=True)
        
        self.seq_lock_file = os.path.join(self.locks_dir, ".lock_seq_generator.lock")
        self.index_file = os.path.abspath(index_file or os.path.join(paths.user_data_dir(), ".tasks_index.json"))

        self.field_map = field_map or {}
        self._val_to_key = {v: k for k, v in self.field_map.items()}

    # ------------------------------------------------------------------
    # WBS-05: 独立 YAML 原子写内核
    # ------------------------------------------------------------------
    def _atomic_yaml_write(self, target_yaml: str, payload_data: dict) -> bool:
        """临时文件 + os.replace 原子覆写 YAML 文件，失败自动销毁临时文件"""
        target_dir = os.path.dirname(os.path.abspath(target_yaml))
        os.makedirs(target_dir, exist_ok=True)
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".weekly_tmp_", suffix=".yaml")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(payload_data, f, allow_unicode=True, sort_keys=False, indent=2)
            os.replace(tmp_path, target_yaml)
            return True
        except Exception as e:
            sys.stderr.write(f"[FATAL WeeklyBoardAdapter._atomic_yaml_write] 写入失败 {target_yaml}: {e}\n")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def _read_yaml_file(self, yaml_path: str) -> Dict[str, Any]:
        """读取周 YAML 文件，若不存在返回默认空模型"""
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
            sys.stderr.write(f"[WARN] 读取 YAML 文件异常 {yaml_path}: {e}\n")
        return {"metadata": {}, "tasks": []}

    def _week_lock_file(self, week_cycle: str) -> str:
        return os.path.join(self.locks_dir, f".lock_{week_cycle}.lock")

    # ------------------------------------------------------------------
    # WBS-06: 全局发号锁与僵尸锁自愈
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
        """在全局发号短锁内分配全局最大序号 T{max+1:04d}，带外部文件变更轻量探活"""
        handle = self._acquire_seq_lock_with_recovery(timeout=5.0)
        try:
            index = self._load_index()
            max_num = index.get("max_seq", 0)
            weeks_index = index.get("weeks", {})
            
            # 1. 首次或索引重置：执行全量扫描
            if max_num <= 0:
                for fname in os.listdir(self.tasks_dir):
                    if (fname.endswith(".yaml") or fname.endswith(".yml")) and not fname.startswith("."):
                        fpath = os.path.join(self.tasks_dir, fname)
                        data = self._read_yaml_file(fpath)
                        for t in data.get("tasks", []):
                            m = _TASK_ID_RE.match(str(t.get("id", "")))
                            if m:
                                max_num = max(max_num, int(m.group(1)))
            else:
                # 2. 探活外部变更（如 Git Pull 带来了新增周文件或更新了已有文件）
                for fname in os.listdir(self.tasks_dir):
                    if (fname.endswith(".yaml") or fname.endswith(".yml")) and not fname.startswith("."):
                        w_cycle = fname.split(".")[0]
                        fpath = os.path.join(self.tasks_dir, fname)
                        try:
                            st = os.stat(fpath)
                            # 若为新周文件，或 mtime 发生变化
                            if w_cycle not in weeks_index or st.st_mtime > (weeks_index[w_cycle].get("mtime", 0.0) + 0.1):
                                data = self._read_yaml_file(fpath)
                                for t in data.get("tasks", []):
                                    m = _TASK_ID_RE.match(str(t.get("id", "")))
                                    if m:
                                        max_num = max(max_num, int(m.group(1)))
                                # 同步刷新周记录的 mtime 避免重复扫描
                                if w_cycle in weeks_index:
                                    weeks_index[w_cycle]["mtime"] = st.st_mtime
                        except Exception:
                            pass

            next_id = f"T{max_num + 1:04d}"
            index["max_seq"] = max_num + 1
            self._save_index(index)
            return next_id
        finally:
            if handle:
                file_lock.release_lock(handle)

    # ------------------------------------------------------------------
    # WBS-07: 本地派生索引与周冷封
    # ------------------------------------------------------------------
    def _load_index(self) -> Dict[str, Any]:
        if not os.path.exists(self.index_file):
            return self._rebuild_index()
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "tasks" in data and "weeks" in data:
                return data
        except Exception:
            pass
        return self._rebuild_index()

    def _save_index(self, index: Dict[str, Any]):
        try:
            target_dir = os.path.dirname(os.path.abspath(self.index_file))
            os.makedirs(target_dir, exist_ok=True)
            tmp = self.index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.index_file)
        except Exception as e:
            sys.stderr.write(f"[WARN] 保存任务索引失败: {e}\n")

    def _rebuild_index(self) -> Dict[str, Any]:
        """全量扫描周目录极速重建本地派生索引"""
        index = {
            "version": 1,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "weeks": {},
            "tasks": {},
            "max_seq": 0
        }
        max_seq = 0
        for fname in sorted(os.listdir(self.tasks_dir)):
            if (fname.endswith(".yaml") or fname.endswith(".yml")) and not fname.startswith("."):
                fpath = os.path.join(self.tasks_dir, fname)
                st = os.stat(fpath)
                data = self._read_yaml_file(fpath)
                meta = data.get("metadata", {})
                w_cycle = meta.get("week_cycle") or fname.split(".")[0]
                tasks_list = data.get("tasks", [])
                
                active_cnt = 0
                for t in tasks_list:
                    tid = str(t.get("id", ""))
                    tst = str(t.get("status", ""))
                    if tst not in ("已验收", "已取消"):
                        active_cnt += 1
                    index["tasks"][tid] = {"week": w_cycle, "file": fpath, "status": tst}
                    m = _TASK_ID_RE.match(tid)
                    if m:
                        max_seq = max(max_seq, int(m.group(1)))

                is_sealed = meta.get("is_sealed", False)
                if len(tasks_list) > 0 and active_cnt == 0:
                    is_sealed = True

                index["weeks"][w_cycle] = {
                    "file": fpath,
                    "is_sealed": is_sealed,
                    "mtime": st.st_mtime,
                    "active_count": active_cnt,
                    "task_count": len(tasks_list)
                }

        index["max_seq"] = max_seq
        self._save_index(index)
        return index

    def _get_current_week_cycle(self) -> Tuple[str, str, str]:
        now = datetime.now()
        year, week_num, _ = now.isocalendar()
        week_cycle = f"{year}-W{week_num:02d}"
        start_date = now.strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        return week_cycle, start_date, end_date

    # ------------------------------------------------------------------
    # WBS-08: 标准 CRUD 接口与原位就地更新
    # ------------------------------------------------------------------
    def _translate(self, fields: Dict[str, Any]) -> Dict[str, Any]:
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
        return translated

    def create_record(self, fields: Dict[str, Any], week: Optional[str] = None) -> Optional[str]:
        """新建周口径任务卡，持久化至当周 YAML"""
        trans = self._translate(fields)
        req_id = str(trans.get("id", "")).strip()
        if req_id:
            new_id = req_id
        else:
            new_id = self._next_task_id()

        curr_week, w_start, w_end = self._get_current_week_cycle()
        target_week = week or curr_week
        yaml_file = os.path.join(self.tasks_dir, f"{target_week}.yaml")
        week_lock = self._week_lock_file(target_week)

        with file_lock.acquire_lock(week_lock, blocking=True, timeout=5.0):
            data = self._read_yaml_file(yaml_file)
            meta = data.get("metadata", {})
            if not meta.get("week_cycle"):
                meta["week_cycle"] = target_week
                meta["start_date"] = w_start
                meta["end_date"] = w_end
                meta["is_sealed"] = False
            
            tasks = data.get("tasks", [])
            if any(str(c.get("id")) == new_id for c in tasks):
                sys.stderr.write(f"[ERROR] 任务编号 [{new_id}] 在 {target_week} 中已存在\n")
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

            card = {
                "id": new_id,
                "seq": int(_TASK_ID_RE.match(new_id).group(1)) if _TASK_ID_RE.match(new_id) else len(tasks) + 1,
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
                "process": trans.get("process") or f"[{new_id}-N01]  [{now_str}]  建单并进入【{trans.get('status') or '待开始'}】 | 创建人: {creator} (创建角色: {creator_role}) | 负责角色: {assignee}"
            }

            tasks.append(card)
            data["tasks"] = tasks
            meta["updated_at"] = now_str
            meta["total_task_count"] = len(tasks)
            meta["active_task_count"] = len([t for t in tasks if t.get("status") not in ("已验收", "已取消")])
            data["metadata"] = meta

            if not self._atomic_yaml_write(yaml_file, data):
                return None

            index = self._load_index()
            index["tasks"][new_id] = {"week": target_week, "file": yaml_file, "status": card["status"]}
            self._save_index(index)
            return new_id

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        target_file = None
        index = self._load_index()
        task_meta = index.get("tasks", {}).get(str(record_id))
        if task_meta and os.path.exists(task_meta.get("file", "")):
            target_file = task_meta["file"]

        files_to_check = [target_file] if target_file else [
            os.path.join(self.tasks_dir, f) for f in os.listdir(self.tasks_dir)
            if (f.endswith(".yaml") or f.endswith(".yml")) and not f.startswith(".")
        ]

        for fp in files_to_check:
            if not fp or not os.path.exists(fp):
                continue
            data = self._read_yaml_file(fp)
            for c in data.get("tasks", []):
                if str(c.get("id")) == str(record_id):
                    card_copy = dict(c)
                    card_copy["_source_file"] = fp
                    card_copy.setdefault("creator_role", "严经理")
                    card_copy.setdefault("operator", card_copy.get("creator") or "用户")
                    return {"record_id": c.get("id"), "fields": card_copy}
        return None

    def update_record(self, record_id: str, fields: Dict[str, Any], force_reopen: bool = False) -> bool:
        rec = self.get_record(record_id)
        if not rec:
            sys.stderr.write(f"[ERROR] 找不到待更新的任务卡: {record_id}\n")
            return False

        yaml_file = rec["fields"].get("_source_file")
        if not yaml_file or not os.path.exists(yaml_file):
            sys.stderr.write(f"[ERROR] 任务卡归属源文件缺失: {record_id}\n")
            return False

        week_cycle = os.path.basename(yaml_file).split(".")[0]
        week_lock = self._week_lock_file(week_cycle)

        with file_lock.acquire_lock(week_lock, blocking=True, timeout=5.0):
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
            if len(tasks) > 0 and active_cnt == 0:
                meta["is_sealed"] = True
            else:
                meta["is_sealed"] = False
            data["metadata"] = meta

            if not self._atomic_yaml_write(yaml_file, data):
                return False

            index = self._load_index()
            index["tasks"][str(record_id)] = {
                "week": week_cycle,
                "file": yaml_file,
                "status": target_card.get("status")
            }
            if week_cycle in index.get("weeks", {}):
                index["weeks"][week_cycle]["is_sealed"] = meta["is_sealed"]
                index["weeks"][week_cycle]["active_count"] = active_cnt
            self._save_index(index)
            return True

    def list_records(self, filter_json: Optional[Dict[str, Any]] = None,
                     limit: int = 100, offset: int = 0, include_sealed: bool = False) -> List[Dict[str, Any]]:
        index = self._load_index()
        all_cards: List[Dict[str, Any]] = []

        yaml_files = sorted(
            [f for f in os.listdir(self.tasks_dir) if (f.endswith(".yaml") or f.endswith(".yml")) and not f.startswith(".")],
            reverse=True
        )

        for idx, fname in enumerate(yaml_files):
            w_cycle = fname.split(".")[0]
            w_meta = index.get("weeks", {}).get(w_cycle, {})
            if not include_sealed and w_meta.get("is_sealed") and idx >= 2:
                continue

            fpath = os.path.join(self.tasks_dir, fname)
            data = self._read_yaml_file(fpath)
            for c in data.get("tasks", []):
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
        """追加备注字段信息（兼容基类 (record_id, field_name, new_text) 与双参数签名）"""
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
                if m.group(1) == str(task_id):
                    max_n = max(max_n, int(m.group(2)))
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

        week_cycle = os.path.basename(yaml_file).split(".")[0]
        week_lock = self._week_lock_file(week_cycle)

        with file_lock.acquire_lock(week_lock, blocking=True, timeout=5.0):
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
        """从周 YAML 中物理删除指定任务卡并同步索引"""
        rec = self.get_record(record_id)
        if not rec:
            return False

        yaml_file = rec["fields"].get("_source_file")
        if not yaml_file or not os.path.exists(yaml_file):
            return False

        week_cycle = os.path.basename(yaml_file).split(".")[0]
        week_lock = self._week_lock_file(week_cycle)

        with file_lock.acquire_lock(week_lock, blocking=True, timeout=5.0):
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
            if len(remaining_tasks) > 0 and active_cnt == 0:
                meta["is_sealed"] = True
            else:
                meta["is_sealed"] = False
            data["metadata"] = meta

            if not self._atomic_yaml_write(yaml_file, data):
                return False

            index = self._load_index()
            if str(record_id) in index.get("tasks", {}):
                del index["tasks"][str(record_id)]
            if week_cycle in index.get("weeks", {}):
                index["weeks"][week_cycle]["is_sealed"] = meta["is_sealed"]
                index["weeks"][week_cycle]["active_count"] = active_cnt
                index["weeks"][week_cycle]["task_count"] = len(remaining_tasks)
            self._save_index(index)
            return True
