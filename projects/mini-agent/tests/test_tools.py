import pytest
from mini_agent.agent import _merge_stream_delta, _run_tool
from mini_agent.tools import calculator
from mini_agent import tools



def test_calculator_multiply_and_add():
    assert calculator("3*(7+2)") == "27.0"
    assert calculator("3 * (7 + 2)") == "27.0"


def test_calculator_divide():
    assert calculator("10 / 4") == "2.5"


def test_calculator_rejects_divide_by_zero():
    with pytest.raises(ValueError, match="除数不能为 0"):
        calculator("1/0")


def test_calculator_rejects_code():
    with pytest.raises(ValueError):
        calculator("__import__('os').system('echo hacked')")


def test_run_tool_success():
    result = _run_tool("calculator", '{"expression": "3*(7+2)"}')
    assert result == "27.0"


def test_run_tool_unknown_name():
    result = _run_tool("search", '{"expression": "1+1"}')
    assert result.startswith("未知工具")


def test_run_tool_divide_by_zero_returns_string():
    result = _run_tool("calculator", '{"expression": "1/0"}')
    assert result.startswith("工具执行失败")
    assert "0" in result


def test_run_tool_bad_json_returns_string():
    result = _run_tool("calculator", "not-json")
    assert result.startswith("工具执行失败")

def test_read_file_success(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "READ_ROOT", tmp_path)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("你好，mini-agent！", encoding="utf-8")

    assert tools.read_file("hello.txt") == "你好，mini-agent！"

def test_read_file_rejects_path_escape(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(tools, "READ_ROOT", data_dir)

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("不允许读取的测试内容", encoding="utf-8")

    with pytest.raises(ValueError, match="不允许"):
        tools.read_file("../outside.txt")

def test_run_tool_missing_file_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "READ_ROOT", tmp_path)

    result = _run_tool("read_file", '{"path": "missing.txt"}')

    assert result.startswith("工具执行失败:")

def test_merge_stream_tool_call_deltas():
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [],
    }

    deltas = [
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": "",
                    },
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "index": 0,
                    "function": {
                        "arguments": '{"expression"',
                    },
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "index": 0,
                    "function": {
                        "arguments": ':"3*(7+2)"}',
                    },
                }
            ]
        },
    ]

    for delta in deltas:
        _merge_stream_delta(message, delta)

    assert message["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "calculator",
            "arguments": '{"expression":"3*(7+2)"}',
        },
    }