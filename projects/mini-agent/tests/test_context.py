from mini_agent.context import (
    build_context_summary,
    collect_removed_messages,
    estimate_messages_tokens,
    estimate_text_tokens,
    trim_messages_sliding_window,
)
import pytest

def test_estimate_ascii_tokens():
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("abcd") == 1
    assert estimate_text_tokens("abcde") == 2


def test_estimate_non_ascii_tokens():
    assert estimate_text_tokens("你好") == 2
    assert estimate_text_tokens("ab你") == 2


def test_estimate_messages_includes_content_and_structure():
    short_messages = [
        {
            "role": "user",
            "content": "hello",
        }
    ]
    long_messages = [
        {
            "role": "user",
            "content": "hello" * 100,
        }
    ]
    messages_with_tool = short_messages + [
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "27.0",
        }
    ]

    short_tokens = estimate_messages_tokens(short_messages)

    assert short_tokens > 0
    assert estimate_messages_tokens(long_messages) > short_tokens
    assert estimate_messages_tokens(messages_with_tool) > short_tokens

def test_trim_keeps_messages_within_budget():
    messages = [
        {"role": "system", "content": "规则"},
        {"role": "user", "content": "你好"},
    ]
    budget = estimate_messages_tokens(messages)

    result = trim_messages_sliding_window(
        messages,
        max_tokens=budget,
    )

    assert result == messages
    assert result is not messages


def test_trim_removes_old_messages():
    system_message = {
        "role": "system",
        "content": "规则",
    }
    old_user_message = {
        "role": "user",
        "content": "很早的问题" * 50,
    }
    old_assistant_message = {
        "role": "assistant",
        "content": "很早的回答" * 50,
    }
    latest_message = {
        "role": "user",
        "content": "最新问题",
    }

    messages = [
        system_message,
        old_user_message,
        old_assistant_message,
        latest_message,
    ]
    budget = estimate_messages_tokens(
        [system_message, latest_message]
    )

    result = trim_messages_sliding_window(
        messages,
        max_tokens=budget,
    )

    assert result == [
        system_message,
        latest_message,
    ]


def test_trim_rejects_invalid_budget():
    with pytest.raises(
        ValueError,
        match="max_tokens 必须大于 0",
    ):
        trim_messages_sliding_window(
            [],
            max_tokens=0,
        )

def test_trim_keeps_tool_call_and_result_together():
    system = {
        "role": "system",
        "content": "规则",
    }
    user = {
        "role": "user",
        "content": "完成任务",
    }

    old_assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "old_call",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"old.txt"}',
                },
            }
        ],
    }
    old_tool = {
        "role": "tool",
        "tool_call_id": "old_call",
        "content": "旧结果" * 100,
    }

    recent_assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "new_call",
                "type": "function",
                "function": {
                    "name": "calculator",
                    "arguments": '{"expression":"1+1"}',
                },
            }
        ],
    }
    recent_tool = {
        "role": "tool",
        "tool_call_id": "new_call",
        "content": "2.0",
    }

    messages = [
        system,
        user,
        old_assistant,
        old_tool,
        recent_assistant,
        recent_tool,
    ]

    budget = estimate_messages_tokens(
        [
            system,
            user,
            recent_assistant,
            recent_tool,
        ]
    )

    result = trim_messages_sliding_window(
        messages,
        max_tokens=budget,
    )

    assert result == [
        system,
        user,
        recent_assistant,
        recent_tool,
    ]

def test_collect_removed_messages_uses_identity():#即使两条消息内容完全相同，也能根据对象身份判断删除的是哪一条
    first_message = {
        "role": "user",
        "content": "相同内容",
    }
    second_message = {
        "role": "user",
        "content": "相同内容",
    }

    removed_messages = collect_removed_messages(
        original_messages=[
            first_message,
            second_message,
        ],
        kept_messages=[
            second_message,
        ],
    )

    assert removed_messages == [first_message]
    assert removed_messages[0] is first_message

def test_build_context_summary_returns_none_when_empty():
    summary = build_context_summary([])

    assert summary is None


def test_build_context_summary_limits_body_length():
    summary = build_context_summary(
        removed_messages=[
            {
                "role": "user",
                "content": "很长的旧消息" * 100,
            }
        ],
        max_chars=20,
    )

    assert summary is not None
    assert summary["role"] == "system"

    prefix = "此前上下文摘要：\n"
    summary_body = summary["content"].removeprefix(
        prefix
    )

    assert len(summary_body) == 20
    assert summary_body.endswith("…")
