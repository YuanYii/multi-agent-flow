import pytest
import sys
import os

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

from board_adapter_factory import get_board_adapter


def test_factory_raises_file_not_found_on_missing_config():
    """测试当配置文件路径不存在时，工厂 100% 物理抛出 FileNotFoundError，严禁隐式弱回退"""
    with pytest.raises(FileNotFoundError):
        get_board_adapter("/tmp/non_existent_config_12345.yaml")
