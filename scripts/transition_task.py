#!/usr/bin/env python3
"""
一键门控流转管道命令 (Transition Task Pipeline)
物理级硬防错：Fail-Closed 并发排他文件锁 + 门控断言 + 完整 Adapter/Schema 检验 + 物理原子补偿回滚 + 结构化审计日志 + 真实的 --dry-run 预检。
"""

import sys
import os
import re
import time
import datetime
import argparse
import logging
from typing import Any, Optional
from difflib import SequenceMatcher

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from _lib.core.validate_transition import validate, validate_delegation_authority
from _lib.boards.board_adapter_factory import get_board_adapter
from _lib.audit.audit_logger import record_audit_event
from _lib.core.file_lock import acquire_lock, release_lock, remove_lock_file_if_free, LockBusyError
from _lib.core.step_summary import generate_step_summary
from _lib.core.task_spec import resolve_default_stage_wp_wbs
from _lib.core.task_linter import lint_task_single_responsibility
from _lib.boards.offline_board_adapter import get_current_os_user
from enums import normalize_role, ROLE_NORMALIZE_MAP
import paths

# 容错型日志格式化类，防 traceback 泄漏
class SafeTaskFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "task_id"):
            record.task_id = "SYSTEM"
        return super().format(record)

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(SafeTaskFormatter("%(asctime)s [%(levelname)s] [Task: %(task_id)s] %(message)s"))

logger = logging.getLogger("transition_pipeline")
logger.setLevel(logging.INFO)
logger.addHandler(handler)


def cleanup_stale_locks(ttl_seconds: int = 300):
    """自动清理超过 ttl_seconds (默认5分钟) 的旧垃圾锁文件。
    安全语义：先非阻塞试锁确认无持有者，再在【持锁状态下】unlink——
    并发进程在 unlink 后只能拿到新 inode 的锁文件，互斥不会被删除破坏。
    扫描 user_data/locks/（现行）与 scripts/（历史残留自然过期清除）。"""
    now = time.time()
    removed = 0
    scan_dirs = []
    locks_dir = paths.locks_dir()
    os.makedirs(locks_dir, exist_ok=True)
    scan_dirs.append(locks_dir)
    if os.path.isdir(SCRIPT_DIR):
        scan_dirs.append(SCRIPT_DIR)
    for scan_dir in scan_dirs:
        for entry in os.listdir(scan_dir):
            if entry.startswith(".lock_") and entry.endswith(".lock"):
                full_p = os.path.join(scan_dir, entry)
                try:
                    if os.path.isfile(full_p) and (now - os.path.getmtime(full_p)) > ttl_seconds:
                        if remove_lock_file_if_free(full_p):
                            removed += 1
                            logger.info(f"[LOCK]  已清理无持有者的过期锁文件: {entry}")
                except Exception:
                    pass
    return removed


def acquire_concurrency_lock(task_id: str):
    """获取物理排他并发锁 (Fail-Closed：冲突则直接返回 None, None 阻断)
    统一走 file_lock 抽象（Unix fcntl / Windows msvcrt），锁内写入 pid/ts 元数据。
    锁文件落 data_root/user_data/locks/（共享安装下不污染只读 skill 代码）。"""
    cleanup_stale_locks(300)
    locks_dir = paths.locks_dir()
    os.makedirs(locks_dir, exist_ok=True)
    lock_file = os.path.join(locks_dir, f".lock_{task_id}.lock")
    try:
        handle = acquire_lock(lock_file, blocking=False)
        return handle, lock_file
    except LockBusyError:
        return None, None
    except Exception:
        # Fail-Closed: 锁竞争失败或不支持，绝对返回 None！
        return None, None


def release_concurrency_lock(lock_tuple):
    """释放并发锁：只解锁不删除锁文件。
    删除统一交给 cleanup_stale_locks 的持锁 unlink，消除"释放后立即删除"的竞态窗口。"""
    if not lock_tuple or not lock_tuple[0]:
        return
    handle, _lock_file = lock_tuple
    release_lock(handle)


ROLE_NAME_MAP = ROLE_NORMALIZE_MAP


def normalize_role_name(val: Any) -> str:
    """角色编码/子代理 ID/占位符 归一化为中文角色名"""
    if not val:
        return ""
    return normalize_role(val)

PLACEHOLDER_TASK_NAMES = {"", "工作包任务", "-", "暂无", "新建任务", "未命名任务"}


def normalize_task_name(name: str) -> str:
    """任务名称归一化：去除空白与常见标点、转小写，用于重复度比对。"""
    return re.sub(r"[\s\u3000，,。.;；:：()（）\[\]【】{}<>《》\"'`~!！?？\-_/\\|]", "", str(name)).lower()


