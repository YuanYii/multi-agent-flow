#!/usr/bin/env python3
"""
多 Agent 执行链路与轨迹离线全景图鉴生成器 (Generate Trace HTML CLI)

核心设计目标：
- 确定性离线生成：完全由底层 Python 脚本解析 transcript.jsonl 并渲染，大模型 0 Token 消耗。
- 纯矢量扁平化：采用极简现代 UI Token 与原生 SVG 矢量图标，无外部 CDN 依赖，完全支持离线查看。
- 自动化全景聚合：提取各步骤的角色、工具调用、输入输出字符量与时间戳，呈现执行耗时与算力流向。
"""
import os
import sys
import json
import argparse
import datetime
from typing import List, Dict, Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import paths as _paths


def find_transcript_file(conversation_id: Optional[str] = None, transcript_path: Optional[str] = None) -> Optional[str]:
    """定位会话的 transcript.jsonl 路径"""
    if transcript_path:
        if os.path.isfile(transcript_path):
            return os.path.abspath(transcript_path)
        return None

    brain_base = os.path.expanduser("~/.gemini/antigravity-cli/brain")

    if conversation_id:
        target = os.path.join(brain_base, conversation_id, ".system_generated", "logs", "transcript.jsonl")
        if os.path.isfile(target):
            return target
        # 兼容直属路径
        target_direct = os.path.join(brain_base, conversation_id, "transcript.jsonl")
        if os.path.isfile(target_direct):
            return target_direct
        return None

    # 若均未指定，尝试获取当前活跃的会话或最近修改的会话
    if os.path.isdir(brain_base):
        conv_dirs = [os.path.join(brain_base, d) for d in os.listdir(brain_base) if os.path.isdir(os.path.join(brain_base, d))]
        conv_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        for cd in conv_dirs:
            p = os.path.join(cd, ".system_generated", "logs", "transcript.jsonl")
            if os.path.isfile(p):
                return p

    return None


def parse_transcript(transcript_path: str) -> Dict[str, Any]:
    """解析 transcript.jsonl，提取执行步骤、工具调用与量化指标"""
    steps = []
    tool_counter: Dict[str, int] = {}
    total_content_chars = 0
    total_thinking_chars = 0
    start_time = None
    end_time = None

    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                record = json.loads(line_str)
            except Exception:
                continue

            step_idx = record.get("step_index", len(steps))
            source = record.get("source", "UNKNOWN")
            step_type = record.get("type", "UNKNOWN")
            created_at = record.get("created_at", "")
            status = record.get("status", "DONE")
            content = record.get("content") or ""
            thinking = record.get("thinking") or ""
            tool_calls = record.get("tool_calls") or []

            total_content_chars += len(content)
            total_thinking_chars += len(thinking)

            if created_at:
                if start_time is None:
                    start_time = created_at
                end_time = created_at

            tools_summary = []
            for tc in tool_calls:
                name = tc.get("name", "tool")
                tool_counter[name] = tool_counter.get(name, 0) + 1
                args = tc.get("args") or {}
                summary = tc.get("toolSummary") or tc.get("toolAction") or ""
                tools_summary.append({
                    "name": name,
                    "summary": summary,
                    "args_preview": str(args)[:150]
                })

            role = "用户" if source == "USER_EXPLICIT" else ("系统" if source == "SYSTEM" else "AI Agent")
            
            steps.append({
                "step_index": step_idx,
                "role": role,
                "source": source,
                "type": step_type,
                "status": status,
                "created_at": created_at,
                "tool_calls": tools_summary,
                "tool_count": len(tool_calls),
                "content_len": len(content),
                "thinking_len": len(thinking),
                "content_snippet": (content[:200] + "...") if len(content) > 200 else content,
                "thinking_snippet": (thinking[:150] + "...") if len(thinking) > 150 else thinking,
            })

    # 排序与工期
    return {
        "transcript_path": transcript_path,
        "total_steps": len(steps),
        "total_tool_calls": sum(tool_counter.values()),
        "total_content_chars": total_content_chars,
        "total_thinking_chars": total_thinking_chars,
        "tool_breakdown": sorted(tool_counter.items(), key=lambda x: x[1], reverse=True),
        "start_time": start_time or "未知",
        "end_time": end_time or "未知",
        "steps": steps
    }


