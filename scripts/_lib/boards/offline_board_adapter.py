#!/usr/bin/env python3
r"""
离线看板 Adapter (Offline Board Adapter)
基于本地 JSON 文件 (board.json) 的看板实现，与 multiagent-kanban 离线看板数据格式互通。

设计要点：
1. 统一接口：list_records / get_record / update_record / create_record / append_remarks，
   与 FeishuBaseAdapter / JiraAdapter / GitHubProjectsAdapter 完全一致，可经 board_adapter_factory 无缝切换。
2. 字段翻译：workflow.config.yaml 中 board.fields 的配置值 → 离线看板 JSON 字段名（id/name/status/...）。
3. 并发安全：
   - 所有读-改-写操作持「全局排他锁」(board.json.seq.lock, 阻塞式 flock)，保证读改写原子性；
   - create_record 在锁内分配最大任务编号 (T\d+ → max+1)，多个专家并发新建任务时严格保障编号唯一不重复；
   - 文件写入采用 tmp + os.replace 原子替换，避免半写文件。
4. Fail-Closed：写入失败返回 False/None 拒绝落库；board.json 不存在时按空看板处理。
"""
import os
import re
import sys
import json
from datetime import datetime
import subprocess
import getpass
from typing import Dict, Any, List, Optional

# CLI 直接执行本文件时（__package__ 为空），先把 scripts 根目录注入搜索路径，
# 确保 enums / _lib.core 等平级模块可导入；作为库被 import 时此注入无害。
if __package__ in (None, ""):
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _scripts_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
    if _scripts_root not in sys.path:
        sys.path.insert(0, _scripts_root)

from enums import TaskStatus, normalize_role
from _lib.core import file_lock, board_io


def sanitize_comment(comment: str, max_len: int = 500) -> str:
    """清洗说明内容，去除换行符，限制最大长度防止存储膨胀"""
    if not comment:
        return ""
    clean = " ".join(str(comment).replace("\r", " ").replace("\n", " ").split()).strip()
    if len(clean) > max_len:
        clean = clean[:max_len] + "... (详见产出报告)"
    return clean


def get_current_os_user() -> str:
    """自动获取当前真人操作者名称（Git用户名优先，OS系统登录名兜底）"""
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
        return os.environ.get("USER") or os.environ.get("USERNAME") or "system"


# skill 逻辑字段 key → 离线看板 JSON 字段名 (None = 看板无对应字段，写入时跳过)
KANBAN_FIELD_MAP: Dict[str, Optional[str]] = {
    "task_id": "id",
    "task_name": "name",
    "wbs_id": "wbs",
    "status": "status",
    "assignee": "assignee",
    "owner": "assignee",
    "handler": "handler",
    "creator": "creator",
    "priority": None,
    "task_type": "type",
    "type": "type",
    "estimated_hours": "est_hours",
    "actual_hours": "act_hours",
    "start_time": "start_date",
    "end_time": "end_date",
    "created_date": None,
    "stage": "stage",
    "workpackage": "wp",
    "process_desc": "process",
    "remarks": "remarks",
    "pretask": "pretask",
    "pre_task": "pretask",
    "depends_on": "pretask",
    "attachment": None,
}

# 看板原生字段集合（直接透传的白名单）
KANBAN_NATIVE_FIELDS = {
    "id", "name", "wbs", "status", "assignee", "handler", "creator", "est_hours", "act_hours",
    "start_date", "end_date", "stage", "wp", "process", "remarks", "pretask", "seq", "type",
}

_TASK_ID_RE = re.compile(r"^T(\d+)$")
# 流程节点 ID（如 T0001-N03 / T0001-3）: 任务ID + 任务内单调递增节点序号
_NODE_ID_RE = re.compile(r"\b(T\d+)-N?(\d+)\b")


