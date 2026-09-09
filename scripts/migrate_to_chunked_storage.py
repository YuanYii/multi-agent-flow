#!/usr/bin/env python3
r"""
存量看板数据平滑迁移至 50 任务分卷工具 (Migrate to 50-Task Chunked Storage - CCP V2.0)

职责：
1. 探测 user_data/board.json 及存量自然周 YYYY-Www.yaml 中的历史任务卡片；
2. 自动创建物理备份 board.json.bak.<timestamp>；
3. 按照任务序号 O(1) 物理分流至固定 50 任务容量分卷 tasks_XXXX_YYYY.yaml；
4. 补齐 CCP V2.0 所需契约字段（tier, target, acceptance_criteria, contract, return_contract）；
5. 自动升级 user_data/workflow.config.yaml 与 config/workflow.config.yaml 的 storage_mode 为 chunked；
6. 幂等运行，已存在分卷中的任务自动比对不重复添加。
"""
import os
import sys
import json
import yaml
import time
import shutil
import re
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import paths

_TASK_ID_RE = re.compile(r"^T(\d+)$")
_WEEK_FILENAME_RE = re.compile(r"^\d{4}-W\d{2}\.(?:yaml|yml)$")
_CHUNK_FILENAME_RE = re.compile(r"^tasks_(\d{4})_(\d{4})\.(?:yaml|yml)$")


def get_chunk_range(seq: int, chunk_size: int = 50) -> Tuple[int, int]:
    """计算 50 任务分卷起止序号"""
    if seq < 1:
        seq = 1
    chunk_idx = (seq - 1) // chunk_size
    start_id = chunk_idx * chunk_size + 1
    end_id = (chunk_idx + 1) * chunk_size
    return start_id, end_id


