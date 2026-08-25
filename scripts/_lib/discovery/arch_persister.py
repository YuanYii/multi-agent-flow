"""
项目技术架构与专家技术栈安全定版持久化模块
"""
import os
import sys
import json
import yaml
import subprocess
from typing import Any, Dict, List

import paths as _paths
from _lib.core.tech_capability_expander import expand_expert_capabilities


def clean_list(val: Any) -> List[str]:
    """统一将逗号分隔字符串或列表转换为干净的非空字符串列表"""
    if isinstance(val, list):
        out = []
        for v in val:
            if isinstance(v, dict):
                out.append(str(v.get("name", "")))
            elif v:
                out.append(str(v).strip())
        return [x for x in out if x]
    if isinstance(val, str):
        return [x.strip() for x in val.replace("，", ",").split(",") if x.strip()]
    return []


def validate_schema(data: dict) -> bool:
    """基于 project_architecture.schema.json 校验数据格式"""
    schema_path = os.path.join(_paths.skill_root(), "config", "project_architecture.schema.json")
    if not os.path.exists(schema_path):
        return True
    try:
        import jsonschema
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(instance=data, schema=schema)
        return True
    except ImportError:
        req = ["project", "tech_stack", "architecture_overview"]
        for k in req:
            if k not in data:
                sys.stderr.write(f"[FAIL-CLOSED ERROR] 缺少必需根字段: {k}\n")
                return False
        return True
    except Exception as e:
        sys.stderr.write(f"[FAIL-CLOSED ERROR] Schema 校验失败: {e}\n")
        return False


def save_architecture_config(arch_dict: dict) -> bool:
    """持久化架构配置并执行 Fail-Closed 断言"""
    config_path = _paths.arch_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # 1. 自动迁移与规范化
    if "meta" not in arch_dict:
        arch_dict["meta"] = {}
    arch_dict["meta"]["initialized"] = True

    tech_stack = arch_dict.get("tech_stack", {})
    object_list_fields = ["languages", "databases_and_storage", "frameworks", "tools_and_services"]
    for fld in object_list_fields:
        if fld in tech_stack:
            items = tech_stack[fld]
            if isinstance(items, list):
                norm_items = []
                for item in items:
                    if isinstance(item, str):
                        norm_items.append({"name": item})
                    elif isinstance(item, dict) and "name" in item:
                        norm_items.append(item)
                tech_stack[fld] = norm_items

    # 2. 自动派生 3~5 项专家能力并回填
    expert_caps = expand_expert_capabilities(arch_dict)
    if "tech_stack" not in arch_dict:
        arch_dict["tech_stack"] = {}
    arch_dict["tech_stack"]["expert_capabilities"] = expert_caps

    # 3. Schema 校验
    if not validate_schema(arch_dict):
        sys.stderr.write("[FAIL-CLOSED ERROR] 架构数据不满足规范，阻断写入！\n")
        return False

    # 4. 物理原子写入
    tmp_path = config_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(arch_dict, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp_path, config_path)
    print(f"[SUCCESS]  架构配置已安全落盘: {config_path}")

    # 5. 联动重导出 Subagent
    export_script = os.path.join(_paths.skill_root(), "scripts", "verify_and_export_agents.py")
    res = subprocess.run([sys.executable, export_script, "--target-project-dir", _paths.project_root()], capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"[FAIL-CLOSED ERROR] Subagent 重新导出失败: {res.stderr}\n")
        return False
    print("[SUCCESS]  专家 Subagent 已携专属能力完成刷新导出。")

    # 6. Fail-Closed 物理断言
    sample_agents = [
        os.path.join(_paths.project_root(), ".agents", "agents", "flow-dev", "agent.md"),
        os.path.join(_paths.project_root(), ".agents", "agents", "flow-frontend", "agent.md"),
    ]
    verified = False
    for sa in sample_agents:
        if os.path.exists(sa):
            with open(sa, "r", encoding="utf-8") as f:
                c = f.read()
            if "### 专属技术栈能力" in c:
                verified = True
                break
    if not verified and any(os.path.exists(sa) for sa in sample_agents):
        sys.stderr.write("[FAIL-CLOSED ERROR] 导出的专家 Subagent 缺少注入的专属技术栈能力，落盘被阻断！\n")
        return False

    return True
