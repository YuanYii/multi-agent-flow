#!/usr/bin/env python3
"""
Gate 1: 静态 Schema 与双轨一致性门禁检查器 (Static Consistency Gate Checker)

本脚本负责执行全量定版发布门禁中的 Gate 1 校验：
1. 静态 Schema 与配置语法校验 (YAML/JSON 语法与 JSON Schema 合规性)；
2. 枚举双轨一致性对账 (enums.py, enums.json, fields.json, 新旧双轨规约)；
3. 迁移脚本行为一致性与源码行尾符 (LF vs CRLF) 检测。

运行方式:
    python3 scripts/check_static_consistency.py
    python3 scripts/check_static_consistency.py --json
"""

import os
import sys
import json
import yaml
import argparse
from typing import List, Dict, Any, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import jsonschema
except ImportError:
    jsonschema = None


class StaticConsistencyChecker:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root
        self.violations: List[Dict[str, Any]] = []

    def add_violation(self, gate: str, file_path: str, message: str):
        self.violations.append({
            "gate": gate,
            "file": os.path.relpath(file_path, self.repo_root) if os.path.isabs(file_path) else file_path,
            "message": message,
        })

    def check_yaml_json_syntax(self) -> int:
        """检查 config/, agents/, templates/ 下所有 YAML 与 JSON 语法。"""
        checked_count = 0
        target_dirs = ["config", "agents", "templates"]
        for d in target_dirs:
            full_d = os.path.join(self.repo_root, d)
            if not os.path.exists(full_d):
                continue
            for root, _, files in os.walk(full_d):
                for f in files:
                    p = os.path.join(root, f)
                    if f.endswith((".yaml", ".yml")):
                        checked_count += 1
                        try:
                            with open(p, "r", encoding="utf-8") as fp:
                                yaml.safe_load(fp)
                        except Exception as e:
                            self.add_violation("Syntax", p, f"YAML 解析失败: {e}")
                    elif f.endswith(".json"):
                        checked_count += 1
                        try:
                            with open(p, "r", encoding="utf-8") as fp:
                                json.load(fp)
                        except Exception as e:
                            self.add_violation("Syntax", p, f"JSON 解析失败: {e}")
        return checked_count

    def check_schema_compliance(self) -> int:
        """检查核心配置文件与模板是否符合 JSON Schema 规范。"""
        if jsonschema is None:
            self.add_violation("Schema", "requirements.txt", "jsonschema 库未安装，无法执行 Schema 校验")
            return 0

        checked_count = 0
        schema_pairs = [
            ("config/config.schema.json", "config/workflow.config.template.yaml"),
            ("config/config.schema.json", "config/workflow.config.yaml"),
            ("config/project_architecture.schema.json", "config/project_architecture.template.yaml"),
        ]

        for s_rel, d_rel in schema_pairs:
            s_path = os.path.join(self.repo_root, s_rel)
            d_path = os.path.join(self.repo_root, d_rel)
            if not os.path.exists(s_path) or not os.path.exists(d_path):
                continue

            checked_count += 1
            try:
                with open(s_path, "r", encoding="utf-8") as s_fp:
                    schema_data = json.load(s_fp)
                with open(d_path, "r", encoding="utf-8") as d_fp:
                    data = yaml.safe_load(d_fp)
                jsonschema.validate(instance=data, schema=schema_data)
            except Exception as e:
                self.add_violation("Schema", d_path, f"违反 Schema {s_rel}: {e}")

        return checked_count

    def check_enums_and_fields_alignment(self) -> int:
        """校验前后端枚举与新旧双轨规约对齐。"""
        checked_count = 0
        try:
            import enums
            py_enums = enums.dump_enums_dict()
        except Exception as e:
            self.add_violation("Enums", "scripts/enums.py", f"导入 enums.py 失败: {e}")
            return 0

        enums_json_path = os.path.join(self.repo_root, "kanban/json/enums.json")
        if os.path.exists(enums_json_path):
            checked_count += 1
            try:
                with open(enums_json_path, "r", encoding="utf-8") as fp:
                    json_enums = json.load(fp)
                # 对齐 task_statuses
                py_statuses = py_enums.get("task_statuses", [])
                json_statuses = json_enums.get("task_statuses", [])
                if py_statuses != json_statuses:
                    self.add_violation(
                        "Enums",
                        enums_json_path,
                        f"task_statuses 枚举不一致: python={py_statuses} vs json={json_statuses}"
                    )
                # 对齐 roles
                py_roles = py_enums.get("roles", [])
                json_roles = json_enums.get("roles", [])
                if py_roles != json_roles:
                    self.add_violation(
                        "Enums",
                        enums_json_path,
                        f"roles 枚举不一致: python={py_roles} vs json={json_roles}"
                    )
            except Exception as e:
                self.add_violation("Enums", enums_json_path, f"比对 enums.json 失败: {e}")

        # 校验新旧双轨规范文档覆盖全部 9 个状态
        dual_track_docs = [
            "references/02-State-Flow-Rules.md",
            "references/03-engine/01-state_flow_rules.md",
        ]
        raw_statuses = py_enums.get("task_statuses", [])
        expected_statuses = [
            s["key"] if isinstance(s, dict) else s for s in raw_statuses
        ] if raw_statuses else [
            "待开始", "进行中", "审查中", "测试中", "已完成", "已验收", "已退回", "已阻塞", "已取消"
        ]
        for doc_rel in dual_track_docs:
            doc_path = os.path.join(self.repo_root, doc_rel)
            if os.path.exists(doc_path):
                checked_count += 1
                with open(doc_path, "r", encoding="utf-8") as fp:
                    content = fp.read()
                missing = [s for s in expected_statuses if s not in content]
                if missing:
                    self.add_violation(
                        "DualTrack",
                        doc_path,
                        f"双轨规约缺少对以下状态的定义: {', '.join(missing)}"
                    )

        return checked_count

    def check_migrations_and_line_endings(self) -> int:
        """校验平滑迁移入口与 Shell 换行符。"""
        checked_count = 0
        # 1. 迁移入口文件校验
        fwd_script = os.path.join(self.repo_root, "scripts/migrate_legacy_board.py")
        impl_script = os.path.join(self.repo_root, "scripts/migrations/migrate_legacy_board.py")
        if os.path.exists(fwd_script) and os.path.exists(impl_script):
            checked_count += 1
            with open(fwd_script, "r", encoding="utf-8") as fp:
                fwd_content = fp.read()
            if "migrate_legacy_board" not in fwd_content or "migrate_board_data" not in fwd_content:
                self.add_violation("Migration", fwd_script, "转发脚本未正确接入底层 migrate_legacy_board 实现")

        # 2. Shell 脚本 CRLF 换行符检查
        for root, _, files in os.walk(self.repo_root):
            if any(ign in root for ign in [".git", ".pytest_cache", ".venv", "node_modules"]):
                continue
            for f in files:
                if f.endswith(".sh"):
                    p = os.path.join(root, f)
                    checked_count += 1
                    try:
                        with open(p, "rb") as fp:
                            raw = fp.read()
                        if b"\r\n" in raw:
                            self.add_violation("Formatting", p, "发现 CRLF 换行符污染，必须统一为 LF 换行符")
                    except Exception as e:
                        self.add_violation("Formatting", p, f"读取失败: {e}")

        return checked_count

    def run_all(self) -> Dict[str, Any]:
        syntax_count = self.check_yaml_json_syntax()
        schema_count = self.check_schema_compliance()
        enums_count = self.check_enums_and_fields_alignment()
        infra_count = self.check_migrations_and_line_endings()

        passed = len(self.violations) == 0
        return {
            "passed": passed,
            "total_items_checked": syntax_count + schema_count + enums_count + infra_count,
            "violations_count": len(self.violations),
            "violations": self.violations,
        }


def main():
    parser = argparse.ArgumentParser(description="Gate 1 静态 Schema 与双轨一致性检查器")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    args = parser.parse_args()

    checker = StaticConsistencyChecker(REPO_ROOT)
    result = checker.run_all()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print("  Gate 1: 静态 Schema 与双轨一致性门禁检查 (Static Consistency Gate)")
        print("=" * 70)
        print(f"[*] 检查项总数: {result['total_items_checked']}")
        if result["passed"]:
            print("[+] 门禁判定: 通过 (未发现 Schema、枚举或格式偏差)。")
        else:
            print(f"[!] 门禁判定: 失败 (发现 {result['violations_count']} 项违规):")
            for v in result["violations"]:
                print(f"    - [{v['gate']}] {v['file']}: {v['message']}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
