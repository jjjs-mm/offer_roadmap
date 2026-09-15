import pytest
import httpx

from mini_agent.agent import stream_agent


@pytest.mark.asyncio#模拟缺少环境变量
async def test_stream_agent_reports_missing_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    events = [
        event
        async for event in stream_agent(
           "你好",
           max_request_attempts=1,
        )
    ]

    assert events == [
        {
            "type": "error",
            "message": "缺少环境变量 LLM_API_KEY",
        }
    ]

@pytest.mark.asyncio#模拟网络连接失败
async def test_stream_agent_reports_network_error(monkeypatch):
    class FailingClient:
        async def stream_chat(self, messages, tools=None):
            raise httpx.ConnectError("network down")

            # 让这个函数保持异步生成器类型
            yield {}

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: FailingClient(),
    )

    events = [
        event
        async for event in stream_agent(
           "你好",
           max_request_attempts=1,
       )
    ]

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "ConnectError" in events[0]["message"]
    assert "network down" in events[0]["message"]

@pytest.mark.asyncio
async def test_stream_agent_emits_context_trim(monkeypatch):
    class FakeClient:
        async def stream_chat(
            self,
            messages,
            tools=None,
        ):
            yield {
                "content": "完成",
            }

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: FakeClient(),
    )

    def fake_trim(messages, max_tokens):
        return [messages[-1]]

    monkeypatch.setattr(
        "mini_agent.agent.trim_messages_sliding_window",
        fake_trim,#用来模拟“发生了裁剪”
    )

    events = [
        event
        async for event in stream_agent(
            "你好",
            max_context_tokens=100,
        )
    ]

    assert events[0] == {
        "type": "context_trim",
        "before_tokens": events[0]["before_tokens"],
        "after_tokens": events[0]["after_tokens"],
        "removed_messages": 1,
    }
    assert (
        events[0]["after_tokens"]
        < events[0]["before_tokens"]
    )
    assert events[1] == {
        "type": "content",
        "content": "完成",
    }

@pytest.mark.asyncio
async def test_stream_agent_emits_context_summary(#专门确认“摘要足够短时会被采用并发出事件”
    monkeypatch,
):
    class FakeClient:
        async def stream_chat(
            self,
            messages,
            tools=None,
        ):
            yield {
                "content": "完成",
            }

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: FakeClient(),
    )

    def fake_trim(messages, max_tokens):
        return [messages[-1]]

    monkeypatch.setattr(
        "mini_agent.agent.trim_messages_sliding_window",
        fake_trim,
    )

    monkeypatch.setattr(
        "mini_agent.agent.build_context_summary",
        lambda removed_messages: {
            "role": "system",
            "content": "此前上下文摘要：\n旧内容",
        },
    )

    events = [
        event
        async for event in stream_agent(
            "你好",
            max_context_tokens=100,
        )
    ]

    assert [
        event["type"]
        for event in events
    ] == [
        "context_trim",
        "context_summary",
        "content",
    ]

    assert events[1] == {
        "type": "context_summary",
        "summary": "此前上下文摘要：\n旧内容",
    }

@pytest.mark.asyncio
async def test_stream_agent_retries_before_first_delta(
    monkeypatch,
):
    class FlakyClient:
        def __init__(self):
            self.calls = 0

        async def stream_chat(
            self,
            messages,
            tools=None,
        ):
            self.calls += 1

            if self.calls == 1:
                raise httpx.ConnectError("network down")

            yield {
                "content": "重试成功",
            }

    client = FlakyClient()

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: client,
    )

    events = [
        event
        async for event in stream_agent(
            "你好",
            max_request_attempts=3,
            retry_delay_seconds=0,
        )
    ]

    assert client.calls == 2

    assert events[0] == {
        "type": "retry",
        "next_attempt": 2,
        "max_attempts": 3,
        "delay_seconds": 0,
        "reason": "ConnectError",
    }

    assert events[1] == {
        "type": "content",
        "content": "重试成功",
    }

@pytest.mark.asyncio
async def test_stream_agent_does_not_retry_after_delta(
    monkeypatch,
):
    class PartialFailureClient:
        def __init__(self):
            self.calls = 0

        async def stream_chat(
            self,
            messages,
            tools=None,
        ):
            self.calls += 1

            yield {
                "content": "已经输出",
            }

            raise httpx.ConnectError("stream lost")

    client = PartialFailureClient()

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: client,
    )

    events = [
        event
        async for event in stream_agent(
            "你好",
            max_request_attempts=3,
            retry_delay_seconds=0,
        )
    ]

    assert client.calls == 1

    assert [
        event["type"]
        for event in events
    ] == [
        "content",
        "error",
    ]

    assert events[0]["content"] == "已经输出"
    assert "ConnectError" in events[1]["message"]

@pytest.mark.asyncio
async def test_stream_agent_reuses_cached_tool_result(
    monkeypatch,
):
    class RepeatingToolClient:
        def __init__(self):
            self.calls = 0

        async def stream_chat(
            self,
            messages,
            tools=None,
        ):
            self.calls += 1

            if self.calls <= 2:
                yield {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"call_{self.calls}",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": (
                                    '{"expression":"3*(7+2)"}'
                                ),
                            },
                        }
                    ]
                }
            else:
                yield {"content": "答案是 27"}

    client = RepeatingToolClient()
    tool_runs = 0

    def fake_run_tool(name, arguments):
        nonlocal tool_runs
        tool_runs += 1
        return "27.0"

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: client,
    )
    monkeypatch.setattr(
        "mini_agent.agent._run_tool",
        fake_run_tool,
    )

    events = [
        event
        async for event in stream_agent("计算 3*(7+2)")
    ]

    assert client.calls == 3
    assert tool_runs == 1
    assert [
        event["type"]
        for event in events
    ] == [
        "tool_start",
        "tool_end",
        "content",
    ]

@pytest.mark.asyncio
async def test_stream_agent_includes_history(
    monkeypatch,
):
    captured_messages = []

    class FakeClient:
        async def stream_chat(
            self,
            messages,
            tools=None,
        ):
            captured_messages.extend(messages)
            yield {"content": "你叫小明"}

    monkeypatch.setattr(
        "mini_agent.agent.LLMClient.from_env",
        lambda: FakeClient(),
    )

    history = [
        {
            "role": "user",
            "content": "我叫小明",
        },
        {
            "role": "assistant",
            "content": "记住了",
        },
    ]

    events = [
        event
        async for event in stream_agent(
            "我叫什么？",
            history=history,
        )
    ]

    assert events == [
        {
            "type": "content",
            "content": "你叫小明",
        }
    ]

    assert captured_messages[-3:] == [
        *history,
        {
            "role": "user",
            "content": "我叫什么？",
        },
    ]