#!/usr/bin/env python3
"""
单元测试：多 Agent 执行链路与轨迹离线全景图鉴生成器 (test_generate_trace_html.py)
验证 transcript.jsonl 离线解析、零 Token 渲染、异常容错与 CLI 接口。
"""
import os
import sys
import json
import tempfile
import pytest

from generate_trace_html import (
    find_transcript_file,
    parse_transcript,
    render_html,
    main as cli_main,
)


@pytest.fixture
def sample_transcript_data():
    """构造标准仿真 transcript.jsonl 数据行"""
    return [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-09-09T14:00:00+08:00",
            "content": "请实现用户登录接口并生成单元测试",
            "thinking": "",
            "tool_calls": [],
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-09-09T14:00:05+08:00",
            "content": "正在分析需求并拆解 WBS 工单...",
            "thinking": "首先需要检查是否有现有鉴权模块...",
            "tool_calls": [
                {
                    "name": "run_command",
                    "args": {"CommandLine": "python3 scripts/cli.py task create --name 登录接口"},
                    "toolSummary": "创建任务卡",
                },
                {
                    "name": "view_file",
                    "args": {"AbsolutePath": "/dummy/auth.py"},
                    "toolSummary": "查看文件",
                },
            ],
        },
        {
            "step_index": 2,
            "source": "SYSTEM",
            "type": "TOOL_RESULT",
            "status": "DONE",
            "created_at": "2026-09-09T14:00:08+08:00",
            "content": "Command finished with exit code 0.",
            "thinking": "",
            "tool_calls": [],
        },
    ]


@pytest.fixture
def temp_transcript_file(sample_transcript_data):
    """创建临时包含格式化 JSONL 和容错脏数据的 transcript 文件"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as f:
        # 写入空行与损坏行以测试容错性
        f.write("\n")
        f.write("MALFORMED JSON STRING\n")
        for item in sample_transcript_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        f.write("\n")
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


class TestGenerateTraceHtml:
    """轨迹解析与图鉴生成测试集"""

    def test_find_transcript_file_explicit(self, temp_transcript_file):
        """测试显式指定文件路径模式"""
        found = find_transcript_file(transcript_path=temp_transcript_file)
        assert found == os.path.abspath(temp_transcript_file)

    def test_find_transcript_file_not_found(self):
        """测试文件不存在场景"""
        assert find_transcript_file(transcript_path="/non/existent/path/transcript.jsonl") is None

    def test_find_transcript_file_by_conversation_id(self, monkeypatch, tmp_path):
        """测试基于 conversation_id 匹配 brain 目录"""
        mock_brain = tmp_path / "mock_brain"
        conv_id = "test-conv-12345"
        log_dir = mock_brain / conv_id / ".system_generated" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        target_file = log_dir / "transcript.jsonl"
        target_file.write_text('{"step_index": 0}\n', encoding="utf-8")

        monkeypatch.setattr(os.path, "expanduser", lambda p: str(mock_brain) if "brain" in p else os.path.expanduser(p))

        found = find_transcript_file(conversation_id=conv_id)
        assert found == str(target_file)

    def test_parse_transcript(self, temp_transcript_file):
        """测试核心轨迹解析与统计指标提取"""
        data = parse_transcript(temp_transcript_file)

        assert data["total_steps"] == 3
        assert data["total_tool_calls"] == 2
        assert data["total_content_chars"] > 0
        assert data["total_thinking_chars"] > 0
        assert data["start_time"] == "2026-09-09T14:00:00+08:00"
        assert data["end_time"] == "2026-09-09T14:00:08+08:00"

        # 校验工具分布
        breakdown_dict = dict(data["tool_breakdown"])
        assert breakdown_dict.get("run_command") == 1
        assert breakdown_dict.get("view_file") == 1

        # 校验步骤角色识别
        roles = [s["role"] for s in data["steps"]]
        assert roles == ["用户", "AI Agent", "系统"]

        # 校验步骤详情
        agent_step = data["steps"][1]
        assert len(agent_step["tool_calls"]) == 2
        assert agent_step["tool_calls"][0]["name"] == "run_command"
        assert agent_step["tool_calls"][0]["summary"] == "创建任务卡"

    def test_render_html(self, temp_transcript_file):
        """测试原生矢量 HTML 模板渲染"""
        data = parse_transcript(temp_transcript_file)
        custom_title = "测试流水线全景图鉴"
        html = render_html(data, title=custom_title)

        assert "<!DOCTYPE html>" in html
        assert f"<title>{custom_title}</title>" in html
        assert "run_command" in html
        assert "view_file" in html
        assert "创建任务卡" in html
        assert "总交互步数 (Steps)" in html
        assert "3" in html
        assert "工具调用分布统计" in html
        assert "0 LLM Token 消耗" in html

    def test_cli_execution_success(self, temp_transcript_file, tmp_path, monkeypatch):
        """测试 CLI 命令行入口成功流程"""
        out_html = tmp_path / "output_trace.html"
        test_args = [
            "generate_trace_html.py",
            "--transcript-file",
            temp_transcript_file,
            "--output",
            str(out_html),
            "--title",
            "自动化构建图鉴",
        ]
        monkeypatch.setattr(sys, "argv", test_args)

        ret = cli_main()
        assert ret == 0
        assert out_html.is_file()
        content = out_html.read_text(encoding="utf-8")
        assert "自动化构建图鉴" in content
        assert "run_command" in content

    def test_cli_execution_file_not_found(self, monkeypatch):
        """测试 CLI 未找到文件时非 0 退出"""
        test_args = [
            "generate_trace_html.py",
            "--transcript-file",
            "/invalid/path/does_not_exist.jsonl",
        ]
        monkeypatch.setattr(sys, "argv", test_args)

        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code != 0
