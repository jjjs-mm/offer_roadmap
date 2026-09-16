import pytest
from mini_agent.agent import _merge_stream_delta
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