def check_duplicate_tasks(adapter, task_name, cfg_dup, limit=10, threshold=0.8, exclude_task_id=None):
    """重复任务校验：取看板最近 N 条任务（按 seq 倒序），与 task_name 做三级命中比对。
    返回命中候选列表 [{task_id, name, level}]；无命中或未启用返回空列表。
    配置：duplicate_check.enabled / limit / threshold（workflow.config.yaml）。"""
    raw = str(task_name or "").strip()
    if not raw or raw in PLACEHOLDER_TASK_NAMES:
        return []
    dup_cfg = cfg_dup or {}
    if dup_cfg.get("enabled", True) is False:
        return []
    limit = int(dup_cfg.get("limit", limit) or limit)
    threshold = float(dup_cfg.get("threshold", threshold) or threshold)
    try:
        recs = adapter.list_records(limit=1000)
    except Exception:
        return []
    recs = sorted(recs, key=lambda r: int(r.get("fields", {}).get("seq") or 0), reverse=True)
    target = normalize_task_name(raw)
    hits = []
    for r in recs[:limit]:
        f = r.get("fields", {})
        tid = str(f.get("id") or r.get("record_id") or "")
        if exclude_task_id and tid.upper() == str(exclude_task_id).upper():
            continue
        name = str(f.get("name") or f.get("task_name") or "")
        if not name:
            continue
        n = normalize_task_name(name)
        if not n:
            continue
        if n == target:
            level = "完全一致"
        elif target in n or n in target:
            level = "包含关系"
        else:
            ratio = SequenceMatcher(None, target, n).ratio()
            if ratio < threshold:
                continue
            level = f"相似度 {ratio:.2f}"
        hits.append({"task_id": f.get("id"), "name": name, "level": level})
    return hits


def print_duplicate_protocol(task_name, hits):
    """输出机器可解析的重复任务协议行 + 人类可读候选列表（无弹窗，输出后命令终止由调用方处理）。"""
    print(f"DUPLICATE_TASK|v1|{task_name}|" + "|".join(f"{h['task_id']}({h['level']})" for h in hits))
    for h in hits:
        print(f"  [重复候选] {h['task_id']} {h['name']} ({h['level']})")


def normalize_stage_name(stage_str: Optional[str]) -> Optional[str]:
    """标准化阶段名称：将 Sprint-1, sprint 1, Sprint_1, S1 等统一格式化为标准规范 'Sprint 1'，
    非 Sprint 格式（如 Milestone 1、灰度发布）原样放行，绝不破坏。"""
    if not stage_str or stage_str == "-":
        return stage_str
    s = str(stage_str).strip()
    m = re.match(r"^(?:sprint|stage|s)[\s_\-]*(\d+)$", s, re.IGNORECASE)
    if m:
        return f"Sprint {m.group(1)}"
    return s


