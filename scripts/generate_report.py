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
    "reviewer": "code_review_template.md",
    "qa": "qa_test_report_template.md",
    "docs": "module_design_template.md",
    "devops": "troubleshooting_template.md"
}

def generate_report(report_type: str, task_id: str, task_name: str, assignee: str, output_path: str, summary_content: str = ""):
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
    content = content.replace("【填写任务名称】", task_name)
    content = content.replace("【填写处理人】", assignee)
    content = content.replace("【填写日期】", now_str)

    if summary_content:
        content += f"\n\n### 📝 过程执行明细与补充记录 ({now_str})\n\n{summary_content}\n"

    # 若报告文件已存在，则作为复验/复测结论追加模式（确保不产生孤儿报告）
    mode = "a" if os.path.exists(output_path) else "w"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, mode, encoding="utf-8") as f:
        if mode == "a":
            f.write(f"\n\n---\n## 🔄 追加复验/复测记录 ({now_str})\n\n{summary_content}\n")
        else:
            f.write(content)

    action = "追加更新" if mode == "a" else "创建生成"
    print(f"[SUCCESS] 已成功{action}任务报告: {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="自动化任务报告生成器")
    parser.add_argument("--type", required=True, help="报告类型 (dev|review|qa)")
    parser.add_argument("--task-id", required=True, help="任务编号 (如 T0001)")
    parser.add_argument("--task-name", default="任务示例", help="任务名称")
    parser.add_argument("--assignee", default="Agent", help="处理人")
    parser.add_argument("--output", help="输出报告文件路径 (未指定时自动归档至 docs/reports/{type}/)")
    parser.add_argument("--summary", default="", help="执行总结与补充文本")

    args = parser.parse_args()

    output_path = args.output
    if not output_path:
        reports_dir = os.path.join(PROJECT_ROOT, "docs", "reports", args.type.lower())
        os.makedirs(reports_dir, exist_ok=True)
        filename = f"{args.task_id}_{args.type.lower()}_report.md"
        output_path = os.path.join(reports_dir, filename)

    success = generate_report(
        report_type=args.type,
        task_id=args.task_id,
        task_name=args.task_name,
        assignee=args.assignee,
        output_path=output_path,
        summary_content=args.summary
    )

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
