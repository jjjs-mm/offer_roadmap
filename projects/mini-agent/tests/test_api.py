from fastapi.testclient import TestClient

from mini_agent import api
import json


def test_health():
    client = TestClient(api.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_stream_returns_agent_events(monkeypatch):
    async def fake_stream_agent(
        question: str,
        history=None,
    ):
        assert question == "计算 3*(7+2)"

        yield {
            "type": "tool_start",
            "name": "calculator",
            "arguments": '{"expression":"3*(7+2)"}',
        }
        yield {
            "type": "tool_end",
            "name": "calculator",
            "result": "27.0",
        }
        yield {
            "type": "content",
            "content": "答案是 27。",
        }

    monkeypatch.setattr(api, "stream_agent", fake_stream_agent)

    client = TestClient(api.app)
    response = client.post(
        "/chat/stream",
        json={"question": "计算 3*(7+2)"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    assert "event: tool_start" in body
    assert "event: tool_end" in body
    assert "event: content" in body
    assert "calculator" in body
    assert "event: done" in body
    data_lines = [
       line.removeprefix("data:")
       for line in body.splitlines()
       if line.startswith("data:")
    ]
    events = [json.loads(line) for line in data_lines]

    assert events[-2]["type"] == "content"
    assert events[-2]["content"] == "答案是 27。"
    assert events[-1] == {"type": "done"}

def test_chat_stream_error_does_not_send_done(monkeypatch):
    async def failing_stream_agent(
        question: str,
        history=None,
    ):
        yield {
            "type": "error",
            "message": "network down",
        }

    monkeypatch.setattr(
        api,
        "stream_agent",
        failing_stream_agent,
    )

    client = TestClient(api.app)
    response = client.post(
        "/chat/stream",
        json={"question": "你好"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "network down" in response.text
    assert "event: done" not in response.text

def test_chat_stream_remembers_conversation(
    monkeypatch,
):
    received_histories = []

    async def fake_stream_agent(
        question: str,
        history=None,
    ):
        received_histories.append(
            [
                message.copy()
                for message in (history or [])
            ]
        )

        if question == "我叫小明":
            yield {
                "type": "content",
                "content": "记住了",
            }
        else:
            yield {
                "type": "content",
                "content": "你叫小明",
            }

    monkeypatch.setattr(
        api,
        "stream_agent",
        fake_stream_agent,
    )

    client = TestClient(api.app)

    first_response = client.post(
        "/chat/stream",
        json={
            "question": "我叫小明",
            "conversation_id": "memory-test",
        },
    )

    second_response = client.post(
        "/chat/stream",
        json={
            "question": "我叫什么？",
            "conversation_id": "memory-test",
        },
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert received_histories[0] == []
    assert received_histories[1] == [
        {
            "role": "user",
            "content": "我叫小明",
        },
        {
            "role": "assistant",
            "content": "记住了",
        },
    ]