def transition_task_pipeline(
    config_path: str,
    task_id: str = "",
    record_id: str = None,
    current_role: str = "",
    from_status: str = "",
    to_status: str = "",
    assignee: str = "",
    task_type: str = "A",
    est_hours: float = 0.0,
    pretask: str = None,
    ignore_pretask: bool = False,
    start_time: str = None,
    end_time: str = None,
    remarks: str = None,
    comment: str = None,
    dry_run: bool = False,
    active_dev_count: int = 1,
    task_name: str = None,
    stage: str = None,
    wp: str = None,
    wbs: str = None,
    owner: str = None,
    creator: str = None,
    creator_role: str = None,
    operator: str = None,
    delegated_by: str = "",
    delegation_reason: str = "",
    force_verify_operator: bool = False,
    force_reopen: bool = False,
    create_only: bool = False,
    force: bool = False,
    no_dup_check: bool = False,
    target: str = None,
    criteria: Any = None,
    week: str = None,
) -> bool:
    resolved_task_id = task_id or "AUTO"
    extra_log = {"task_id": resolved_task_id}
    stage = normalize_stage_name(stage)
    logger.info(f"[SECURITY]  触发防错门控校验 ({from_status} -> {to_status}, 模式: {'DRY-RUN' if dry_run else 'REAL'})...", extra=extra_log)

    # 0. 模式参数校验：流转模式必须提供 from/to/assignee；仅建卡使用 --create
    if not create_only and (not from_status or not to_status or not assignee):
        logger.error("[FAILED]  流转模式必须提供 --from-status/--to-status/--assignee；仅建卡请使用 --create", extra=extra_log)
        return False

    # 0. 提权代行白名单预检(Fail-Closed):在 validate 前阻断非法代行
    #    无代行声明(delegated_by 为空)时直接跳过,交由原 validate 权限矩阵处理
    if not validate_delegation_authority(current_role, delegated_by):
        logger.error(f"[FAILED]  [代行未授权] 角色 {current_role} 不接受来自 {delegated_by} 的代行授权,硬阻断！", extra=extra_log)
        record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, f"代行未授权阻断: {delegated_by} 代行 {current_role}", delegated_by=delegated_by, delegation_reason=delegation_reason)
        return False

    # 0.1 安全门禁 (2026-08-27): 流转至【已验收】必须携带真实人类操作凭据 (Fail-Closed)
    #     合法通道仅两种:
    #       A) Web 看板 API 持主控 Token 验证后注入 delegated_by="OPERATOR_VIA_TOKEN";
    #       B) 真人终端调用 (--force-verify-operator / quick_task accept): 由入口层完成
    #          isatty 检测与 [y/N] 交互确认后注入。
    #     CLI 显式伪造 role=USER 或 delegated_by=USER 均不再被承认。
    if to_status == "已验收":
        _operator_vouched = bool(force_verify_operator) or (
            str(delegated_by or "").strip().upper() == "OPERATOR_VIA_TOKEN"
        )
        if not _operator_vouched:
            print("[REJECT 人类专属门禁] 流转至【已验收】必须由真实人类授权: Web 看板主控 Token 验收, 或真人终端执行 quick_task.py accept。CLI 自报 role/delegated-by=USER 不再被承认！")
            logger.error("[FAILED]  [人类专属门禁] 流转至【已验收】必须由真实人类授权: Web 看板主控 Token 验收, 或真人终端执行 quick_task.py accept。CLI 自报 role/delegated-by=USER 不再被承认！", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "人类专属验收门禁拦截: 缺少真实人类操作凭据", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

    # 1. 尝试获取并发独占锁 (Fail-Closed 硬拦截)
    #    AUTO 场景使用全局建单锁，特定 task_id 使用 per-task 锁
    lock_key = resolved_task_id if resolved_task_id != "AUTO" else "auto_create_global"
    lock_tuple = acquire_concurrency_lock(lock_key)
    if not lock_tuple or not lock_tuple[0]:
        logger.error(f"[FAILED]  [并发锁排他硬拦截] 任务 {resolved_task_id} (锁标识: {lock_key}) 当前正被另一个进程独占写卡中，物理阻断！", extra=extra_log)
        record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "物理并发排他锁硬拦截", delegated_by=delegated_by, delegation_reason=delegation_reason)
        return False

    try:
        # 2. 完整加载看板 Adapter 与配置文件格式断言 (dry-run 模式下也不跳过校验)
        import yaml
        try:
            adapter = get_board_adapter(config_path)
            # config_path 为 None（未传 --config）时用 factory 同一解析链定位
            effective_config = config_path or paths.resolve_runtime_config()
            with open(effective_config, "r", encoding="utf-8") as cfg_f:
                cfg_data = yaml.safe_load(cfg_f)
                field_mapping = cfg_data.get("board", {}).get("fields", {})
        except Exception as e:
            logger.error(f"[FAILED]  看板配置文件/Schema 校验断言失败: {e}，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"配置文件校验失败: {e}", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        if not adapter:
            logger.error("[FAILED]  适配器未正确初始化，拦截落库", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "适配器缺失", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        dup_cfg = cfg_data.get("duplicate_check", {}) or {}

        # 2.5 显式建单模式 (--create / quick create)：建卡为【待开始】，不执行流转
        if create_only:
            role_upper = current_role.upper()
            effective_assignee = normalize_role_name(assignee or current_role)
            expected_self = normalize_role_name(role_upper)
            # 建卡权限：PM 可派发任意处理人；非 PM 仅可为自己建卡
            if role_upper != "PM" and effective_assignee != expected_self:
                logger.error(f"[FAILED]  [建卡权限拦截] 角色 {role_upper} 仅可为自己建卡（assignee 必须为 {expected_self}），如需派发请由 PM 执行！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, "新建", "待开始", assignee, False, "建卡权限拦截", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False
            if not task_name or not str(task_name).strip():
                logger.error("[FAILED]  [建卡拦截] --create 模式必须提供 --task-name！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, "新建", "待开始", assignee, False, "建卡缺失任务名", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False

            # 单一任务原则 (SRP) 前置校验：拦截跨领域混合、并列复合动作、任务类型与角色不匹配等复合大卡
            srp_ok, srp_vtype, srp_reasons, srp_splits = lint_task_single_responsibility(
                name=task_name,
                task_type=task_type or "A",
                assignee=effective_assignee,
                est_hours=est_hours or 0.0
            )
            if not srp_ok:
                if not force:
                    logger.error(f"[FAILED]  [单一任务原则拦截] 任务卡 [{task_name}] 违反单一职责规范 ({srp_vtype})！", extra=extra_log)
                    for r in srp_reasons:
                        logger.error(f"  ❌ 原因: {r}", extra=extra_log)
                    if srp_splits:
                        logger.info("  💡 推荐原子任务拆解清单:", extra=extra_log)
                        for s in srp_splits:
                            logger.info(f"     ➔ {s}", extra=extra_log)
                    logger.info("  👉 如确需特殊情况强制建卡，请追加 --force 参数重跑。", extra=extra_log)
                    record_audit_event(resolved_task_id, current_role, "新建", "待开始", assignee, False, f"单一任务校验拦截: {'; '.join(srp_reasons)}", delegated_by=delegated_by, delegation_reason=delegation_reason)
                    return False
                else:
                    logger.warning(f"[WARN]  [单一任务原则覆盖] 用户确认强制创建（--force），忽略 {len(srp_reasons)} 条单一职责告警: {'; '.join(srp_reasons)}", extra=extra_log)

            # 重复任务校验：命中时输出重复内容并终止命令（无弹窗），用户决策后以 --force 重跑
            if not no_dup_check:
                dup_hits = check_duplicate_tasks(adapter, task_name, dup_cfg, exclude_task_id=task_id)
                if dup_hits:
                    print_duplicate_protocol(task_name, dup_hits)
                    if not force:
                        logger.error(f"[FAILED]  [重复任务拦截] 任务名称疑似与 {len(dup_hits)} 条现有任务重复，命令终止；确认重复创建请加 --force 重跑", extra=extra_log)
                        record_audit_event(resolved_task_id, current_role, "新建", "待开始", assignee, False, f"重复任务校验拦截: {len(dup_hits)} 条候选", delegated_by=delegated_by, delegation_reason=delegation_reason)
                        return False
                    logger.warning(f"[WARN]  [重复任务] 用户确认强制创建（--force），命中 {len(dup_hits)} 条候选", extra=extra_log)
            # 任务负责人 (Owner): 实际执行人。PM派单时默认等于被派发的执行人(如李开发)；自建自领为自身
            if owner:
                effective_owner = normalize_role_name(owner)
            else:
                effective_owner = effective_assignee if role_upper == "PM" else expected_self

            try:
                all_cards = adapter.list_records(limit=2000)
            except Exception:
                all_cards = []
            res_stage, res_wp, res_wbs = resolve_default_stage_wp_wbs(all_cards, stage=stage, wp=wp, wbs=wbs)

            effective_creator = creator or get_current_os_user()
            effective_creator_role = normalize_role_name(creator_role or current_role or "PM")
            effective_operator = operator or effective_creator

            create_fields = {
                "task_id": task_id,
                "task_name": task_name,
                "status": "待开始",
                "assignee": effective_owner,
                "owner": effective_owner,
                "handler": effective_assignee,
                "stage": res_stage,
                "workpackage": res_wp,
                "wbs_id": res_wbs,
                "creator": effective_creator,
                "creator_role": effective_creator_role,
                "operator": effective_operator,
                "start_date": start_time or None,
                "type": task_type or "A",
                "task_type": task_type or "A",
                "est_hours": est_hours or 0.0,
                "act_hours": 0.0,
                "pretask": pretask or None,
                "process": None,
                "remarks": remarks or None,
                "target": target or None,
                "acceptance_criteria": criteria or [],
            }
            if hasattr(adapter, "create_record") and "week" in adapter.create_record.__code__.co_varnames:
                created_id = adapter.create_record(create_fields, week=week)
            else:
                created_id = adapter.create_record(create_fields)
            if not created_id:
                logger.error("[FAILED]  建单失败（编号冲突或写入失败），硬阻断！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, "新建", "待开始", assignee, False, "建单失败", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False
            logger.info(f" 任务 {created_id} 已建卡【待开始】(负责人: {effective_owner}, 处理人: {effective_assignee})", extra={"task_id": created_id})
            record_audit_event(created_id, current_role, "新建", "待开始", effective_assignee, True, "显式建单", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return True

        # 从配置与现有工单解析 task_name 与 max_parallel_tasks
        role_cfg = cfg_data.get("roles", {}).get(current_role.upper(), {})
        max_parallel = role_cfg.get("max_parallel_tasks", 3)

        effective_task_name = task_name or ""
        if resolved_task_id != "AUTO":
            existing_rec = adapter.get_record(resolved_task_id)
            if existing_rec:
                f_data = existing_rec.get("fields", {})
                board_task_name = f_data.get("task_name") or f_data.get("name") or ""
                # 针对已存在看板卡片，防 CLI 伪造 [HOTFIX]，校验强制以看板记录的真实名称为准
                if board_task_name:
                    effective_task_name = board_task_name

        # 动态解析活跃进行中任务数，防隐式逃逸并发限制
        effective_active_dev_count = active_dev_count
        all_workers = ["DEV", "FRONTEND", "QA", "DOCS", "ARCHITECT", "DEVOPS"]
        if to_status == "进行中" and current_role.upper() in all_workers:
            try:
                status_k = field_mapping.get("status", "status")
                assignee_k = field_mapping.get("assignee", "assignee")
                recs = adapter.list_records(limit=1000)
                board_active_count = 0
                target_norms = {normalize_role(assignee), normalize_role(current_role), assignee, current_role}
                for r in recs:
                    f = r.get("fields", {})
                    st_val = str(f.get(status_k) or f.get("status") or "")
                    as_val = str(f.get(assignee_k) or f.get("assignee") or "")
                    as_norm = normalize_role(as_val)
                    if st_val == "进行中" and (as_norm in target_norms or as_val in target_norms):
                        board_active_count += 1
                effective_active_dev_count = max(active_dev_count, board_active_count)
            except Exception:
                pass

        # 3. 身份硬校验（前置）：执行状态流转（from_status 不是待开始/新建）必须显式提供 --task-id，
        #    严禁无任务 ID 隐式创建新卡片；先于门控校验快速失败
        if not task_id and from_status not in ["待开始", "新建"]:
            logger.error(f"[FAILED]  [Fail-Closed 物理硬拦截] 执行状态流转 ({from_status} -> {to_status}) 时必须通过 --task-id 提供原任务编号，严禁无任务 ID 隐式创建新卡片！", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, False, "流转缺失task_id", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        # 4. 任务存在性检查（只读，前置）：确定目标记录与是否需要自动建单
        resolved_record_id = record_id or task_id
        existing = adapter.get_record(resolved_record_id) if resolved_record_id else None

        eff_pretask = pretask
        if not eff_pretask and existing:
            eff_pretask = existing.get("fields", {}).get("pretask")

        # 5. 强制运行防护门控 (并发上限与 HOTFIX 特权透传，未通过则直接抛错中断！)
        is_valid = validate(
            role=current_role,
            from_status=from_status,
            to_status=to_status,
            assignee=assignee,
            end_time=end_time or "",
            active_dev_count=effective_active_dev_count,
            task_type=task_type,
            task_name=effective_task_name,
            max_parallel=max_parallel,
            remarks=remarks or "",
            delegated_by=delegated_by or "",
            delegation_reason=delegation_reason or "",
            pretask=eff_pretask or "",
            adapter=adapter,
            ignore_pretask=ignore_pretask or force,
            force_verify_operator=force_verify_operator,
            force_reopen=force_reopen,
        )

        if not is_valid:
            logger.error("[FAILED]  门控物理拦截失败！阻止落库更新", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "门控规则校验未通过", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        logger.info("[SUCCESS]  防错规则核验成功", extra=extra_log)

        # [CCP 连续性门禁扩展插槽 - 默认受环境变量保护，Fail-Safe]
        if os.environ.get("YY_FLOW_ENABLE_CCP_GATE") == "1":
            try:
                from _lib.ccp.validators.pipeline import check_continuity_gate
                ccp_report = check_continuity_gate(task_id or resolved_record_id or "UNKNOWN", to_status)
                logger.info(f"[CCP_GATE] 连续性门禁预检状态: {ccp_report.status}", extra=extra_log)
            except Exception as _e:
                logger.warning(f"[CCP_GATE_SKIP] 连续性门禁预检跳过: {_e}", extra=extra_log)

        # 6. 动态读取 Key 映射
        status_key = field_mapping.get("status", "status")
        assignee_key = field_mapping.get("assignee", "assignee")
        end_time_key = field_mapping.get("end_time", "end_time")

        # 7. dry-run 模式：不落库，仅提示正式执行时的行为（门控已通过）
        if dry_run:
            if task_id and existing is None:
                logger.info(f"ℹ [DRY-RUN] 任务 {task_id} 在看板中不存在，正式执行时将自动创建后再流转", extra=extra_log)
            logger.info(" [DRY-RUN] 配置文件与 Schema 检验完全通过！模拟预检不触发物理网络写卡", extra=extra_log)
            record_audit_event(resolved_task_id, current_role, from_status, to_status, assignee, True, "DRY-RUN 完整校验测试通过", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return True

        norm_assignee = normalize_role_name(assignee)

        # 8. 物理硬阻断：对于 A 类常规开发任务，若看板中尚无此任务，绝对禁止直接新建为【已完成/审查中】！
        # 所有任务卡必须经历【待开始】：任务开始时先建单为【待开始】，领取后转【进行中】，完成后再提交！
        if existing is None:
            is_valid_creation = (from_status in ["待开始", "新建"]) or (to_status == "进行中") or (task_type in ["B", "C", "D", "E", "F", "G"])
            if not is_valid_creation:
                logger.error(f"[FAILED]  [物理硬阻断] 看板中尚无此任务，绝对禁止直接新建为【{to_status}】！你必须首先在任务开始时调用 CLI 初始化建单为【待开始】！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, from_status, to_status, norm_assignee, False, f"拒绝直接新建为{to_status}", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False

            # 兜底自动建单同样执行重复任务校验（命中输出重复内容并终止命令，--force 确认重跑）
            if not no_dup_check:
                dup_hits = check_duplicate_tasks(adapter, task_name, dup_cfg)
                if dup_hits and not force:
                    print_duplicate_protocol(task_name, dup_hits)
                    logger.error(f"[FAILED]  [重复任务拦截] 自动建单疑似与 {len(dup_hits)} 条现有任务重复，命令终止；确认请加 --force 重跑", extra=extra_log)
                    record_audit_event(resolved_task_id, current_role, from_status, to_status, norm_assignee, False, f"重复任务校验拦截: {len(dup_hits)} 条候选", delegated_by=delegated_by, delegation_reason=delegation_reason)
                    return False

            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            initial_status = "待开始"  # 所有任务卡必须经历【待开始】
            effective_owner = normalize_role_name(owner) if owner else norm_assignee
            try:
                all_cards = adapter.list_records(limit=2000)
            except Exception:
                all_cards = []
            res_stage, res_wp, res_wbs = resolve_default_stage_wp_wbs(all_cards, stage=stage, wp=wp, wbs=wbs)

            effective_creator = creator or get_current_os_user()
            effective_creator_role = normalize_role_name(creator_role or current_role or "PM")
            effective_operator = operator or effective_creator

            create_fields = {
                "task_id": task_id,
                "task_name": task_name or "工作包任务",
                "status": initial_status,
                "assignee": effective_owner,
                "owner": effective_owner,
                "handler": norm_assignee,
                "stage": res_stage,
                "workpackage": res_wp,
                "wbs_id": res_wbs,
                "creator": effective_creator,
                "creator_role": effective_creator_role,
                "operator": effective_operator,
                "start_date": start_time or None,
                "type": task_type or "A",
                "task_type": task_type or "A",
                "est_hours": est_hours or 0.0,
                "act_hours": 0.0,
                "pretask": pretask or None,
                "process": None,
                "remarks": None,
                "target": target or None,
                "acceptance_criteria": criteria or [],
            }
            if hasattr(adapter, "create_record") and "week" in adapter.create_record.__code__.co_varnames:
                created_id = adapter.create_record(create_fields, week=week)
            else:
                created_id = adapter.create_record(create_fields)
            if not created_id:
                logger.error(f"[FAILED]  任务自动创建失败（编号冲突或写入失败），硬阻断流转！", extra=extra_log)
                record_audit_event(resolved_task_id, current_role, from_status, to_status, norm_assignee, False, "任务自动创建失败", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False
            if not task_id:
                task_id = created_id
            resolved_record_id = task_id
            extra_log = {"task_id": task_id}
            logger.info(f" 任务 {task_id} 在看板中不存在，已成功初始化建单为【{initial_status}】(负责人: {effective_owner}, 处理人: {norm_assignee})", extra=extra_log)
            record_audit_event(task_id, current_role, "新建", initial_status, norm_assignee, True, "任务自动初始化建单", delegated_by=delegated_by, delegation_reason=delegation_reason)
        else:
            resolved_record_id = existing.get("record_id") or resolved_record_id

        # 8.1 同步更新主负责人字段（生命周期保持稳定）
        if owner and not create_only:
            update_fields[field_mapping.get("owner", "assignee")] = normalize_role_name(owner)

        if not resolved_record_id:
            resolved_record_id = task_id or (existing.get("record_id") if existing else None)
        if not resolved_record_id:
            logger.error("[FAILED]  无法确定物理更新的记录 ID，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "无法确定记录ID", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        if existing and not task_id:
            resolved_record_id = existing.get("record_id") or resolved_record_id

        # 9. 执行物理原子写入
        exist_fields = (existing.get("fields", {}) if existing else {}) or {}
        end_time_key = field_mapping.get("end_time") or field_mapping.get("end_date", "end_date")
        start_time_key = field_mapping.get("start_time") or field_mapping.get("start_date", "start_time")

        # 处理人 (handler): 随流转推进更新；终态（已完成/已验收/已取消）默认收敛至 严经理
        target_handler = norm_assignee
        if to_status in ["已完成", "已验收", "已取消"] and (not target_handler or target_handler == normalize_role_name(current_role)):
            target_handler = "严经理"
        elif to_status == "已退回":
            orig_owner = exist_fields.get("assignee") or exist_fields.get("owner")
            if orig_owner:
                target_handler = normalize_role_name(orig_owner)

        handler_key = field_mapping.get("handler", "handler")
        owner_key = field_mapping.get("owner") or field_mapping.get("assignee", "assignee")
        
        # operator 物理防伪：必须为真实自然人/系统用户名，若传入虚拟角色代号强制回退为当前系统用户
        virtual_roles = {"严经理", "钱架构", "李开发", "马前端", "周审查", "章测试", "李文通", "吕改特", "pm", "arch", "dev", "frontend", "reviewer", "qa", "docs", "devops"}
        effective_operator = operator
        if not effective_operator or str(effective_operator).strip().lower() in virtual_roles or str(effective_operator).strip() in virtual_roles:
            effective_operator = get_current_os_user() or "用户"

        update_fields = {status_key: to_status, handler_key: target_handler, "operator": effective_operator}
        if "status" not in update_fields:
            update_fields["status"] = to_status
        if owner:
            update_fields[owner_key] = normalize_role_name(owner)
        if to_status in ["已完成", "已验收", "已取消"]:
            if end_time:
                update_fields[end_time_key] = end_time
            elif not (exist_fields.get(end_time_key) or exist_fields.get("end_date") or exist_fields.get("end_time")):
                update_fields[end_time_key] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            update_fields[end_time_key] = ""  # 迁回活跃状态时强制清空完工时间戳

        # 终态纠偏重开 (force_reopen) 专属清洗逻辑：
        # 若重开至【进行中】，必须物理清洗原有结束时间戳与生效工时，避免效能度量负数畸变；
        # 且若经办人未显式指定（或仍为 PM），自动回退至任务原始负责人 (Owner)
        if force_reopen and to_status == "进行中":
            update_fields[end_time_key] = ""
            update_fields["end_date"] = ""
            update_fields["act_hours"] = None
            orig_owner = exist_fields.get("owner") or exist_fields.get("handler") or ""
            if orig_owner and (not assignee or assignee in ["PM", "严经理"]):
                update_fields[handler_key] = orig_owner
                target_handler = orig_owner
                logger.info(f" [REOPEN]  已自动将重开工单经办人回退至原负责人: {orig_owner}", extra=extra_log)

        if stage: update_fields[field_mapping.get("stage", "stage")] = stage
        if wp: update_fields[field_mapping.get("workpackage", "workpackage")] = wp
        if wbs: update_fields[field_mapping.get("wbs_id", "wbs_id")] = wbs
        if task_name: update_fields[field_mapping.get("task_name", "task_name")] = task_name
        # 领取开工与终态开工时间兜底：
        # 1) 首次从【待开始】推进到【进行中】时，动态落盘当前真实开工时间戳（若未显式指定 start_time）
        # 2) 直推终态（已完成/已验收）且尚无 start_date 时：
        #    - 若提供了 start_time，使用 start_time；
        #    - 若提供了 est_hours > 0，自动按 (end_time - est_hours) 智能回溯开工时间戳；
        #    - 否则补填当前时间。
        # 3) 从【已退回】重新领回【进行中】时，保留原有 start_date 不覆盖，保护初始开工时间！
        current_start = exist_fields.get(start_time_key) or exist_fields.get("start_date") or exist_fields.get("start_time")
        if start_time:
            update_fields[start_time_key] = start_time
        elif to_status == "进行中" and from_status == "待开始":
            update_fields[start_time_key] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif to_status in ["已完成", "已验收"]:
            eff_end = update_fields.get(end_time_key) or end_time or datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if not current_start or current_start == eff_end:
                if est_hours and float(est_hours) > 0:
                    try:
                        e_dt = datetime.datetime.strptime(str(eff_end).strip(), '%Y-%m-%d %H:%M:%S')
                        s_dt = e_dt - datetime.timedelta(minutes=int(float(est_hours) * 60))
                        update_fields[start_time_key] = s_dt.strftime('%Y-%m-%d %H:%M:%S')
                        update_fields["act_hours"] = float(est_hours)
                    except Exception:
                        if not current_start:
                            update_fields[start_time_key] = eff_end
                elif not current_start:
                    update_fields[start_time_key] = eff_end
        elif to_status in ["进行中"] and not current_start:
            update_fields[start_time_key] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        orig_handler = (existing.get("fields", {}).get(handler_key) or existing.get("fields", {}).get("handler") if existing else None) or current_role

        try:
            success = adapter.update_record(resolved_record_id, update_fields, force_reopen=force_reopen)
            if not success:
                logger.error("[FAILED]  物理 API 写入失败，硬阻断流转！", extra=extra_log)
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "看板状态 API 写入失败", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False
        except Exception as e:
            logger.error(f"[FAILED]  物理 API 调用抛出异常 ({e})，硬阻断！", extra=extra_log)
            record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"API 抛出异常: {e}", delegated_by=delegated_by, delegation_reason=delegation_reason)
            return False

        # 10. 追加备注与补偿回滚
        remarks_key = field_mapping.get("remarks", "remarks")
        if remarks:
            try:
                rem_ok = adapter.append_remarks(resolved_record_id, remarks_key, remarks)
                if not rem_ok:
                    logger.warning("[WARN]  结构化缺陷备注追加失败，准备执行物理原子补偿回滚...", extra=extra_log)
                    rollback_fields = {status_key: from_status, handler_key: orig_handler}
                    # 回滚必须写回 resolved_record_id（auto-create 场景 record_id 为 None，原实现回滚静默失效）
                    adapter.update_record(resolved_record_id, rollback_fields)
                    logger.error("[SYNC]  状态已物理回滚还原至原状态，拒绝非原子性中间态落库！", extra=extra_log)
                    record_audit_event(task_id, current_role, from_status, to_status, assignee, False, "追加备注失败触发状态原子补偿回滚", delegated_by=delegated_by, delegation_reason=delegation_reason)
                    return False
            except Exception as e:
                logger.error(f"[WARN]  备注追加抛出异常 ({e})，执行物理原子补偿回滚...", extra=extra_log)
                adapter.update_record(resolved_record_id, {status_key: from_status, handler_key: orig_handler})
                record_audit_event(task_id, current_role, from_status, to_status, assignee, False, f"备注异常回滚: {e}", delegated_by=delegated_by, delegation_reason=delegation_reason)
                return False

        # 11. 追加流程节点行（任务ID-N序号 双标识；时间线渲染与排序的数据源）
        #     失败仅告警不回滚——节点行是展示增强，状态本体已原子落库；
        #     但烧掉的节点号不复用，审计日志仍有完整记录
        try:
            if hasattr(adapter, "append_process_node"):
                effective_role = normalize_role(current_role) or "用户"
                effective_operator = operator or get_current_os_user() or "用户"
                effective_comment = (comment or remarks or "").strip()
                if not effective_comment:
                    effective_comment = generate_step_summary(from_status or "待开始", to_status, effective_task_name, effective_role)
                node_id = adapter.append_process_node(
                    resolved_record_id, effective_role,
                    from_status or "-", to_status, effective_operator,
                    comment=effective_comment)
                if node_id:
                    logger.info(f" [NODE]  已追加流程节点 {node_id}", extra=extra_log)
                else:
                    logger.warning("[WARN]  流程节点行追加失败（记录不存在？），不影响已落库状态", extra=extra_log)
        except Exception as e:
            logger.warning(f"[WARN]  流程节点行追加异常 ({e})，不影响已落库状态", extra=extra_log)

        logger.info(f" 看板 {task_id} 已成功推至【{to_status}】，处理人: {target_handler}", extra=extra_log)
        record_audit_event(task_id, current_role, from_status, to_status, target_handler, True, "流转全量物理落库成功", delegated_by=delegated_by, delegation_reason=delegation_reason)
        return True

    finally:
        release_concurrency_lock(lock_tuple)


def main():
    parser = argparse.ArgumentParser(description="一键门控任务流转管道工具")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--task-id", default="", help="任务编号 (如 T0001)；不传则自动分配最大编号+1 (并发安全)")
    parser.add_argument("--record-id", default=None, help="看板内部记录 ID (离线看板默认等于任务编号，可省略)")
    parser.add_argument("--task-name", "--name", dest="task_name", default=None, help="任务名称 (任务不存在自动创建时必填建议项)")
    parser.add_argument("--stage", default=None, help="项目阶段 (自动创建时写入)")
    parser.add_argument("--wp", default=None, help="工作包 (自动创建时写入)")
    parser.add_argument("--wbs", default=None, help="WBS 编号 (自动创建时写入)")
    parser.add_argument("--owner", default=None, help="任务负责人 (实际承接人，生命周期保持稳定)")
    parser.add_argument("--role", required=True, help="当前触发者角色 (PM/DEV/REVIEWER/QA 等)")
    parser.add_argument("--from-status", default="", help="原状态 (流转模式必填；--create 建卡模式可省略)")
    parser.add_argument("--to-status", default="", help="目标状态 (流转模式必填；--create 建卡模式可省略)")
    parser.add_argument("--assignee", default="", help="同步更新的处理人 (流转模式必填；--create 建卡模式必填)")
    parser.add_argument("--type", default="A", help="任务类型 (A-G: A为L2标准任务全链; B/C/D/F/G为L1轻量任务短链; E为用户直验)")
    parser.add_argument("--est-hours", type=float, default=0.0, help="预估工时 (小时)")
    parser.add_argument("--pretask", default=None, help="前置依赖任务编号 (如 T0001 或 T0001,T0002)")
    parser.add_argument("--ignore-pretask", action="store_true", help="忽略前置任务状态强制推进")
    parser.add_argument("--start-time", default=None, help="开始时间 (格式 YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--end-time", help="结束时间 (完成/验收必填)")
    parser.add_argument("--remarks", help="追加结构化缺陷或备注描述")
    parser.add_argument("--comment", default=None, help="操作说明/阶段交付总结 (写入流程节点)")
    parser.add_argument("--active-dev-count", type=int, default=1, help="当前开发人员'进行中'任务数 (并发上限校验用)")
    parser.add_argument("--dry-run", action="store_true", help="开启预检测试模式而不物理写卡")
    parser.add_argument("--creator", default=None, help="真人创建人/系统用户名 (任务新建时记录)")
    parser.add_argument("--creator-role", default=None, help="建单虚拟专家角色 (如 PM/严经理/钱架构)")
    parser.add_argument("--operator", default=None, help="真实人类操作人姓名 (缺省自动读取 Git/OS 用户名)")
    parser.add_argument("--delegated-by", default="", help="提权代行来源角色 (如 PM/USER),留痕到 audit,需在白名单内")
    parser.add_argument("--delegation-reason", default="", help="提权代行理由")
    parser.add_argument("--force-verify-operator", action="store_true",
                        help="[仅限真人交互] 声明本次为真人终端操作 (自动 TTY 检测 + [y/N] 二次确认)；非交互环境会被物理阻断")
    parser.add_argument("--force-reopen", action="store_true",
                        help="终态纠偏重开模式：允许由 PM (严经理) 或真实人类用户 (USER) 将已验收/已取消工单受控回退至进行中或已完成")
    parser.add_argument("--create", action="store_true", help="显式建单模式：创建任务卡【待开始】并分配处理人，不执行流转")
    parser.add_argument("--target", default=None, help="任务核心目标说明")
    parser.add_argument("--criteria", action="append", default=None, help="验收标准（支持传多次或用分号/换行分隔）")
    parser.add_argument("--week", default=None, help="显式归属周口径 (如 2026-W36)")
    parser.add_argument("--force", action="store_true", help="重复任务校验命中时强制创建（用户已确认重复创建）")
    parser.add_argument("--no-dup-check", action="store_true", help="跳过重复任务校验")

    args = parser.parse_args()

    # 0.2 真人操作凭据入口门禁 (2026-08-27 安全加固):
    #     --force-verify-operator 仅是"声明"，绝不直接可信 —— 必须同时满足:
    #       a) stdin 为交互式终端 (TTY 检测，物理阻断自动化子进程/管道/CI);
    #       b) 目标状态必须是【已验收】(仅人类专属终态才允许声明真人操作，其余状态视为滥用拒绝);
    #       c) 完成 [y/N] 二次确认 (真人敲击，防任何非阻塞脚本静默穿透)。
    #     全部通过后才向管线注入 force_verify_operator=True。
    _force_op = bool(getattr(args, "force_verify_operator", False))
    if _force_op:
        if not sys.stdin.isatty():
            print("[REJECT 物理拦截] --force-verify-operator 仅限真人交互终端使用！非交互/自动化环境请走 Web 看板主控 Token 验收。")
            sys.exit(1)
        if args.to_status != "已验收":
            print("[REJECT 越权拦截] --force-verify-operator 只能用于流转至【已验收】的人类专属验收，其他状态流转禁止声明真人操作！")
            sys.exit(1)
        print("[SECURITY]  即将以真人身份执行最终验收，任务将永久流转至【已验收】终态 (不可逆)。")
        try:
            confirm = input("请输入 y 确认 (其他任意键取消): ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm != "y":
            print("[CANCEL]  已取消操作，任务状态未变更。")
            sys.exit(1)

    ok = transition_task_pipeline(
        config_path=args.config,
        task_id=args.task_id,
        record_id=args.record_id,
        current_role=args.role,
        from_status=args.from_status,
        to_status=args.to_status,
        assignee=args.assignee,
        task_type=args.type,
        est_hours=args.est_hours,
        pretask=args.pretask,
        ignore_pretask=args.ignore_pretask,
        start_time=args.start_time,
        end_time=args.end_time,
        remarks=args.remarks,
        comment=args.comment,
        dry_run=args.dry_run,
        active_dev_count=args.active_dev_count,
        task_name=args.task_name,
        stage=args.stage,
        wp=args.wp,
        wbs=args.wbs,
        owner=args.owner,
        creator=args.creator,
        creator_role=args.creator_role,
        operator=args.operator,
        delegated_by=args.delegated_by,
        delegation_reason=args.delegation_reason,
        force_verify_operator=_force_op,
        force_reopen=bool(getattr(args, "force_reopen", False)),
        create_only=args.create,
        force=args.force,
        no_dup_check=args.no_dup_check,
        target=getattr(args, "target", None),
        criteria=getattr(args, "criteria", None),
        week=getattr(args, "week", None),
    )

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