class OfflineBoardAdapter:
    def __init__(self, board_file: str, field_map: Optional[Dict[str, Any]] = None):
        """
        :param board_file: 离线看板 JSON 文件路径 (如 kanban/board.json)
        :param field_map: workflow.config.yaml 的 board.fields 配置 (key=skill 逻辑字段名, value=看板字段 ID/名)
        """
        self.board_file = os.path.abspath(board_file)
        os.makedirs(os.path.dirname(self.board_file), exist_ok=True)
        self.seq_lock_file = self.board_file + ".seq.lock"
        self.field_map = field_map or {}

        # 配置值(可能为 fldxxx 或逻辑名) → 看板字段名 翻译表
        self._value_to_kanban: Dict[str, Optional[str]] = {}
        for skill_key, config_value in self.field_map.items():
            self._value_to_kanban[str(config_value)] = KANBAN_FIELD_MAP.get(skill_key)

    # ------------------------------------------------------------------
    # 内部工具：读写
    # ------------------------------------------------------------------
    def _read_cards(self) -> List[Dict[str, Any]]:
        """读取看板全部卡片（JSON 数组，经 board_io 共享内核）。文件不存在返回空列表。"""
        return board_io.load_cards(self.board_file)

    def _write_cards(self, cards: List[Dict[str, Any]]) -> bool:
        """原子写：先写临时文件再 os.replace，避免半写文件。内置只追加完整性校验断言。"""
        # 只追加断言校验（Append-Only Integrity Assertion）：
        # 禁止以任何形式物理删除历史已存在的 Task ID
        old_cards = self._read_cards()
        if old_cards:
            old_ids = {str(c.get("id")) for c in old_cards if c.get("id")}
            new_ids = {str(c.get("id")) for c in cards if c.get("id")}
            missing = old_ids - new_ids
            if missing:
                sys.stderr.write(f"[FATAL 数据完整性校验失败] 检测到企图物理删除历史任务卡 {missing}！已硬拦截物理写入。\n")
                return False

        # 写入统一走 board_io 共享原子写内核（排他锁由调用方在锁内持有）
        return board_io.atomic_write(self.board_file, cards)

    def _translate(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """skill 字段 key/配置值 → 看板 JSON 字段名，白名单外字段丢弃。"""
        out: Dict[str, Any] = {}
        for k, v in fields.items():
            if v is None:
                continue
            # 1) 配置翻译表（优先）：config 里的 value 可能是 fldxxx 或逻辑名
            kanban_field = self._value_to_kanban.get(str(k))
            # 2) 直接是 skill 逻辑 key
            if kanban_field is None:
                kanban_field = KANBAN_FIELD_MAP.get(k)
            # 3) 直接是看板原生字段名
            if kanban_field is None and k in KANBAN_NATIVE_FIELDS:
                kanban_field = k
            if kanban_field:
                out[kanban_field] = v
        return out

    @staticmethod
    def _next_task_id(cards: List[Dict[str, Any]]) -> str:
        """在锁内计算下一个任务编号：取现有 T\\d+ 最大号 +1，无则从 T0001 开始。"""
        max_num = 0
        for c in cards:
            m = _TASK_ID_RE.match(str(c.get("id", "")))
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"T{max_num + 1:04d}"

    @staticmethod
    def _next_node_seq(process_text: Optional[str], task_id: str) -> int:
        """在锁内计算指定任务的下一个流程节点序号。

        扫描 process 文本行内的节点 ID（如 [T0001-N03]），取最大 N + 1；
        无任何节点行时返回 1。与任务编号 max+1 分配同构：
        单调递增、只追加、永不重排（回滚烧号不复用）。
        """
        max_n = 0
        if process_text:
            for m in _NODE_ID_RE.finditer(str(process_text)):
                if m.group(1) == str(task_id):
                    max_n = max(max_n, int(m.group(2)))
        return max_n + 1

    # ------------------------------------------------------------------
    # 统一接口
    # ------------------------------------------------------------------
    def list_records(self, filter_json: Optional[Dict[str, Any]] = None,
                     limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """检索看板记录（支持按 status/assignee 等字段的简单等值过滤）。"""
        with file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=5.0):
            cards = self._read_cards()
            items = [{"record_id": c.get("id"), "fields": c} for c in cards]

            if filter_json:
                for cond in filter_json.get("conditions", []):
                    field_name = str(cond.get("field_name", ""))
                    operator = cond.get("operator", "is")
                    values = [str(v) for v in (cond.get("value") or [])]
                    kanban_field = (self._value_to_kanban.get(field_name)
                                    or KANBAN_FIELD_MAP.get(field_name) or field_name)
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

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """获取指定任务编号的详情记录；不存在返回 None。"""
        with file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=5.0):
            for c in self._read_cards():
                if str(c.get("id")) == str(record_id):
                    return {"record_id": c.get("id"), "fields": c}
            return None

    def update_record(self, record_id: str, fields: Dict[str, Any], force_reopen: bool = False) -> bool:
        """更新指定任务的状态/处理人/描述等字段；记录不存在或企图篡改已验收终态核心状态时返回 False。"""
        with file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=5.0):
            cards = self._read_cards()
            for c in cards:
                if str(c.get("id")) == str(record_id):
                    # 防篡改硬拦截：在终态【已验收】或【已取消】时，禁止将其跨跃更新至非终态状态（除非显式携带 force_reopen）
                    translated = self._translate(fields)
                    curr_st = c.get("status")
                    if curr_st in ("已验收", "已取消"):
                        new_st = translated.get("status")
                        if new_st and new_st != curr_st:
                            if not force_reopen:
                                print(f"[REJECT 终态防篡改] 任务 {record_id} 已处于最终【{curr_st}】状态，绝对禁止将其修改为【{new_st}】！若需管理员纠偏请使用 --force-reopen。")
                                return False
                            print(f"[AUDIT 重开放行] 任务 {record_id} 由终态【{curr_st}】受控纠偏重开至【{new_st}】。")
                    c.update(translated)
                    # pretask 规范化与自依赖拦截
                    if "pretask" in translated:
                        raw_pre = translated["pretask"]
                        if raw_pre:
                            pre_ids = [p.strip() for p in re.split(r"[,;\s]+", str(raw_pre)) if p.strip()]
                            if record_id in pre_ids:
                                print(f"[REJECT 依赖校验失败] 任务 {record_id} 不能将自身作为前置依赖！")
                                return False
                            c["pretask"] = ",".join(pre_ids) if pre_ids else None
                        else:
                            c["pretask"] = None
                    # 若存在开始与结束时间，自动按 (结束-开始) 计算实际工时 (小时)
                    st = c.get("start_date") or c.get("start_time")
                    et = c.get("end_date") or c.get("end_time")
                    est_h = float(c.get("est_hours") or 0.0)
                    if st and et:
                        mins = self._calc_minutes(st, et)
                        if mins is not None:
                            if mins == 0 and est_h > 0:
                                from datetime import datetime, timedelta
                                try:
                                    e_dt = datetime.strptime(str(et).strip(), "%Y-%m-%d %H:%M:%S")
                                    s_dt = e_dt - timedelta(minutes=int(est_h * 60))
                                    c["start_date"] = s_dt.strftime("%Y-%m-%d %H:%M:%S")
                                    c["act_hours"] = float(est_h)
                                except Exception:
                                    c["act_hours"] = float(est_h)
                            else:
                                c["act_hours"] = round(max(1, mins) / 60.0, 2)
                    elif c.get("status") not in ("已完成", "已验收", "已取消"):
                        # 活跃态（进行中/待开始等）且未设定有效结束时间，实际工时与完工日期彻底清空
                        c["act_hours"] = None
                        c["end_date"] = None
                    return self._write_cards(cards)
            return False

    @staticmethod
    def _calc_minutes(start_str: str, end_str: str) -> Optional[int]:
        """计算开始与结束时间之间的分钟差值（支持 ISO 8601 时区串与多种时间格式）"""
        from datetime import datetime
        def parse_dt(s: Any) -> Optional[datetime]:
            if not s:
                return None
            s_clean = str(s).strip()
            # 优先使用 fromisoformat 解析 ISO 字符串 (例如 2026-08-11T23:00:00+08:00 或 Z)
            try:
                iso_str = s_clean.replace("Z", "+00:00")
                return datetime.fromisoformat(iso_str)
            except Exception:
                pass
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S%z",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(s_clean, fmt)
                except Exception:
                    pass
            return None

        s_dt = parse_dt(start_str)
        e_dt = parse_dt(end_str)
        if s_dt and e_dt:
            diff_sec = (e_dt - s_dt).total_seconds()
            if diff_sec <= 0:
                return 0
            return max(1, int(diff_sec // 60))
        return None

    def create_record(self, fields: Optional[Dict[str, Any]] = None, **kwargs) -> Optional[str]:
        r"""
        新建看板任务。
        - 自动补全默认规范字段：wbs 默认为 "-"，wp/stage 默认为 "-"，est_hours 默认为 "-"；
        - 未提供 task_id / id 时，在全局锁内自动分配 max(T\d+)+1；
        - 成功返回任务编号 (record_id)，失败返回 None。
        """
        merged_fields = {}
        if isinstance(fields, dict):
            merged_fields.update(fields)
        merged_fields.update(kwargs)
        if "task_name" in merged_fields and "name" not in merged_fields:
            merged_fields["name"] = merged_fields["task_name"]

        with file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=5.0):
            cards = self._read_cards()

            task_id = str(merged_fields.get("task_id") or merged_fields.get("id") or "").strip()
            if not task_id:
                task_id = self._next_task_id(cards)
            else:
                if any(str(c.get("id")) == task_id for c in cards):
                    return None  # 编号已存在 → Fail-Closed 拒绝

            translated = self._translate(merged_fields)
            translated["id"] = task_id
            translated.setdefault("status", "待开始")
            translated.setdefault("wbs", "-")
            translated.setdefault("wp", "-")
            translated.setdefault("stage", merged_fields.get("stage") or "-")
            translated.setdefault("type", merged_fields.get("type") or merged_fields.get("task_type") or "A")
            try:
                translated["est_hours"] = float(translated.get("est_hours", 0.0) or 0.0)
            except (ValueError, TypeError):
                translated["est_hours"] = 0.0
            try:
                translated["act_hours"] = float(translated.get("act_hours", 0.0) or 0.0)
            except (ValueError, TypeError):
                translated["act_hours"] = 0.0
            translated.setdefault("creator", merged_fields.get("creator") or get_current_os_user())
            translated.setdefault("process", "")

            # pretask 规范化与自依赖拦截
            raw_pretask = translated.get("pretask") or merged_fields.get("pretask") or merged_fields.get("pre_task") or merged_fields.get("depends_on")
            if raw_pretask:
                pre_ids = [p.strip() for p in re.split(r"[,;\s]+", str(raw_pretask)) if p.strip()]
                if task_id in pre_ids:
                    sys.stderr.write(f"[REJECT 依赖校验失败] 任务 {task_id} 不能将自身作为前置依赖！\n")
                    return None
                translated["pretask"] = ",".join(pre_ids) if pre_ids else None
            else:
                translated["pretask"] = None

            # 时间与实际工时计算
            st = translated.get("start_date") or translated.get("start_time")
            et = translated.get("end_date") or translated.get("end_time")
            est_h = float(translated.get("est_hours") or 0.0)
            if st and et:
                mins = self._calc_minutes(st, et)
                if mins is not None:
                    if mins == 0 and est_h > 0:
                        from datetime import datetime, timedelta
                        try:
                            e_dt = datetime.strptime(str(et).strip(), "%Y-%m-%d %H:%M:%S")
                            s_dt = e_dt - timedelta(minutes=int(est_h * 60))
                            translated["start_date"] = s_dt.strftime("%Y-%m-%d %H:%M:%S")
                            translated["act_hours"] = float(est_h)
                        except Exception:
                            translated["act_hours"] = float(est_h)
                    else:
                        translated["act_hours"] = round(max(1, mins) / 60.0, 2)

            max_seq = max([int(c.get("seq") or 0) for c in cards] or [0])
            translated["seq"] = max_seq + 1

            cards.append(translated)
            if not self._write_cards(cards):
                return None
            return task_id

    def append_remarks(self, record_id: str, remarks_field_name: str, new_text: str) -> bool:
        """原子级追加备注（打回缺陷信息等）；记录不存在返回 False。"""
        with file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=5.0):
            kanban_field = self._value_to_kanban.get(str(remarks_field_name)) or "remarks"
            cards = self._read_cards()
            for c in cards:
                if str(c.get("id")) == str(record_id):
                    existing = c.get(kanban_field) or ""
                    combined = f"{existing}\n\n{new_text}".strip() if existing else new_text
                    c[kanban_field] = combined
                    return self._write_cards(cards)
            return False

    def append_process_node(self, record_id: str, role: str,
                            from_status: str, to_status: str,
                            operator: str = "", comment: str = "") -> "str | None":
        """锁内分配节点号并向 process 字段追加结构化流转节点。

        节点格式（两行，说明可选）:
          [{节点ID}]  [{时间戳}]  状态由【{from}】更新至【{to}】，角色: {角色}，操作人: {操作人}
          操作说明: {说明}

        节点号在 board.json.seq.lock 排他锁内取该卡 max(N)+1 —— 并发安全、
        单调递增、只追加、回滚烧号不复用。
        返回完整节点 ID（如 "T0001-N03"）；记录不存在返回 None。
        """
        with file_lock.acquire_lock(self.seq_lock_file, blocking=True, timeout=5.0):
            cards = self._read_cards()
            for c in cards:
                if str(c.get("id")) == str(record_id):
                    node_seq = self._next_node_seq(c.get("process"), str(record_id))
                    node_id = f"{record_id}-N{node_seq:02d}"
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    clean_comment = sanitize_comment(comment)
                    effective_role = normalize_role(role) or "用户"
                    effective_operator = operator or get_current_os_user() or "用户"
                    line = f"[{node_id}]  [{ts}]  状态由【{from_status}】更新至【{to_status}】，角色: {effective_role}，操作人: {effective_operator}"
                    if clean_comment:
                        line += f"\n操作说明: {clean_comment}"
                    existing = c.get("process") or ""
                    c["process"] = f"{existing}\n{line}".strip() if existing else line
                    if self._write_cards(cards):
                        return node_id
                    return None
            return None


