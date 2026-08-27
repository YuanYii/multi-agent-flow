#!/usr/bin/env python3
"""
三大底层设计盲区修复回归测试 (Blind Spot Fixes Regression Tests)
覆盖批判者视角挖掘的 3 个缺陷的修复验证:
  1. secrets_checker 等号赋值密钥漏扫 → 等号赋值模式 + 误报免疫
  2. heartbeat 孤儿检测 48h 窗口外历史文件永久隐形 → ORPHAN_HISTORICAL 一次性兜底
  3. heartbeat 状态入态时间提取容错性不足 → 动作词/箭头/无括号时间戳通用兜底
"""
import os
import sys
import time
import shutil
import tempfile
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from _lib.gates.secrets_checker import scan_file
from _lib.metrics.heartbeat_engine import run_heartbeat, _get_status_entry_time


# ============ 缺陷 1: 等号赋值密钥扫描 ============

def _scan_content(content: str) -> list:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(content)
        path = f.name
    try:
        return scan_file(path)
    finally:
        os.unlink(path)


@pytest.mark.parametrize("content", [
    'APP_SECRET = "abcdefghijklmnopqrst1234"\n',
    'const appSecret = "abcdefghijklmnopqrst1234";\n',
    'API_SECRET = "sk-abc123def456ghi789jkl012"\n',
    'feishu:\n  app_secret: "abcdefghijklmnopqrst1234"\n',
])
def test_secret_assignment_is_detected(content):
    """等号赋值与冒号风格的硬编码密钥均应被拦截"""
    assert _scan_content(content), f"硬编码密钥未被拦截: {content!r}"


@pytest.mark.parametrize("content", [
    'logger.info("secret loaded from env")\n',
    'SECRET_MODE = "debug"\n',
    'SECRET = os.environ.get("SECRET")\n',
    'RETRY_COUNT = 123456789012345\n',
    'secret: "${FEISHU_APP_SECRET}"\n',
])
def test_benign_content_not_flagged(content):
    """良性内容不应误报"""
    assert not _scan_content(content), f"误报: {content!r}"


# ============ 缺陷 2: 孤儿检测历史窗口兜底 ============

class NullAdapter:
    def list_records(self, limit=1000):
        return []


def test_orphan_historical_files_are_reported_once():
    """48h 窗口外的存量孤儿文档应触发一次性 ORPHAN_HISTORICAL 兜底告警"""
    tmp = tempfile.mkdtemp()
    try:
        d = os.path.join(tmp, "docs", "D04-研发过程", "D02-报告")
        os.makedirs(d)
        old_t = time.time() - 72 * 3600
        fp = os.path.join(d, "无人认领的历史设计文档.md")
        open(fp, "w").write("x")
        os.utime(fp, (old_t, old_t))
        os.utime(d, (old_t, old_t))

        result = run_heartbeat(NullAdapter(), doc_dirs_override=[d])
        hist = [a for a in result["alerts"] if a["code"] == "ORPHAN_HISTORICAL"]
        assert any("历史设计文档" in a["message"] for a in hist), "72h 旧孤儿未被兜底检出"
        assert all(a["severity"] == "info" for a in hist), "历史孤儿应为 info 级"

        # 哨兵落盘后第二次巡检应静默（一次性告警）
        result2 = run_heartbeat(NullAdapter(), doc_dirs_override=[d])
        hist2 = [a for a in result2["alerts"] if a["code"] == "ORPHAN_HISTORICAL"]
        assert not hist2, "历史孤儿告警应仅报告一次"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_orphan_recent_files_still_warning():
    """48h 窗口内的新孤儿仍为 warning 级 ORPHAN_OUTPUT（原能力保持）"""
    tmp = tempfile.mkdtemp()
    try:
        d = os.path.join(tmp, "docs", "D04-研发过程", "D02-报告")
        os.makedirs(d)
        fp = os.path.join(d, "新孤儿文档.md")
        open(fp, "w").write("x")
        result = run_heartbeat(NullAdapter(), doc_dirs_override=[d])
        assert any(a["code"] == "ORPHAN_OUTPUT" and "新孤儿文档" in a["message"]
                   for a in result["alerts"]), "近窗孤儿应维持 warning 级"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============ 缺陷 3: 状态入态时间提取容错 ============

FALLBACK_START = "2026-08-20 08:00"


FALLBACK_DT = "08-20 08:00"  # start_date 兜底值

@pytest.mark.parametrize("process,expect", [
    # 标准格式（原能力保持）
    ("[T0001-N02] [2026-08-25 09:00] 状态: 【审查中】 -> 【测试中】", "08-25 09:00"),
    ("[T0001-N02] [2026-08-25 09:30] 状态由【审查中】更新至【测试中】", "08-25 09:30"),
    ("[T0001-N01] [2026-08-24 08:00] 初始状态【待开始】", FALLBACK_DT),  # 目标状态不存在→回退 start_date
    ("[2026-08-01 10:00] [待开始] 备注", FALLBACK_DT),                   # 极简历史目标不符→回退 start_date
    # 修复新增容错
    ("[2026-08-25 10:00] [手动追加] 状态更新至【测试中】", "08-25 10:00"),
    ("2026-08-25 11:00 外部脚本 状态更新至【测试中】", "08-25 11:00"),
    ("2026-08-25 12:00 外部工具 状态变更为【测试中】", "08-25 12:00"),
    ("2026-08-25 14:00 管理员置为【测试中】", "08-25 14:00"),
    ("[2026-08-25 13:00] [同步] 【审查中】->【测试中】", "08-25 13:00"),
    ("[2026-08-25 15:00] [sync] 状态: 【审查中】=>【测试中】", "08-25 15:00"),
    # 多节点倒序取最新入态
    ("[T0001-N01] [2026-08-21 08:00] 初始状态【测试中】\n"
     "[T0001-N02] [2026-08-22 09:00] 状态: 【测试中】 -> 【审查中】\n"
     "[T0001-N03] [2026-08-23 10:00] 状态: 【审查中】 -> 【测试中】", "08-23 10:00"),
])
def test_status_entry_time_extraction(process, expect):
    """标准与外部追加格式均应精确提取入态时间；目标不存在时回退 start_date"""
    dt = _get_status_entry_time({"process": process, "start_date": FALLBACK_START}, "测试中")
    got = dt.strftime("%m-%d %H:%M") if dt else None
    assert got == expect, f"提取结果 {got} != 期望 {expect} (process={process!r})"


@pytest.mark.parametrize("process,status", [
    ("这里讨论了测试中的注意事项与边界", "测试中"),
    ("[T0001-N03] [2026-08-26 09:00] 状态: 【测试中】 -> 【已完成】 交付说明中提到审查中的注意事项", "审查中"),
])
def test_descriptive_text_not_misparsed(process, status):
    """无时间戳/无动作词的说明性文字不应被误解析为状态节点；
    函数契约：未命中节点时回退 start_date，故免疫判据 = 结果恰为兜底时间而非正文捏造时间"""
    dt = _get_status_entry_time({"process": process, "start_date": FALLBACK_START}, status)
    got = dt.strftime("%m-%d %H:%M") if dt else None
    assert got == FALLBACK_DT, f"说明性文字被误判为状态节点: 得到 {got} (process={process!r})"
