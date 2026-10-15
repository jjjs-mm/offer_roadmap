from fastapi.testclient import TestClient
from decimal import Decimal
from mini_agent import api
import json
from mini_agent.portfolio_repository import PortfolioRepository

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

def test_root_returns_chat_page():
    client = TestClient(api.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "mini-agent" in response.text

def test_delete_conversation_clears_history():
    conversation_id = "clear-test"
    api.conversation_histories[conversation_id] = [
        {
            "role": "user",
            "content": "我叫小明",
        }
    ]

    client = TestClient(api.app)
    response = client.delete(
        f"/conversations/{conversation_id}",
    )

    assert response.status_code == 204
    assert conversation_id not in api.conversation_histories

def test_analyze_portfolio_upload(
    tmp_path,
    monkeypatch,
) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "portfolio_repository",
        repository,
        raising=False,
    )

    client = TestClient(api.app)

    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,20,100\n"
        "债券基金,bond_fund,20,50\n"
        "现金,cash,1000,1\n"
    )

    response = client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                csv_content.encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert len(payload["portfolio_id"]) == 32
    assert payload["filename"] == "portfolio.csv"
    assert len(payload["content_sha256"]) == 64

    analysis = payload["analysis"]

    assert analysis["position_count"] == 3
    assert Decimal(
        str(analysis["total_market_value"])
    ) == Decimal("4000")
    assert (
        analysis["largest_position"]["name"]
        == "股票基金"
    )
    assert Decimal(
        str(analysis["concentration_hhi"])
    ) == Decimal("0.375")

    get_response = client.get(
        f"/portfolio/{payload['portfolio_id']}"
    )

    assert get_response.status_code == 200
    assert get_response.json() == payload

def test_get_unknown_portfolio_returns_404(
    tmp_path,
    monkeypatch,
) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "portfolio_repository",
        repository,
        raising=False,
    )

    client = TestClient(api.app)

    response = client.get("/portfolio/missing-id")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "未找到持仓分析记录"
    }

def test_analyze_portfolio_rejects_non_csv() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.txt",
                b"not a csv",
                "text/plain",
            )
        },
    )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "只支持 CSV 文件"
    }


def test_analyze_portfolio_rejects_invalid_csv() -> None:
    client = TestClient(api.app)

    invalid_csv = (
        "name,asset_type,quantity\n"
        "股票基金,equity_fund,20\n"
    )

    response = client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                invalid_csv.encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "CSV 缺少必要列: price"
    }


def test_analyze_portfolio_rejects_large_file() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                b"x" * (
                    api.MAX_PORTFOLIO_FILE_BYTES + 1
                ),
                "text/csv",
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "持仓 CSV 不能超过 1 MiB"
    }


def test_analyze_portfolio_rejects_non_utf8() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                b"\xff\xfe\xfd",
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "持仓 CSV 必须使用 UTF-8 编码"
    }

def test_get_portfolio_risk_report(
    tmp_path,
    monkeypatch,
) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "portfolio_repository",
        repository,
    )

    client = TestClient(api.app)

    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,50,100\n"
        "债券基金,bond_fund,25,100\n"
        "货币基金,cash,25,100\n"
    )

    upload_response = client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                csv_content.encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 200

    portfolio_id = upload_response.json()["portfolio_id"]

    risk_response = client.get(
        f"/portfolio/{portfolio_id}/risk"
    )

    assert risk_response.status_code == 200

    payload = risk_response.json()

    assert payload["portfolio_id"] == portfolio_id
    assert payload["report"]["overall_level"] == "high"

    signal_codes = {
        signal["code"]
        for signal in payload["report"]["signals"]
    }

    assert "largest_position_concentration" in signal_codes
    assert "hhi_concentration" in signal_codes


def test_get_unknown_portfolio_risk_returns_404(
    tmp_path,
    monkeypatch,
) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "portfolio_repository",
        repository,
    )

    client = TestClient(api.app)

    response = client.get(
        "/portfolio/missing-id/risk"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "未找到持仓分析记录"
    }