def init_board_file(board_file: str) -> str:
    """初始化空看板文件（不覆盖已有数据），返回 board_file 路径。"""
    board_file = os.path.abspath(board_file)
    if not os.path.exists(board_file):
        os.makedirs(os.path.dirname(board_file) or ".", exist_ok=True)
        with open(board_file, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    return board_file


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="离线看板适配器独立工具")
    parser.add_argument("--init", metavar="BOARD_FILE", help="初始化空看板文件 (不覆盖已有数据)")
    parser.add_argument("--list", metavar="BOARD_FILE", help="列出看板全部任务")
    args = parser.parse_args()

    if args.init:
        print(f"[SUCCESS] 已初始化离线看板: {init_board_file(args.init)}")
    elif args.list:
        adapter = OfflineBoardAdapter(args.list)
        items = adapter.list_records(limit=10000)
        print(f"共 {len(items)} 条任务（仅展示最新 5 条，倒序）:")
        recent_items = items[-5:][::-1] if len(items) > 5 else items[::-1]
        for it in recent_items:
            f = it["fields"]
            print(f"  {f.get('id'):<8} {f.get('status'):<6} {str(f.get('assignee','')):<10} {str(f.get('name',''))[:50]}")
        if len(items) > 5:
            print(f"  ... 其余 {len(items) - 5} 条请登录 Web 看板查看")
    else:
        parser.print_help()
