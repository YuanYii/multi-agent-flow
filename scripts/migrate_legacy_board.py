#!/usr/bin/env python3
r"""
存量看板数据平滑迁移工具 (Legacy Board to Weekly Storage Migrator)

职责：
1. 探测 user_data/board.json 中的历史任务卡片；
2. 自动创建物理备份 board.json.bak.<timestamp>；
3. 根据任务 start_date 精准分流至各个自然周 YYYY-Www.yaml；
4. 补齐 target 与 acceptance_criteria 结构化字段，净化流程节点；
5. 计算周生命周期，将全终态历史周自动标记冷封 (is_sealed = true)；
6. 提取最大序列号重建本地派生索引 (.tasks_index.json)；
7. 自动升级 user_data/workflow.config.yaml 为 storage_mode: weekly；
8. 原 board.json 安全置为 .migrated 标记，实现初始化绝对幂等。
"""
import os
import sys
import json
import yaml
import time
import shutil
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import paths

_TASK_ID_RE = re.compile(r"^T(\d+)$")
_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def resolve_week_cycle(card: Dict[str, Any], fallback_week: str) -> str:
    """根据任务日期字段智能解析出自然周 YYYY-Www"""
    date_candidates = [
        card.get("start_date"),
        card.get("created_date"),
        card.get("end_date"),
    ]
    proc = str(card.get("process") or "")
    m_proc = _DATE_RE.search(proc)
    if m_proc:
        date_candidates.append(m_proc.group(0))

    for d_str in date_candidates:
        if not d_str:
            continue
        m = _DATE_RE.search(str(d_str))
        if m:
            try:
                y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(y, mth, d)
                iso_y, iso_w, _ = dt.isocalendar()
                return f"{iso_y}-W{iso_w:02d}"
            except Exception:
                continue
    return fallback_week


def get_current_week_info() -> Tuple[str, str, str]:
    now = datetime.now()
    y, w, _ = now.isocalendar()
    curr_week = f"{y}-W{w:02d}"
    today_str = now.strftime("%Y-%m-%d")
    return curr_week, today_str, today_str


