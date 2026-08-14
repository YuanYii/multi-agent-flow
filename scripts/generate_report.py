#!/usr/bin/env python3
"""
自动化任务报告渲染生成器 (Generate Report CLI)
"""
import os
import sys
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "..", "templates")

REPORT_TEMPLATE_MAP = {
    "pm": "wbs_breakdown_template.md",
    "arch": "module_design_template.md",
    "dev": "dev_task_report_template.md",
    "frontend": "dev_task_report_template.md",
    "reviewer": "code_review_template.md",
    "qa": "qa_test_report_template.md",
    "docs": "documentation_template.md",
    "devops": "troubleshooting_template.md"
}

# 旧名/别名兼容映射 (如 --type review 等价 reviewer)
TYPE_ALIASES = {
    "review": "reviewer"
}

# 元数据/表格示例类占位符：生成时统一替换，避免交付物残留 ${...}
# (正文内容占位符如 ${PROBLEM_BACKGROUND} 保留给专家填写)
META_PLACEHOLDERS = {
    "${STAGE_NAME}": "",
    "${WORKPACKAGE_NAME}": "",
    "${START_DATE}": "",
    "${END_DATE}": "",
    "${QA_NAME}": "",
    "${SCENARIO_1}": "",
    "${SCENARIO_2}": "",
    "${EXPECT_1}": "",
    "${EXPECT_2}": "",
    "${ACTUAL_1}": "",
    "${ACTUAL_2}": ""
}

def generate_report(report_type: str, task_id: str, task_name: str, assignee: str, output_path: str, summary_content: str = ""):
    report_type = TYPE_ALIASES.get(report_type.lower(), report_type.lower())
    template_file = REPORT_TEMPLATE_MAP.get(report_type.lower())
    if not template_file:
        print(f"[ERROR] 不支持的报告类型: {report_type}")
        return False

    template_path = os.path.join(TEMPLATES_DIR, template_file)
    if not os.path.exists(template_path):
        print(f"[ERROR] 报告模板文件不存在: {template_path}")
        return False

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 替换变量占位符
    content = content.replace("T0001", task_id)
    content = content.replace("${TASK_ID}", task_id)
    content = content.replace("${TASK_NAME}", task_name)
    content = content.replace("${DEV_NAME}", assignee)
    content = content.replace("${QA_NAME}", assignee)
    content = content.replace("${REVIEWER_NAME}", assignee)
    content = content.replace("${ARCHITECT_NAME}", assignee)
    content = content.replace("${DOCS_NAME}", assignee)
    content = content.replace("${DEVOPS_NAME}", assignee)
    content = content.replace("${PM_NAME}", assignee)
    content = content.replace("${DATE}", now_str)
    content = content.replace("${END_DATE}", now_str)
    content = content.replace("【填写任务名称】", task_name)
    content = content.replace("【填写处理人】", assignee)
    content = content.replace("【填写日期】", now_str)
    for placeholder, value in META_PLACEHOLDERS.items():
        content = content.replace(placeholder, value)

    if summary_content:
        content += f"\n\n### [CONFIG]  过程执行明细与补充记录 ({now_str})\n\n{summary_content}\n"

    # 若报告文件已存在，则作为复验/复测结论追加模式（仅当带有非空文本时追加，避免空分隔线污染）
    if os.path.exists(output_path):
        if summary_content and summary_content.strip():
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n---\n## [SYNC]  追加复验/复测记录 ({now_str})\n\n{summary_content}\n")
            print(f"[SUCCESS] 已成功追加更新任务报告: {output_path}")
        else:
            print(f"[INFO] 任务报告已存在且无新增摘要文本，保持现有文件不变: {output_path}")
        return True

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[SUCCESS] 已成功创建生成任务报告: {output_path}")
    return True

def main(args: list = None):
    parser = argparse.ArgumentParser(description="自动化任务报告生成器")
    parser.add_argument("--type", required=True, help="报告类型 (pm|arch|dev|frontend|reviewer|qa|docs|devops，兼容别名 review)")
    parser.add_argument("--task-id", required=True, help="任务编号 (如 T0001)")
    parser.add_argument("--task-name", default="工作包开发任务", help="任务名称")
    parser.add_argument("--assignee", default="DEV", help="处理人")
    parser.add_argument("--output", default="", help="输出报告文件路径 (未指定时自动归档至 docs/reports/{type}/)")
    parser.add_argument("--summary", default="", help="执行总结与补充文本")

    parsed_args = parser.parse_args(args)

    # 归一化类型 (别名兼容) 并物理校验，不支持的返回非零退出码 (Fail-Closed)
    report_type = TYPE_ALIASES.get(parsed_args.type.lower(), parsed_args.type.lower())
    if report_type not in REPORT_TEMPLATE_MAP:
        print(f"[ERROR] 不支持的报告类型: {parsed_args.type} (可选: {', '.join(REPORT_TEMPLATE_MAP.keys())})")
        return 1

    output_path = parsed_args.output
    if not output_path:
        reports_dir = os.path.join(PROJECT_ROOT, "docs", "reports", report_type)
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"{parsed_args.task_id}_{report_type}_report.md"
        output_path = os.path.join(reports_dir, filename)

    success = generate_report(
        report_type=report_type,
        task_id=parsed_args.task_id,
        task_name=parsed_args.task_name,
        assignee=parsed_args.assignee,
        output_path=output_path,
        summary_content=parsed_args.summary
    )

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
