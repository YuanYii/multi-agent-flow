"""
修复 ① 回归测试:验证 6 个 references/*.md 规约文档已同步 8 角色(FRONTEND 出现)。

背景:之前 6 个 references 文档停留在 7 角色时代(无 FRONTEND),
     规约与代码不同步,前端任务无规约可查。本测试在合并时阻断回退。
"""
import os
import re
import pytest

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
REFERENCES_DIR = os.path.join(PROJECT_ROOT, "references")

REQUIRED_REFS = [
    "01-AI-Team-Workflow-Index.md",
    "02-State-Flow-Rules.md",
    "03-Anti-Error-Mechanism.md",
    "04-Git-Workflow-Spec.md",
    "05-Document-Management-Spec.md",
    "06-Inter-Agent-Handover-Protocol.md",
]


@pytest.mark.parametrize("filename", REQUIRED_REFS)
def test_references_file_exists(filename):
    """所有 6 个 references 规约文档必须存在"""
    assert os.path.exists(os.path.join(REFERENCES_DIR, filename)), f"references/{filename} 缺失"


@pytest.mark.parametrize("filename", REQUIRED_REFS)
def test_references_mentions_frontend(filename):
    """每个 references 规约文档必须显式提到 FRONTEND 或 前端 (大小写不敏感)"""
    path = os.path.join(REFERENCES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    has_frontend = bool(re.search(r"FRONTEND|前端", content, re.IGNORECASE))
    assert has_frontend, (
        f"references/{filename} 未提及 FRONTEND 角色。"
        f"规约与代码不同步会导致前端任务无规可依。请补全 8 角色同步。"
    )


def test_main_index_uses_8_roles_not_7():
    """01 主索引必须使用 8 角色而非 7 角色"""
    with open(os.path.join(REFERENCES_DIR, "01-AI-Team-Workflow-Index.md"), "r", encoding="utf-8") as f:
        content = f.read()
    assert "8 大角色" in content, "01 主索引未声明 8 大角色"
    assert "7 大角色" not in content, "01 主索引仍残留 7 大角色表述(应已升级)"


def test_state_flow_handles_frontend_rollback():
    """02 状态流转规则的打回表必须包含前端任务场景"""
    with open(os.path.join(REFERENCES_DIR, "02-State-Flow-Rules.md"), "r", encoding="utf-8") as f:
        content = f.read()
    # 检查打回表第一行(审查打回)已包含 FRONTEND
    assert re.search(r"审查.*?(A.*?前端|FRONTEND)", content, re.DOTALL), (
        "02 打回表第一行未覆盖前端任务打回场景"
    )


def test_anti_error_uses_8_actors():
    """03 防错机制必须声明 8 个角色(不能再说 7 个)"""
    with open(os.path.join(REFERENCES_DIR, "03-Anti-Error-Mechanism.md"), "r", encoding="utf-8") as f:
        content = f.read()
    # 旧表述: "所有 7 个角色"
    assert "所有 7 个角色" not in content, "03 防错机制仍写'所有 7 个角色'(应已升级为 8 个)"
    assert "所有 8 个角色" in content or "8 个角色" in content, "03 防错机制未升级为 8 角色"


def test_anti_error_documents_delegation_cli():
    """03 防错机制代行协议一节必须明确 CLI --delegated-by 强制门控(防回退)"""
    with open(os.path.join(REFERENCES_DIR, "03-Anti-Error-Mechanism.md"), "r", encoding="utf-8") as f:
        content = f.read()
    assert "--delegated-by" in content, "03 防错机制未文档化 --delegated-by CLI 强制门控"
    assert "DELEGATION_ALLOW_MATRIX" in content, "03 防错机制未指向 validate_transition.py 的代行白名单"


def test_handover_protocol_uses_8_actors():
    """06 交接协议必须声明 8 大角色(不能再说 7 大)"""
    with open(os.path.join(REFERENCES_DIR, "06-Inter-Agent-Handover-Protocol.md"), "r", encoding="utf-8") as f:
        content = f.read()
    assert "8 大角色" in content, "06 交接协议未声明 8 大角色"
    assert "7 大角色" not in content, "06 交接协议仍残留 7 大角色表述"


def test_handover_protocol_frontend_in_matrix():
    """06 交接协议动作矩阵必须包含 FRONTEND 提交/打回行"""
    with open(os.path.join(REFERENCES_DIR, "06-Inter-Agent-Handover-Protocol.md"), "r", encoding="utf-8") as f:
        content = f.read()
    # DEV / FRONTEND 合并行
    assert "DEV / FRONTEND" in content or "DEV/FRONTEND" in content, (
        "06 交接协议动作矩阵未把 FRONTEND 接入 DEV 行(应合并写为 'DEV / FRONTEND')"
    )