def atomic_write_yaml(target_yaml: str, payload_data: dict) -> bool:
    """临时文件 + os.replace 原子写入 YAML 文件"""
    target_dir = os.path.dirname(os.path.abspath(target_yaml))
    os.makedirs(target_dir, exist_ok=True)
    tmp_path = target_yaml + f".tmp.{os.getpid()}_{int(time.time()*1000)}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload_data, f, allow_unicode=True, sort_keys=False, indent=2)
        os.replace(tmp_path, target_yaml)
        return True
    except Exception as e:
        sys.stderr.write(f"[ERROR] 写入周文件失败 {target_yaml}: {e}\n")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def migrate_board_data(project_root: Optional[str] = None) -> bool:
    """执行历史看板数据迁移的主函数"""
    data_root = paths.resolve_data_root(explicit=project_root) if project_root else paths.resolve_data_root()
    user_data_dir = os.path.join(data_root, "user_data")
    board_json = os.path.join(user_data_dir, "board.json")
    migrated_marker = os.path.join(user_data_dir, "board.json.migrated")

    # 1. 静默预检与幂等保障
    if os.path.exists(migrated_marker):
        print(f"[MIGRATE]  检测到已完成历史迁移标记 ({migrated_marker})，跳过迁移。")
        return True

    if not os.path.exists(board_json):
        return True

    try:
        with open(board_json, "r", encoding="utf-8") as f:
            raw_cards = json.load(f)
    except Exception as e:
        sys.stderr.write(f"[WARN] 读取存量 board.json 失败: {e}\n")
        return True

    if not isinstance(raw_cards, list) or len(raw_cards) == 0:
        return True

    print(f"==============================================================================")
    print(f"[MIGRATE]  检测到存量单体看板工单 ({board_json})，共计 {len(raw_cards)} 张历史卡片。")
    print(f"[MIGRATE]  开始执行向自然周存储 (docs/D04-研发过程/D01-任务/) 平滑无损迁移...")
    print(f"==============================================================================")

    # 2. 物理不可逆备份
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(user_data_dir, f"board.json.bak.{ts}")
    shutil.copy2(board_json, backup_file)
    print(f"  [BACKUP]   历史数据已安全备份至: {backup_file}")

    # 3. 按自然周智能归集分流
    curr_week, cur_start, cur_end = get_current_week_info()
    weeks_map: Dict[str, List[Dict[str, Any]]] = {}

    for idx, raw_card in enumerate(raw_cards, start=1):
        c = dict(raw_card)
        w_cycle = resolve_week_cycle(c, fallback_week=curr_week)
        
        # 补全与净化新契约字段
        c["target"] = str(c.get("target") or "").strip()
        raw_crit = c.get("acceptance_criteria")
        if isinstance(raw_crit, list):
            c["acceptance_criteria"] = raw_crit
        elif isinstance(raw_crit, str) and raw_crit.strip():
            c["acceptance_criteria"] = [raw_crit.strip()]
        else:
            c["acceptance_criteria"] = []
        
        # 净化 process 轨迹
        proc = str(c.get("process") or "").strip()
        if proc.startswith("None\n"):
            proc = proc[5:].strip()
        elif proc in ("None", "null"):
            proc = ""
        c["process"] = proc
        
        # 基础字段格式规整
        c["stage"] = c.get("stage") or "开发阶段"
        c["wp"] = c.get("wp") or "WP-默认"
        c["wbs"] = c.get("wbs") or ""
        c["pretask"] = c.get("pretask") or ""
        c["assignee"] = c.get("assignee") or "李开发"
        c["handler"] = c.get("handler") or c.get("assignee") or "李开发"
        c["status"] = c.get("status") or "待开始"
        c["priority"] = c.get("priority") or "中"
        c["seq"] = idx

        if w_cycle not in weeks_map:
            weeks_map[w_cycle] = []
        weeks_map[w_cycle].append(c)

    # 4. 写入周 YAML 文件
    tasks_dir = paths.tasks_dir(explicit=project_root) if project_root else paths.tasks_dir()
    os.makedirs(tasks_dir, exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sealed_count = 0
    active_week_count = 0

    for w_cycle, t_list in sorted(weeks_map.items()):
        yaml_path = os.path.join(tasks_dir, f"{w_cycle}.yaml")
        
        active_cnt = len([t for t in t_list if t.get("status") not in ("已验收", "已取消")])
        is_sealed = (len(t_list) > 0 and active_cnt == 0)

        # 推导周时间范围
        earliest_date = ""
        for t in t_list:
            sd = str(t.get("start_date") or "")[:10]
            if sd and (not earliest_date or sd < earliest_date):
                earliest_date = sd

        meta = {
            "week_cycle": w_cycle,
            "start_date": earliest_date or cur_start,
            "end_date": earliest_date or cur_end,
            "is_sealed": is_sealed,
            "updated_at": now_str,
            "total_task_count": len(t_list),
            "active_task_count": active_cnt
        }

        payload = {
            "metadata": meta,
            "tasks": t_list
        }

        if not atomic_write_yaml(yaml_path, payload):
            sys.stderr.write(f"[FATAL] 迁移周文件 {yaml_path} 失败，终止迁移！\n")
            return False

        if is_sealed:
            sealed_count += 1
            status_tag = "全部已验收 -> 自动冷封"
        else:
            active_week_count += 1
            status_tag = f"含 {active_cnt} 项活跃任务 -> 保持活跃"

        print(f"  - [{w_cycle}.yaml] 归集 {len(t_list)} 张任务 ({status_tag})")

    # 5. 重建本地派生倒排索引 (.tasks_index.json)
    from _lib.boards.weekly_board_adapter import WeeklyBoardAdapter
    adapter = WeeklyBoardAdapter(tasks_dir=tasks_dir)
    idx_data = adapter._rebuild_index()
    print(f"  [INDEX]    本地派生索引重建完毕，最大序号识别为: T{idx_data.get('max_seq', 0):04d}")

    # 6. 自动升级宿主项目 workflow.config.yaml 配置
    runtime_config = paths.resolve_runtime_config(explicit=project_root) if project_root else paths.resolve_runtime_config()
    if os.path.exists(runtime_config):
        try:
            with open(runtime_config, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            if "board" not in cfg or not isinstance(cfg["board"], dict):
                cfg["board"] = {}
            
            cfg["board"]["storage_mode"] = "weekly"
            if "fields" not in cfg["board"] or not isinstance(cfg["board"]["fields"], dict):
                cfg["board"]["fields"] = {}
            cfg["board"]["fields"].setdefault("target", "target")
            cfg["board"]["fields"].setdefault("acceptance_criteria", "acceptance_criteria")

            with open(runtime_config, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False, indent=2)
            print(f"  [CONFIG]   宿主工作流配置已自动升级为 storage_mode: weekly ({runtime_config})")
        except Exception as e:
            sys.stderr.write(f"[WARN] 升级工作流配置失败: {e}\n")

    # 7. 标记原 board.json 为归档态，并留存幂等标记
    shutil.move(board_json, migrated_marker)
    with open(board_json, "w", encoding="utf-8") as f:
        f.write("[]")

    print(f"==============================================================================")
    print(f"[SUCCESS]  存量单体工单平滑迁移至周口径完成！")
    print(f"  任务总计: {len(raw_cards)} 张 | 划分自然周: {len(weeks_map)} 个 | 冷封周: {sealed_count} 个")
    print(f"  周任务物理存储路径: {tasks_dir}")
    print(f"==============================================================================")
    return True


if __name__ == "__main__":
    ok = migrate_board_data()
    sys.exit(0 if ok else 1)
