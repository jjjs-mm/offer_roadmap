from fastapi.testclient import TestClient
from decimal import Decimal
from mini_agent import api
import json
from mini_agent.portfolio_repository import PortfolioRepository
from mini_agent.knowledge_repository import KnowledgeRepository
from mini_agent.ingestion_repository import IngestionRepository
from mini_agent.rag_trace import RagTraceRepository

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


def test_chat_stream_abstains_when_selected_document_lacks_fee_rate(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    text = "本资料未披露赎回费，管理费每年0.50%。"
    record = repository.save(
        filename="fund.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )
    monkeypatch.setattr(api, "knowledge_repository", repository)

    async def unexpected_stream_agent(question, history=None):
        raise AssertionError("证据不足时不应请求模型")
        yield  # 保持为异步生成器

    monkeypatch.setattr(api, "stream_agent", unexpected_stream_agent)

    response = TestClient(api.app).post(
        "/chat/stream",
        json={
            "question": "这只基金的赎回费是多少？",
            "conversation_id": "missing-fee-test",
            "knowledge_document_id": record.document_id,
        },
    )

    assert response.status_code == 200
    assert "event: content" in response.text
    assert "event: done" in response.text
    assert "event: error" not in response.text
    events = [
        json.loads(line.removeprefix("data:"))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    assert events[0]["type"] == "trace"
    content_event = next(
        event for event in events if event["type"] == "content"
    )
    assert "赎回费" in content_event["content"]
    assert "无法" in content_event["content"]
    assert events[-1] == {"type": "done"}

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

def test_upload_and_get_knowledge_document(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "knowledge_repository",
        repository,
        raising=False,
    )

    client = TestClient(api.app)

    document_text = (
        "# 沪深300指数基金\n\n"
        "该基金主要跟踪沪深300指数。"
    )

    response = client.post(
        "/knowledge/documents",
        files={
            "file": (
                "fund_report.md",
                document_text.encode("utf-8"),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 201

    payload = response.json()

    assert len(payload["document_id"]) == 32
    assert payload["filename"] == "fund_report.md"
    assert len(payload["content_sha256"]) == 64
    assert payload["chunk_count"] == 1

    assert payload["chunks"][0]["chunk_index"] == 0
    assert payload["chunks"][0]["content"] == document_text

    get_response = client.get(
        f"/knowledge/documents/{payload['document_id']}"
    )

    assert get_response.status_code == 200
    assert get_response.json() == payload


def test_async_knowledge_ingestion_persists_job_and_document(
    tmp_path,
    monkeypatch,
) -> None:
    knowledge = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    ingestions = IngestionRepository(tmp_path / "ingestions.sqlite3")
    monkeypatch.setattr(api, "knowledge_repository", knowledge)
    monkeypatch.setattr(api, "ingestion_repository", ingestions)

    response = TestClient(api.app).post(
        "/knowledge/ingestions",
        files={
            "file": (
                "fund.md",
                "投资目标：跟踪宽基股票指数。".encode("utf-8"),
                "text/markdown",
            )
        },
        data={
            "source_url": "https://fund.example/fund.md",
            "published_at": "2026-10-28",
        },
    )

    assert response.status_code == 202
    submitted = response.json()
    assert submitted["status"] == "queued"
    assert submitted["attempt_count"] == 0

    status_response = TestClient(api.app).get(
        f"/knowledge/ingestions/{submitted['ingestion_id']}"
    )
    assert status_response.status_code == 200
    completed = status_response.json()
    assert completed["status"] == "succeeded"
    assert completed["attempt_count"] == 1
    assert completed["document_id"] is not None

    document = knowledge.get(completed["document_id"])
    assert document is not None
    assert document.source_url == "https://fund.example/fund.md"


def test_async_knowledge_ingestion_can_retry_failed_pdf(
    tmp_path,
    monkeypatch,
) -> None:
    knowledge = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    ingestions = IngestionRepository(tmp_path / "ingestions.sqlite3")
    monkeypatch.setattr(api, "knowledge_repository", knowledge)
    monkeypatch.setattr(api, "ingestion_repository", ingestions)
    monkeypatch.setattr(
        api,
        "extract_pdf_pages",
        lambda _: (_ for _ in ()).throw(ValueError("PDF 无法解析")),
    )

    client = TestClient(api.app)
    response = client.post(
        "/knowledge/ingestions",
        files={"file": ("fund.pdf", b"%PDF-test", "application/pdf")},
    )
    ingestion_id = response.json()["ingestion_id"]

    failed = client.get(f"/knowledge/ingestions/{ingestion_id}")
    assert failed.json()["status"] == "failed"
    assert failed.json()["error_message"] == "PDF 无法解析"

    monkeypatch.setattr(
        api,
        "extract_pdf_pages",
        lambda _: ["投资目标：跟踪宽基股票指数。"],
    )
    retried = client.post(
        f"/knowledge/ingestions/{ingestion_id}/retry"
    )

    assert retried.status_code == 202
    completed = client.get(f"/knowledge/ingestions/{ingestion_id}")
    assert completed.json()["status"] == "succeeded"
    assert completed.json()["attempt_count"] == 2


def test_async_knowledge_ingestion_reuses_identical_upload(
    tmp_path,
    monkeypatch,
) -> None:
    knowledge = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    ingestions = IngestionRepository(tmp_path / "ingestions.sqlite3")
    monkeypatch.setattr(api, "knowledge_repository", knowledge)
    monkeypatch.setattr(api, "ingestion_repository", ingestions)
    client = TestClient(api.app)
    files = {
        "file": (
            "fund.md",
            "投资目标：跟踪宽基股票指数。".encode("utf-8"),
            "text/markdown",
        )
    }

    first = client.post("/knowledge/ingestions", files=files)
    second = client.post("/knowledge/ingestions", files=files)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["ingestion_id"] == second.json()["ingestion_id"]


def test_get_unknown_knowledge_document_returns_404(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "knowledge_repository",
        repository,
        raising=False,
    )

    client = TestClient(api.app)

    response = client.get(
        "/knowledge/documents/missing-id"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "未找到知识文档"
    }

def test_upload_knowledge_rejects_unsupported_file() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/knowledge/documents",
        files={
            "file": (
                "fund_report.docx",
                b"not a text document",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "只支持 TXT、Markdown 或 PDF 文件"
    }


def test_upload_pdf_preserves_source_metadata_and_page_number(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    monkeypatch.setattr(api, "knowledge_repository", repository)
    monkeypatch.setattr(
        api,
        "extract_pdf_pages",
        lambda _: ["投资目标：跟踪沪深300指数。", "管理费：0.15%。"],
    )

    response = TestClient(api.app).post(
        "/knowledge/documents",
        files={"file": ("official.pdf", b"%PDF-test", "application/pdf")},
        data={
            "source_url": "https://fund.example/official.pdf",
            "published_at": "2026-05-29",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_url"] == "https://fund.example/official.pdf"
    assert payload["published_at"] == "2026-05-29"
    assert [chunk["page_number"] for chunk in payload["chunks"]] == [1, 2]


def test_upload_knowledge_rejects_large_file() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/knowledge/documents",
        files={
            "file": (
                "large.txt",
                b"x" * (
                    api.MAX_KNOWLEDGE_FILE_BYTES + 1
                ),
                "text/plain",
            )
        },
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "知识文档不能超过 10 MiB"
    }


def test_upload_knowledge_rejects_non_utf8() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/knowledge/documents",
        files={
            "file": (
                "invalid.txt",
                b"\xff\xfe\xfa",
                "text/plain",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "知识文档必须使用 UTF-8 编码"
    }


def test_upload_knowledge_rejects_empty_document() -> None:
    client = TestClient(api.app)

    response = client.post(
        "/knowledge/documents",
        files={
            "file": (
                "empty.txt",
                b"   ",
                "text/plain",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "文档内容不能为空"
    }

def test_search_knowledge_returns_matching_chunks(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )
    monkeypatch.setattr(
        api,
        "knowledge_repository",
        repository,
    )

    text = "沪深300指数基金的管理费为0.5%。"
    saved = repository.save(
        filename="fund_a.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )

    client = TestClient(api.app)
    response = client.get(
        "/knowledge/search",
        params={"q": "管理费", "limit": 5},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "document_id": saved.document_id,
            "source_name": "fund_a.md",
            "chunk_index": 0,
            "content": text,
        }
    ]

    no_match = client.get(
        "/knowledge/search",
        params={"q": "托管费"},
    )
    assert no_match.status_code == 200
    assert no_match.json() == []


def test_search_knowledge_rejects_blank_query() -> None:
    client = TestClient(api.app)

    response = client.get(
        "/knowledge/search",
        params={"q": "   "},
    )

    assert response.status_code == 422

def test_search_knowledge_ngram_mode(tmp_path, monkeypatch) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    monkeypatch.setattr(api, "knowledge_repository", repository)

    text = "指数基金的管理费每年0.50%。"
    repository.save(
        filename="fees.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )

    response = TestClient(api.app).get(
        "/knowledge/search",
        params={
            "q": "这只基金每年收多少费用？",
            "mode": "ngram",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["source_name"] == "fees.md"


def test_search_knowledge_hybrid_mode(tmp_path, monkeypatch) -> None:
    objective = "投资目标是跟踪宽基股票指数。"
    query = "它想复制哪类市场表现？"

    def fake_embed(texts: list[str]) -> list[list[float]]:
        vectors = {
            query: [1.0, 0.0],
            objective: [0.9, 0.1],
        }
        return [vectors[text] for text in texts]

    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3",
        embed_texts=fake_embed,
    )
    monkeypatch.setattr(api, "knowledge_repository", repository)
    repository.save(
        filename="objective.md",
        file_bytes=objective.encode("utf-8"),
        text=objective,
    )

    response = TestClient(api.app).get(
        "/knowledge/search",
        params={
            "q": query,
            "mode": "hybrid",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["source_name"] == "objective.md"

def test_chat_stream_returns_fee_with_citation(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    text = "管理费每年0.50%。"
    record = repository.save(
        filename="fund_a.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )
    monkeypatch.setattr(api, "knowledge_repository", repository)

    async def unexpected_stream_agent(question, history=None):
        raise AssertionError("明确费率应从文档提取")
        yield

    monkeypatch.setattr(api, "stream_agent", unexpected_stream_agent)

    response = TestClient(api.app).post(
        "/chat/stream",
        json={
            "question": "管理费是多少？",
            "conversation_id": "cited-fee-test",
            "knowledge_document_id": record.document_id,
        },
    )

    events = [
        json.loads(line.removeprefix("data:"))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]

    answer = "".join(
        event["content"]
        for event in events
        if event["type"] == "content"
    )
    citations = [
        event for event in events
        if event["type"] == "citation"
    ]

    assert "0.50%" in answer
    assert citations == [{
        "type": "citation",
        "document_id": record.document_id,
        "source_name": "fund_a.md",
        "chunk_index": 0,
    }]
    assert events[-1] == {"type": "done"}

def test_chat_stream_uses_document_evidence_and_returns_citation(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )
    text = "投资目标：跟踪宽基股票指数。"
    record = repository.save(
        filename="fund-research.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )
    monkeypatch.setattr(
        api,
        "knowledge_repository",
        repository,
    )

    received_questions: list[str] = []
    received_tool_modes: list[bool] = []

    async def fake_stream_agent(
        question: str,
        history=None,
        enable_tools: bool = True,
    ):
        received_questions.append(question)
        received_tool_modes.append(enable_tools)
        yield {
            "type": "content",
            "content": "该基金的投资目标是跟踪宽基股票指数。",
        }

    monkeypatch.setattr(
        api,
        "stream_agent",
        fake_stream_agent,
    )

    response = TestClient(api.app).post(
        "/chat/stream",
        json={
            "question": "这只基金的投资目标是什么？",
            "conversation_id": "grounded-answer-test",
            "knowledge_document_id": record.document_id,
        },
    )

    assert response.status_code == 200
    assert len(received_questions) == 1
    assert "只能根据以下资料回答" in received_questions[0]
    assert "投资目标：跟踪宽基股票指数。" in received_questions[0]
    assert "这只基金的投资目标是什么？" in received_questions[0]
    assert received_tool_modes == [False]

    events = [
        json.loads(line.removeprefix("data:"))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]

    answer = "".join(
        event["content"]
        for event in events
        if event["type"] == "content"
    )
    citations = [
        event
        for event in events
        if event["type"] == "citation"
    ]

    assert "宽基股票指数" in answer
    assert citations == [
        {
            "type": "citation",
            "document_id": record.document_id,
            "source_name": "fund-research.md",
            "chunk_index": 0,
        }
    ]
    assert events[-1] == {"type": "done"}


def test_chat_stream_normalizes_scope_question_before_retrieval(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    trace_repository = RagTraceRepository(tmp_path / "traces.sqlite3")
    text = "投资范围：本基金不投资于股票。"
    record = repository.save(
        filename="bond-fund.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )
    monkeypatch.setattr(api, "knowledge_repository", repository)
    monkeypatch.setattr(api, "rag_trace_repository", trace_repository)

    received_questions: list[str] = []

    async def fake_stream_agent(
        question: str,
        history=None,
        enable_tools: bool = True,
    ):
        received_questions.append(question)
        assert enable_tools is False
        yield {"type": "content", "content": "该基金不投资于股票。"}

    monkeypatch.setattr(api, "stream_agent", fake_stream_agent)
    response = TestClient(api.app).post(
        "/chat/stream",
        json={
            "question": "这只债基能买股票吗？",
            "conversation_id": "normalized-scope-test",
            "knowledge_document_id": record.document_id,
        },
    )

    events = [
        json.loads(line.removeprefix("data:"))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    evidence_check = next(
        event for event in events if event["type"] == "evidence_check"
    )
    trace_event = next(event for event in events if event["type"] == "trace")

    assert response.status_code == 200
    assert evidence_check["sufficient"] is True
    assert evidence_check["question_type"] == "scope"
    assert len(received_questions) == 1
    assert "这只债基能买股票吗？" in received_questions[0]
    assert "是否投资" not in received_questions[0]

    trace = trace_repository.get(trace_event["trace_id"])
    assert trace is not None
    assert trace.retrieval_method == "hybrid_normalized"


def test_chat_stream_abstains_when_no_evidence_is_retrieved(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )
    text = "投资目标：跟踪宽基股票指数。"
    record = repository.save(
        filename="fund-research.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )
    monkeypatch.setattr(
        api,
        "knowledge_repository",
        repository,
    )

    model_called = False

    async def fake_stream_agent(
        question: str,
        history=None,
    ):
        nonlocal model_called
        model_called = True
        yield {
            "type": "content",
            "content": "不应生成这段回答",
        }

    monkeypatch.setattr(
        api,
        "stream_agent",
        fake_stream_agent,
    )

    response = TestClient(api.app).post(
        "/chat/stream",
        json={
            "question": "明天会下雨吗？",
            "conversation_id": "no-evidence-test",
            "knowledge_document_id": record.document_id,
        },
    )

    events = [
        json.loads(line.removeprefix("data:"))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]

    answer = "".join(
        event["content"]
        for event in events
        if event["type"] == "content"
    )

    assert model_called is False
    assert "无法" in answer
    assert not any(
        event["type"] == "citation"
        for event in events
    )
    assert events[-1] == {"type": "done"}


def test_chat_stream_stops_before_model_when_evidence_is_insufficient(
    tmp_path,
    monkeypatch,
) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    trace_repository = RagTraceRepository(tmp_path / "traces.sqlite3")
    text = "最近披露的2025年净值增长率为1.20%。"
    record = repository.save(
        filename="performance.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )
    monkeypatch.setattr(api, "knowledge_repository", repository)
    monkeypatch.setattr(api, "rag_trace_repository", trace_repository)

    async def unexpected_stream_agent(*args, **kwargs):
        raise AssertionError("证据不足时不应调用模型")
        yield

    monkeypatch.setattr(api, "stream_agent", unexpected_stream_agent)
    response = TestClient(api.app).post(
        "/chat/stream",
        json={
            "question": "2027年的收益率是多少？",
            "conversation_id": "insufficient-evidence-test",
            "knowledge_document_id": record.document_id,
        },
    )
    events = [
        json.loads(line.removeprefix("data:"))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]

    checks = [event for event in events if event["type"] == "evidence_check"]
    trace_event = next(event for event in events if event["type"] == "trace")
    assert len(checks) == 1
    assert checks[0]["sufficient"] is False
    assert checks[0]["reason_code"] == "missing_time_constraint"
    assert "无法" in "".join(
        event["content"] for event in events if event["type"] == "content"
    )
    assert not any(event["type"] == "citation" for event in events)
    assert events[-1] == {"type": "done"}

    trace_response = TestClient(api.app).get(
        f"/traces/{trace_event['trace_id']}"
    )
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["status"] == "rejected"
    assert trace_payload["retrieval_method"] == "hybrid"
    assert trace_payload["retrieved_chunk_count"] == 1
    assert trace_payload["evidence_sufficient"] is False
    assert (
        trace_payload["evidence_reason_code"]
        == "missing_time_constraint"
    )
    assert trace_payload["total_duration_ms"] >= 0


def test_get_unknown_rag_trace_returns_404(tmp_path, monkeypatch) -> None:
    trace_repository = RagTraceRepository(tmp_path / "traces.sqlite3")
    monkeypatch.setattr(api, "rag_trace_repository", trace_repository)

    response = TestClient(api.app).get("/traces/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "未找到 RAG Trace"}


def test_get_rag_trace_metrics_returns_aggregated_runtime_data(
    tmp_path,
    monkeypatch,
) -> None:
    trace_repository = RagTraceRepository(tmp_path / "traces.sqlite3")
    trace = trace_repository.start(
        conversation_id="metrics-api",
        question="投资目标是什么？",
        knowledge_document_id="document-1",
    )
    trace_repository.finish(
        trace.trace_id,
        status="succeeded",
        total_duration_ms=120,
    )
    monkeypatch.setattr(api, "rag_trace_repository", trace_repository)

    response = TestClient(api.app).get(
        "/traces/metrics?window_hours=24"
    )

    assert response.status_code == 200
    assert response.json()["request_count"] == 1
    assert response.json()["succeeded_count"] == 1
    assert response.json()["total_latency_p95_ms"] == 120.0
