#!/usr/bin/env python3
"""
paths.py · 数据根解析与路径派生（代码/数据分离的唯一事实源）

职责：
- 区分 SKILL_ROOT（只读技能代码：scripts/kanban/templates/references/rules/config 模板）
  与 DATA_ROOT（按项目隔离的运行数据：user_data/、锁文件）
- docs/ 是项目交付物而非 skill 私有数据 → 恒定锚定项目根，不随 data_root 派生

新布局（.yy-flow 全家桶）：
    <project>/
    ├── .yy-flow/            ← 工具私有根（可整体 gitignore）
    │   ├── skill/           ← 技能代码（degit/tarball 安装于此）
    │   └── user_data/       ← board/审计/锁（数据与 skill 同根，升级删 skill/ 不伤数据）
    ├── docs/                ← 项目交付文档（留项目根，提交 git，行业惯例位）
    └── .claude/skills/yy-flow -> ../.yy-flow/skill

data_root 优先级（高 → 低）：
1. 显式参数（--project-root CLI 透传）
2. 环境变量 YY_FLOW_PROJECT_ROOT
3. .yy-flow 布局：skill 位于 <X>/.yy-flow/skill → data_root = <X>/.yy-flow
   （skill 自定位推导，不依赖 CWD——消灭"在错误目录执行、数据落错项目"）
4. legacy 判定：<skill_root>/user_data/board.json 存在 → skill_root
   （存量 per-project 安装零迁移；收紧为要求 board.json 存在，目录误建不触发）
5. CWD（宿主项目根兜底）

误判的失败模式是"数据落错目录"（可发现可迁移），绝不会跨项目串数据。
"""

import os

_ENV_PROJECT_ROOT = "YY_FLOW_PROJECT_ROOT"

_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


def skill_root(env=None) -> str:
    """技能代码根目录（本文件所在 scripts/ 的上一级，支持符号软链接解引用）"""
    return os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))


def _yyflow_data_root() -> "str | None":
    """新布局判定：skill 位于 <X>/.yy-flow/skill → 数据根为 <X>/.yy-flow。"""
    parent = os.path.dirname(skill_root())
    if os.path.basename(parent) == ".yy-flow":
        return parent
    return None


def _legacy_data_root(env) -> "str | None":
    """legacy per-project 安装判定：skill 拷贝内含 user_data/board.json。
    .yy-flow-shared 标记（install_global 写入）一票否决——共享正本绝不当数据根。"""
    root = skill_root()
    if os.path.isfile(os.path.join(root, ".yy-flow-shared")):
        return None
    legacy_board = os.path.join(root, "user_data", "board.json")
    if os.path.isfile(legacy_board):
        return root
    return None


def project_root(explicit=None, env=None, cwd=None) -> str:
    """项目根目录（docs/ 与宿主标识的锚定点）。

    .yy-flow 布局下 = data_root 的上一级；legacy/共享安装下退回 data_root 本身
    （此时 skill 内数据与项目根同处，docs 就在 data_root 下）。
    """
    env = os.environ if env is None else env
    cwd = os.getcwd() if cwd is None else cwd
    dr = resolve_data_root(explicit=explicit, env=env, cwd=cwd)
    if os.path.basename(dr) == ".yy-flow":
        return os.path.dirname(dr)
    return dr


def resolve_data_root(explicit=None, env=None, cwd=None) -> str:
    """解析数据根目录。参数均可注入以便测试（不依赖进程级 env/cwd）。"""
    env = os.environ if env is None else env
    cwd = os.getcwd() if cwd is None else cwd

    # 1. 显式参数
    if explicit:
        return os.path.abspath(explicit)

    # 2. 环境变量
    env_root = env.get(_ENV_PROJECT_ROOT, "").strip()
    if env_root:
        return os.path.abspath(env_root)

    # 3. .yy-flow 布局：skill 位于 <X>/.yy-flow/skill → <X>/.yy-flow（自定位，不依赖 CWD）
    yyflow = _yyflow_data_root()
    if yyflow:
        return yyflow

    # 4. legacy per-project 安装（数据在 skill 拷贝内）
    legacy = _legacy_data_root(env)
    if legacy:
        return legacy

    # 5. CWD（宿主项目根兜底）
    return os.path.abspath(cwd)


def user_data_dir(**kw) -> str:
    return os.path.join(resolve_data_root(**kw), "user_data")


def locks_dir(**kw) -> str:
    return os.path.join(user_data_dir(**kw), "locks")


def docs_root(**kw) -> str:
    """项目交付文档根：恒定项目根下（交付物不进工具私有目录）。"""
    return os.path.join(project_root(**kw), "docs")


def tasks_dir(**kw) -> str:
    """研发任务卡周口径存储根目录（docs/D04-研发过程/D01-任务，严格符合 3 级深度红线）"""
    path = os.path.join(docs_root(**kw), "D04-研发过程", "D01-任务")
    os.makedirs(path, exist_ok=True)
    return path


def runtime_config_path(**kw) -> str:
    """宿主运行态工作流配置路径（init step 4 生成）"""
    return os.path.join(user_data_dir(**kw), "workflow.config.yaml")


def arch_config_path(**kw) -> str:
    """宿主运行态架构配置路径（auto_scan_stack 生成）"""
    return os.path.join(user_data_dir(**kw), "project_architecture.config.yaml")


def audit_logs_dir(env=None, **kw) -> str:
    """审计日志目录；AUDIT_LOG_DIR 环境变量仍为最高优先覆盖（既有行为保留）"""
    env = os.environ if env is None else env
    override = env.get("AUDIT_LOG_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    # env 需同时用于 data_root 解析（注入测试时不能回退到真实 os.environ）
    return os.path.join(user_data_dir(env=env, **kw), "logs")


def kanban_runtime_file(**kw) -> str:
    return os.path.join(user_data_dir(**kw), "kanban_server.json")


def legacy_config_path() -> str:
    """旧版配置位置（skill 拷贝内，仅作解析链兜底与迁移提示）"""
    return os.path.join(skill_root(), "config", "workflow.config.yaml")


def resolve_runtime_config(explicit=None, env=None, cwd=None) -> str:
    """解析生效的 workflow 配置文件路径。

    链：显式 --config > <data_root>/user_data/workflow.config.yaml（存在即用）
        > <skill_root>/config/workflow.config.yaml（legacy，存在即用）
        > <data_root>/user_data/workflow.config.yaml（Fail-Closed 指向 init）
    """
    if explicit:
        return os.path.abspath(explicit)

    data_root = resolve_data_root(env=env, cwd=cwd)
    env = os.environ if env is None else env
    cwd = os.getcwd() if cwd is None else cwd
    # 显式路径已处理；此处 data_root 用注入参数重新派生 user_data 路径
    candidate_user = os.path.join(data_root, "user_data", "workflow.config.yaml")
    if os.path.isfile(candidate_user):
        return candidate_user

    candidate_legacy = legacy_config_path()
    if os.path.isfile(candidate_legacy):
        return candidate_legacy

    return candidate_user  # 不存在 → 返回目标位置，由调用方 Fail-Closed 提示 init


if __name__ == "__main__":
    # CLI 输出 data_root，供 init_skill.sh 等外壳脚本解析数据根
    import argparse
    ap = argparse.ArgumentParser(description="数据根解析（与各脚本内部同链）")
    ap.add_argument("--project-root", default=None, help="显式数据根（优先级最高）")
    args = ap.parse_args()
    print(resolve_data_root(explicit=args.project_root))