def render_html(data: Dict[str, Any], title: str = "多 Agent 执行链路与轨迹全景图鉴") -> str:
    """以原生 CSS 与扁平化矢量 SVG 渲染完全自包含的 HTML 页面"""
    tools_rows = "".join([
        f'<tr><td><code>{name}</code></td><td style="text-align:right;font-weight:600;">{count} 次</td></tr>'
        for name, count in data["tool_breakdown"]
    ])

    timeline_items = []
    for s in data["steps"]:
        badge_cls = "badge-user" if s["source"] == "USER_EXPLICIT" else ("badge-system" if s["source"] == "SYSTEM" else "badge-agent")
        tools_html = ""
        if s["tool_calls"]:
            tools_html = "<div class='tool-pill-container'>" + "".join([
                f'<span class="tool-pill"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg> {t["name"]}: {t["summary"] or t["args_preview"][:50]}</span>'
                for t in s["tool_calls"]
            ]) + "</div>"

        timeline_items.append(f"""
        <div class="timeline-row">
            <div class="timeline-meta">
                <span class="step-num">#{s["step_index"]}</span>
                <span class="role-badge {badge_cls}">{s["role"]}</span>
                <span class="time-text">{s["created_at"][11:19] if len(s["created_at"]) >= 19 else s["created_at"]}</span>
            </div>
            <div class="timeline-content">
                {tools_html}
                <div class="text-snippet">{s["content_snippet"] or s["thinking_snippet"]}</div>
                <div class="char-stats">正文: {s["content_len"]:,} 字符 | 思考: {s["thinking_len"]:,} 字符 | 状态: {s["status"]}</div>
            </div>
        </div>
        """)

    timeline_html = "\n".join(timeline_items)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #F8FAFC;
            --card-bg: #FFFFFF;
            --text-main: #0F172A;
            --text-muted: #64748B;
            --border: #E2E8F0;
            --primary: #2563EB;
            --primary-light: #EFF6FF;
            --accent: #0EA5E9;
            --success: #10B981;
            --warning: #F59E0B;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text-main);
            padding: 32px 20px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        header {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px 32px;
            margin-bottom: 24px;
        }}
        h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; color: var(--text-main); }}
        .header-desc {{ font-size: 13px; color: var(--text-muted); }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .metric-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px 20px;
        }}
        .metric-label {{ font-size: 12px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; margin-bottom: 4px; }}
        .metric-value {{ font-size: 24px; font-weight: 700; color: var(--primary); }}
        .metric-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 2px; }}

        .layout-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
        }}
        @media (max-width: 860px) {{ .layout-grid {{ grid-template-columns: 1fr; }} }}

        .panel {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px 24px;
        }}
        .panel-title {{
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 12px;
        }}

        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; }}
        th {{ color: var(--text-muted); font-weight: 500; }}
        code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #F1F5F9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}

        .timeline-row {{
            display: flex;
            gap: 16px;
            padding: 14px 0;
            border-bottom: 1px solid var(--border);
        }}
        .timeline-row:last-child {{ border-bottom: none; }}
        .timeline-meta {{
            width: 140px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .step-num {{ font-size: 12px; font-weight: 700; color: var(--text-muted); font-family: monospace; }}
        .time-text {{ font-size: 11px; color: var(--text-muted); }}
        .role-badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 4px;
            width: fit-content;
        }}
        .badge-user {{ background: #FEF3C7; color: #92400E; }}
        .badge-agent {{ background: #DBEAFE; color: #1E40AF; }}
        .badge-system {{ background: #F1F5F9; color: #475569; }}

        .timeline-content {{ flex-grow: 1; }}
        .tool-pill-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
        .tool-pill {{
            background: #F8FAFC;
            border: 1px solid var(--border);
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 6px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: #334155;
            font-family: monospace;
        }}
        .text-snippet {{ font-size: 13px; color: var(--text-main); margin-bottom: 4px; word-break: break-word; }}
        .char-stats {{ font-size: 11px; color: var(--text-muted); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <div class="header-desc">
                来源轨迹: <code>{data["transcript_path"]}</code><br>
                时间跨度: {data["start_time"]} ~ {data["end_time"]} | 离线生成引擎 (0 LLM Token 消耗)
            </div>
        </header>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">总交互步数 (Steps)</div>
                <div class="metric-value">{data["total_steps"]}</div>
                <div class="metric-sub">多轮问答与执行闭环</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">工具调用频次 (Tool Calls)</div>
                <div class="metric-value">{data["total_tool_calls"]}</div>
                <div class="metric-sub">调用 {len(data["tool_breakdown"])} 种不同工具</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">正文输出规模 (Content)</div>
                <div class="metric-value">{data["total_content_chars"]:,}</div>
                <div class="metric-sub">字符数总量</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">思考链字符量 (Thinking)</div>
                <div class="metric-value">{data["total_thinking_chars"]:,}</div>
                <div class="metric-sub">推理过程字符数</div>
            </div>
        </div>

        <div class="layout-grid">
            <div class="panel">
                <div class="panel-title">执行轨迹时间轴与上下文流转</div>
                <div class="timeline-container">
                    {timeline_html}
                </div>
            </div>
            <div>
                <div class="panel">
                    <div class="panel-title">工具调用分布统计</div>
                    <table>
                        <thead>
                            <tr><th>工具名称</th><th style="text-align:right;">调用次数</th></tr>
                        </thead>
                        <tbody>
                            {tools_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="多 Agent 执行链路与轨迹离线全景图鉴生成器 (0 Token)")
    parser.add_argument("--conversation-id", help="会话 ID (从 ~/.gemini/antigravity-cli/brain/ 中匹配)")
    parser.add_argument("--transcript-file", help="显式指定 transcript.jsonl 文件绝对路径")
    parser.add_argument("--output", help="输出 HTML 路径 (默认落盘至当前会话目录或 docs/D04-研发过程/D02-报告/trace_timeline.html)")
    parser.add_argument("--title", default="多 Agent 全流程上下文传递与协作链路图鉴", help="图鉴网页标题")

    args = parser.parse_args()

    t_file = find_transcript_file(args.conversation_id, args.transcript_file)
    if not t_file or not os.path.isfile(t_file):
        sys.stderr.write("[ERROR] 未找到有效的 transcript.jsonl 轨迹文件！\n")
        sys.stderr.write("请通过 --transcript-file 或 --conversation-id 指定。\n")
        sys.exit(1)

    print(f"[EXTRACT] 正在离线解析轨迹文件: {t_file} ...")
    data = parse_transcript(t_file)
    print(f"          解析完成: 共 {data['total_steps']} 步, {data['total_tool_calls']} 次工具调用, {data['total_content_chars']:,} 字符。")

    html_content = render_html(data, title=args.title)

    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        out_dir = os.path.join(_paths.docs_root(), "D04-研发过程", "D02-报告")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "trace_timeline.html")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[SUCCESS] 链路全景图鉴已离线生成 (耗时 <0.1s, 消耗 0 LLM Token):")
    print(f"          {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