def atomic_write_yaml(target_yaml: str, payload_data: dict) -> bool:
    """临时文件 + os.replace 原子覆写 YAML 文件"""
    target_dir = os.path.dirname(os.path.abspath(target_yaml))
    os.makedirs(target_dir, exist_ok=True)
    tmp_path = target_yaml + f".tmp.{os.getpid()}_{int(time.time()*1000)}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload_data, f, allow_unicode=True, sort_keys=False, indent=2)
        os.replace(tmp_path, target_yaml)
        return True
    except Exception as e:
        sys.stderr.write(f"[ERROR] 写入分卷文件失败 {target_yaml}: {e}\n")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def _safe_parse_hours(val: Any) -> float:
    """安全解析工时字段，支持 '1 min', '0.5h', '30m', '2.5' 等字符串或浮点数"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower()
    if not s or s in ("none", "null", ""):
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    m_min = re.search(r"^([\d\.]+)\s*(?:min|mins|分|分钟)$", s)
    if m_min:
        try:
            return round(float(m_min.group(1)) / 60.0, 2)
        except Exception:
            return 0.0
    m_hr = re.search(r"^([\d\.]+)\s*(?:h|hr|hrs|hour|hours|小时)$", s)
    if m_hr:
        try:
            return float(m_hr.group(1))
        except Exception:
            return 0.0
    m_num = re.search(r"[\d\.]+", s)
    if m_num:
        try:
            return float(m_num.group(0))
        except Exception:
            return 0.0
    return 0.0


def normalize_task_for_ccp(raw_card: Dict[str, Any], default_seq: int) -> Dict[str, Any]:
    """将历史任务数据结构规范化为 CCP V2.0 标准卡片"""
    task_id = str(raw_card.get("id") or raw_card.get("task_id") or "").strip()
    m = _TASK_ID_RE.match(task_id)
    if m:
        seq_num = int(m.group(1))
        if not task_id:
            task_id = f"T{seq_num:04d}"
    else:
        seq_num = int(raw_card.get("seq") or default_seq)
        if not task_id:
            task_id = f"T{seq_num:04d}"

    # 确定 Tier 等级
    tier = raw_card.get("tier")
    if not tier:
        task_type = str(raw_card.get("type") or raw_card.get("task_type") or "A").upper()
        if task_type in ("A", "C"):
            tier = "Tier-1"
        elif task_type in ("B", "E", "G"):
            tier = "Tier-2"
        else:
            tier = "Tier-3"

    raw_crit = raw_card.get("acceptance_criteria") or []
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
        "id": task_id,
        "seq": seq_num,
        "tier": tier,
        "name": str(raw_card.get("name") or raw_card.get("task_name") or "").strip(),
        "stage": raw_card.get("stage") or "开发阶段",
        "wp": raw_card.get("wp") or raw_card.get("workpackage") or "WP-默认",
        "wbs": raw_card.get("wbs") or raw_card.get("wbs_id") or "",
        "pretask": raw_card.get("pretask") or "",
        "assignee": raw_card.get("assignee") or "李开发",
        "handler": raw_card.get("handler") or raw_card.get("assignee") or "李开发",
        "creator": raw_card.get("creator") or "严经理",
        "creator_role": raw_card.get("creator_role") or "PM",
        "operator": raw_card.get("operator") or raw_card.get("creator") or "严经理",
        "owner": raw_card.get("owner") or raw_card.get("assignee") or "李开发",
        "status": raw_card.get("status") or "待开始",
        "priority": raw_card.get("priority") or "中",
        "est_hours": _safe_parse_hours(raw_card.get("est_hours") or raw_card.get("estimated_hours")),
        "act_hours": _safe_parse_hours(raw_card.get("act_hours") or raw_card.get("actual_hours")),
        "start_date": raw_card.get("start_date") or raw_card.get("start_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": raw_card.get("end_date") or raw_card.get("end_time") or "",
        "remarks": raw_card.get("remarks") or "",
        "target": raw_card.get("target") or "",
        "acceptance_criteria": crit_list,
        "requirement_id": raw_card.get("requirement_id") or "",
        "artifacts": raw_card.get("artifacts") or {},
        "handover_context": raw_card.get("handover_context") or {},
        "process": raw_card.get("process") or raw_card.get("process_desc") or "",
    }

    if raw_card.get("contract"):
        card["contract"] = raw_card.get("contract")
    if raw_card.get("return_contract"):
        card["return_contract"] = raw_card.get("return_contract")

    return card


def migrate_to_chunked_storage(project_root: Optional[str] = None, dry_run: bool = False) -> bool:
    """执行存量数据向固定 50 任务分卷的平滑迁移"""
    if project_root:
        pr_abs = os.path.abspath(project_root)
        if os.path.basename(pr_abs) == ".yy-flow":
            data_root = pr_abs
            host_proj = os.path.dirname(pr_abs)
        elif os.path.isdir(os.path.join(pr_abs, ".yy-flow")):
            data_root = os.path.join(pr_abs, ".yy-flow")
            host_proj = pr_abs
        else:
            data_root = paths.resolve_data_root(cwd=pr_abs)
            host_proj = pr_abs
    else:
        data_root = paths.resolve_data_root()
        host_proj = paths.project_root()

    user_data_dir = os.path.join(data_root, "user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    # 确定目标分卷目录：若配置中显式指定了 paths.task_breakdown_dir，则遵循配置；否则目标统一收敛至 user_data/tasks
    p_kw = {"explicit": data_root, "cwd": host_proj}
    target_tasks_dir = os.path.join(user_data_dir, "tasks")
    try:
        cfg = paths.load_runtime_workflow_config(**p_kw)
        p_cfg = (cfg.get("paths") or {}).get("task_breakdown_dir")
        if p_cfg:
            if os.path.isabs(p_cfg):
                target_tasks_dir = os.path.abspath(p_cfg)
            else:
                target_tasks_dir = os.path.abspath(os.path.join(host_proj, p_cfg))
    except Exception:
        pass

    os.makedirs(target_tasks_dir, exist_ok=True)

    print(f"[CCP Migration] 开始执行存量任务数据迁移至固定 50 任务分卷...")
    print(f"[CCP Migration] 目标分卷目录: {target_tasks_dir}")

    all_raw_tasks: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_weekly_files: List[str] = []
    seen_legacy_files: List[str] = []

    # 1. 扫描存量 user_data/board.json
    board_json = os.path.join(user_data_dir, "board.json")
    if os.path.exists(board_json):
        try:
            with open(board_json, "r", encoding="utf-8") as f:
                content = json.load(f)
            if isinstance(content, list):
                print(f"[CCP Migration] 从 {board_json} 发现 {len(content)} 条存量任务记录")
                for item in content:
                    tid = item.get("id") or item.get("task_id")
                    if tid and tid not in seen_ids:
                        all_raw_tasks.append(item)
                        seen_ids.add(tid)
        except Exception as e:
            sys.stderr.write(f"[WARN] 读取 {board_json} 失败: {e}\n")

    # 2. 扫描目标目录 target_tasks_dir 中的存量周文件 YYYY-Www.yaml 或已有 chunk
    if os.path.exists(target_tasks_dir):
        for fname in sorted(os.listdir(target_tasks_dir)):
            fpath = os.path.join(target_tasks_dir, fname)
            if _WEEK_FILENAME_RE.match(fname):
                seen_weekly_files.append(fpath)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        w_data = yaml.safe_load(f)
                    if isinstance(w_data, dict) and isinstance(w_data.get("tasks"), list):
                        w_tasks = w_data.get("tasks", [])
                        print(f"[CCP Migration] 从周文件 {fname} 发现 {len(w_tasks)} 条任务记录")
                        for item in w_tasks:
                            tid = item.get("id") or item.get("task_id")
                            if tid and tid not in seen_ids:
                                all_raw_tasks.append(item)
                                seen_ids.add(tid)
                except Exception as e:
                    sys.stderr.write(f"[WARN] 读取周文件 {fpath} 失败: {e}\n")
            elif _CHUNK_FILENAME_RE.match(fname):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        c_data = yaml.safe_load(f)
                    if isinstance(c_data, dict) and isinstance(c_data.get("tasks"), list):
                        for item in c_data.get("tasks", []):
                            tid = item.get("id") or item.get("task_id")
                            if tid and tid not in seen_ids:
                                all_raw_tasks.append(item)
                                seen_ids.add(tid)
                except Exception as e:
                    sys.stderr.write(f"[WARN] 读取目标已有分卷 {fpath} 失败: {e}\n")

    # 2.5 扫描旧版文档路径 <docs_root>/D04-研发过程/D01-任务 中的存量分卷或周文件（若与目标目录不同）
    docs_dir = paths.docs_root(**p_kw)
    legacy_doc_tasks_dir = os.path.join(docs_dir, "D04-研发过程", "D01-任务")
    if os.path.abspath(legacy_doc_tasks_dir) != os.path.abspath(target_tasks_dir) and os.path.exists(legacy_doc_tasks_dir):
        for fname in sorted(os.listdir(legacy_doc_tasks_dir)):
            if _CHUNK_FILENAME_RE.match(fname) or _WEEK_FILENAME_RE.match(fname):
                fpath = os.path.join(legacy_doc_tasks_dir, fname)
                seen_legacy_files.append(fpath)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        c_data = yaml.safe_load(f)
                    if isinstance(c_data, dict) and isinstance(c_data.get("tasks"), list):
                        c_tasks = c_data.get("tasks", [])
                        print(f"[CCP Migration] 从旧版文档目录 {fname} 发现 {len(c_tasks)} 条历史任务")
                        for item in c_tasks:
                            tid = item.get("id") or item.get("task_id")
                            if tid and tid not in seen_ids:
                                all_raw_tasks.append(item)
                                seen_ids.add(tid)
                except Exception as e:
                    sys.stderr.write(f"[WARN] 读取旧版文档任务文件 {fpath} 失败: {e}\n")

    if not all_raw_tasks:
        print("[CCP Migration] 未发现待迁移的历史任务数据，工作区已处于干净状态。")
    else:
        print(f"[CCP Migration] 共汇聚 {len(all_raw_tasks)} 条历史任务，开始按序号归卷...")

        # 按 seq 排序
        def _get_seq(t: Dict[str, Any]) -> int:
            tid = str(t.get("id") or t.get("task_id") or "")
            m = _TASK_ID_RE.match(tid)
            if m:
                return int(m.group(1))
            return int(t.get("seq") or 99999)

        all_raw_tasks.sort(key=_get_seq)

        # 按 50 分卷分组
        chunks_map: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for idx, raw_t in enumerate(all_raw_tasks, start=1):
            norm_card = normalize_task_for_ccp(raw_t, default_seq=idx)
            c_range = get_chunk_range(norm_card["seq"])
            chunks_map.setdefault(c_range, []).append(norm_card)

        # 写入各分卷
        for (s_id, e_id), tasks_in_chunk in sorted(chunks_map.items()):
            chunk_filename = f"tasks_{s_id:04d}_{e_id:04d}.yaml"
            target_path = os.path.join(target_tasks_dir, chunk_filename)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 若目标分卷已存在，执行增量合并（依 ID 去重）
            existing_tasks = []
            if os.path.exists(target_path):
                try:
                    with open(target_path, "r", encoding="utf-8") as f:
                        old_data = yaml.safe_load(f)
                    if isinstance(old_data, dict) and isinstance(old_data.get("tasks"), list):
                        existing_tasks = old_data.get("tasks", [])
                except Exception:
                    existing_tasks = []

            existing_by_id = {str(t.get("id")): t for t in existing_tasks}
            for new_t in tasks_in_chunk:
                existing_by_id[str(new_t["id"])] = new_t

            merged_tasks = sorted(existing_by_id.values(), key=lambda x: int(x.get("seq") or 0))

            payload = {
                "metadata": {
                    "chunk_id": f"tasks_{s_id:04d}_{e_id:04d}",
                    "start_seq": s_id,
                    "end_seq": e_id,
                    "total_task_count": len(merged_tasks),
                    "active_task_count": len([t for t in merged_tasks if t.get("status") not in ("已验收", "已取消")]),
                    "updated_at": now_str,
                },
                "tasks": merged_tasks
            }

            if dry_run:
                print(f"[DRY-RUN] 将写入分卷 {chunk_filename} (含 {len(merged_tasks)} 个任务)")
            else:
                ok = atomic_write_yaml(target_path, payload)
                if ok:
                    print(f"[CCP Migration SUCCESS] 成功写入分卷 {chunk_filename} (含 {len(merged_tasks)} 个任务)")
                else:
                    sys.stderr.write(f"[CCP Migration FAILED] 写入分卷 {chunk_filename} 失败！\n")
                    return False

        # 归档历史周 YAML 文件，防止在 target_tasks_dir 中并存导致重复加载
        if not dry_run and seen_weekly_files:
            archive_dir = os.path.join(target_tasks_dir, "archive_weekly")
            os.makedirs(archive_dir, exist_ok=True)
            for wf in seen_weekly_files:
                if os.path.exists(wf):
                    dest_wf = os.path.join(archive_dir, os.path.basename(wf))
                    try:
                        shutil.move(wf, dest_wf)
                        print(f"[CCP Migration] 历史周文件 {os.path.basename(wf)} 已归档至: {dest_wf}")
                    except Exception as e:
                        sys.stderr.write(f"[WARN] 归档周文件 {wf} 失败: {e}\n")

        # 归档旧版文档目录下的任务文件，防止 paths.tasks_dir() 优先误读旧目录
        if not dry_run and seen_legacy_files:
            legacy_archive = os.path.join(legacy_doc_tasks_dir, "archive_migrated")
            os.makedirs(legacy_archive, exist_ok=True)
            for lf in seen_legacy_files:
                if os.path.exists(lf):
                    dest_lf = os.path.join(legacy_archive, os.path.basename(lf))
                    try:
                        shutil.move(lf, dest_lf)
                        print(f"[CCP Migration] 旧版文档任务文件 {os.path.basename(lf)} 已归档至: {dest_lf}")
                    except Exception as e:
                        sys.stderr.write(f"[WARN] 归档旧版任务文件 {lf} 失败: {e}\n")

        # 备份并安全移走历史 board.json（重命名防止双写裂脑）
        if not dry_run and os.path.exists(board_json):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak_path = f"{board_json}.bak.{ts}"
            try:
                shutil.move(board_json, bak_path)
                print(f"[CCP Migration] 历史 board.json 已备份并安全移走至: {bak_path}")
            except Exception as e:
                sys.stderr.write(f"[WARN] 备份/移走 board.json 失败: {e}\n")

    # 3. 动态解析并升级真实生效的 workflow.config.yaml 的 storage_mode 为 chunked
    active_cfg = paths.resolve_runtime_config(cwd=project_root) if project_root else paths.resolve_runtime_config()
    cfg_targets = []
    if os.path.isfile(active_cfg):
        cfg_targets.append(active_cfg)
    user_cfg = os.path.join(user_data_dir, "workflow.config.yaml")
    if user_cfg not in cfg_targets and os.path.isfile(user_cfg):
        cfg_targets.append(user_cfg)

    for cp in cfg_targets:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    cfg_data = yaml.safe_load(f)
                if isinstance(cfg_data, dict) and "board" in cfg_data:
                    current_mode = cfg_data["board"].get("storage_mode")
                    if current_mode != "chunked":
                        cfg_data["board"]["storage_mode"] = "chunked"
                        if not dry_run:
                            with open(cp, "w", encoding="utf-8") as f:
                                yaml.safe_dump(cfg_data, f, allow_unicode=True, sort_keys=False, indent=2)
                            print(f"[CCP Migration SUCCESS] 已升级配置 {cp} 为 storage_mode: chunked")
                        else:
                            print(f"[DRY-RUN] 将升级配置 {cp} 为 storage_mode: chunked")
            except Exception as e:
                sys.stderr.write(f"[WARN] 升级配置文件 {cp} 失败: {e}\n")

    print("[CCP Migration COMPLETE] 存量数据已完成向固定 50 任务分卷迁移与升级！")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="存量看板数据平滑迁移至 50 任务分卷 (CCP V2.0)")
    parser.add_argument("--project-root", default=None, help="宿主项目根路径")
    parser.add_argument("--dry-run", action="store_true", help="演练模式，不物理覆写文件")
    args = parser.parse_args()

    success = migrate_to_chunked_storage(project_root=args.project_root, dry_run=args.dry_run)
    sys.exit(0 if success else 1)
