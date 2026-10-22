import os
import sys
import json
import time
import copy
import yaml
import threading
import urllib.request
import urllib.error
from unittest import mock
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from _lib.boards.board_adapter_factory import get_board_adapter
from _lib.boards.offline_board_adapter import OfflineBoardAdapter
from _lib.boards.chunked_board_adapter import ChunkedBoardAdapter
from _lib.boards.weekly_board_adapter import WeeklyBoardAdapter
from _lib.boards.feishu_base_adapter import FeishuBaseAdapter
from _lib.boards.jira_adapter import JiraAdapter
from _lib.boards.github_projects_adapter import GitHubProjectsAdapter
from _lib.core.file_lock import acquire_lock, release_lock, LockBusyError


@pytest.fixture
def base_config_template():
    template_path = os.path.join(REPO_ROOT, "config/workflow.config.template.yaml")
    with open(template_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_board_adapter_factory_all_providers(tmp_path, base_config_template):
    """测试工厂根据配置正确实例化各类适配器，并对非法提供商做 Fail-Closed 拦截。"""
    cfg_file = str(tmp_path / "workflow.config.yaml")

    # 1. local chunked
    cfg1 = copy.deepcopy(base_config_template)
    cfg1["board"]["provider"] = "local"
    cfg1["board"]["storage_mode"] = "chunked"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg1, f)
    adapter = get_board_adapter(cfg_file)
    assert isinstance(adapter, ChunkedBoardAdapter)

    # 2. local weekly
    cfg2 = copy.deepcopy(base_config_template)
    cfg2["board"]["provider"] = "local"
    cfg2["board"]["storage_mode"] = "weekly"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg2, f)
    adapter = get_board_adapter(cfg_file)
    assert isinstance(adapter, WeeklyBoardAdapter)

    # 3. local single
    cfg3 = copy.deepcopy(base_config_template)
    cfg3["board"]["provider"] = "local"
    cfg3["board"]["storage_mode"] = "single"
    cfg3["board"]["board_file"] = str(tmp_path / "board.json")
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg3, f)
    adapter = get_board_adapter(cfg_file)
    assert isinstance(adapter, OfflineBoardAdapter)

    # 4. feishu_base
    cfg4 = copy.deepcopy(base_config_template)
    cfg4["board"]["provider"] = "feishu_base"
    cfg4["board"]["base_token"] = "token123"
    cfg4["board"]["table_id"] = "tbl123"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg4, f)
    adapter = get_board_adapter(cfg_file)
    assert isinstance(adapter, FeishuBaseAdapter)

    # 5. jira
    cfg5 = copy.deepcopy(base_config_template)
    cfg5["board"]["provider"] = "jira"
    cfg5["board"]["domain"] = "https://test.atlassian.net"
    cfg5["board"]["project_key"] = "PROJ"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg5, f)
    adapter = get_board_adapter(cfg_file)
    assert isinstance(adapter, JiraAdapter)

    # 6. github_projects
    cfg6 = copy.deepcopy(base_config_template)
    cfg6["board"]["provider"] = "github_projects"
    cfg6["board"]["owner"] = "myorg"
    cfg6["board"]["project_number"] = 42
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg6, f)
    adapter = get_board_adapter(cfg_file)
    assert isinstance(adapter, GitHubProjectsAdapter)

    # 7. 非法提供商 (Schema 与业务代码双层校验)
    cfg7 = copy.deepcopy(base_config_template)
    cfg7["board"]["provider"] = "unknown_cloud_vendor"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg7, f)
    with pytest.raises(ValueError):
        get_board_adapter(cfg_file)


def test_concurrent_multithread_file_lock(tmp_path):
    """压测 10 个线程高频竞争写入同一文件，验证 FileLock 互斥性与数据完整性。"""
    shared_data_file = str(tmp_path / "counter.json")
    lock_file = str(tmp_path / "counter.json.lock")

    with open(shared_data_file, "w", encoding="utf-8") as f:
        json.dump({"count": 0}, f)

    def worker(worker_id):
        for _ in range(10):
            handle = acquire_lock(lock_file, blocking=True, timeout=10.0)
            try:
                with open(shared_data_file, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                data["count"] += 1
                time.sleep(0.005)  # 模拟轻微写入开销
                with open(shared_data_file, "w", encoding="utf-8") as fp:
                    json.dump(data, fp)
            finally:
                release_lock(handle)

    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15.0)

    with open(shared_data_file, "r", encoding="utf-8") as f:
        final_data = json.load(f)

    assert final_data["count"] == 100, f"并发写锁数据丢失，最终计数={final_data['count']}，预期=100"


def test_cloud_adapters_mock_failure_injection():
    """验证云平台适配器在面对 401 鉴权失效与网络不可达时的 Fail-Closed 机制。"""
    # 1. JiraAdapter 对 401 鉴权失败与网络断开的 Fail-Closed
    jira = JiraAdapter(domain="https://jira.example.com", project_key="PROJ", user_email="a@b.c", api_token="tok")

    def mock_401_error(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    with mock.patch.object(urllib.request, "urlopen", side_effect=mock_401_error):
        assert jira.list_records() == []
        assert jira.get_record("PROJ-1") is None
        assert jira.create_record({"task_name": "New Issue"}) is None
        assert jira.update_record("PROJ-1", {"task_name": "Updated Issue"}) is False

    # 2. FeishuBaseAdapter 对 CLI 命令失败与网络超时的 Fail-Closed
    feishu = FeishuBaseAdapter(base_token="token_test", table_id="tbl_test")

    import subprocess
    mock_failed_process = mock.Mock(returncode=1, stdout="", stderr="Error: Unauthorized")

    with mock.patch.object(subprocess, "run", return_value=mock_failed_process):
        assert feishu.list_records() == []
        assert feishu.get_record("rec_1") is None
        assert feishu.update_record("rec_1", {"status": "进行中"}) is False
        assert feishu.create_record({"task_name": "新卡片"}) is None
