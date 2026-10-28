from hashlib import sha256
import pytest
from mini_agent.knowledge_repository import KnowledgeRepository


DOCUMENT_TEXT = "甲乙丙丁戊己庚辛壬癸"


def test_repository_saves_and_loads_document(tmp_path) -> None:
    database_path = tmp_path / "knowledge.sqlite3"
    file_bytes = DOCUMENT_TEXT.encode("utf-8")

    repository = KnowledgeRepository(database_path)

    saved = repository.save(
        filename="fund_report.txt",
        file_bytes=file_bytes,
        text=DOCUMENT_TEXT,
        chunk_size=4,
        overlap=1,
    )

    assert len(saved.document_id) == 32
    assert saved.filename == "fund_report.txt"
    assert saved.content_sha256 == sha256(file_bytes).hexdigest()
    assert saved.chunk_count == 3

    assert [chunk.content for chunk in saved.chunks] == [
        "甲乙丙丁",
        "丁戊己庚",
        "庚辛壬癸",
    ]

    # 使用新 Repository 模拟另一个进程重新连接数据库。
    another_repository = KnowledgeRepository(database_path)
    loaded = another_repository.get(saved.document_id)

    assert loaded == saved


def test_repository_returns_none_for_unknown_document(tmp_path) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )

    assert repository.get("missing-id") is None


def test_search_returns_matching_chunk_with_source(tmp_path) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )

    text = "沪深300指数基金的管理费为0.5%。"
    saved = repository.save(
        filename="fund_a.md",
        file_bytes=text.encode("utf-8"),
        text=text,
    )

    other_text = "债券基金的主要风险是利率波动。"
    repository.save(
        filename="fund_b.md",
        file_bytes=other_text.encode("utf-8"),
        text=other_text,
    )

    matches = repository.search("管理费")

    assert len(matches) == 1
    assert matches[0].document_id == saved.document_id
    assert matches[0].source_name == "fund_a.md"
    assert matches[0].chunk_index == 0
    assert "管理费为0.5%" in matches[0].content

    assert repository.search("托管费") == []


def test_search_respects_limit(tmp_path) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )

    for filename in ("fund_a.md", "fund_b.md"):
        text = "这只基金收取管理费。"
        repository.save(
            filename=filename,
            file_bytes=text.encode("utf-8"),
            text=text,
        )

    assert len(repository.search("管理费", limit=1)) == 1
    assert len(repository.search("管理费", limit=2)) == 2


def test_search_rejects_empty_query(tmp_path) -> None:
    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3"
    )

    with pytest.raises(ValueError, match="查询词不能为空"):
        repository.search("   ")

def test_ngram_search_ranks_saved_documents(tmp_path) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")

    fees = "指数基金的管理费每年0.50%。"
    saved = repository.save(
        filename="fees.md",
        file_bytes=fees.encode("utf-8"),
        text=fees,
    )

    risks = "债券基金的主要风险是利率波动。"
    repository.save(
        filename="risks.md",
        file_bytes=risks.encode("utf-8"),
        text=risks,
    )

    results = repository.search_ngrams(
        "这只基金每年收多少费用？",
        limit=1,
    )

    assert len(results) == 1
    assert results[0].document_id == saved.document_id
    assert results[0].source_name == "fees.md"


def test_vector_and_hybrid_search_use_configured_embedder(
    tmp_path,
) -> None:
    objective = "投资目标是跟踪宽基股票指数。"
    fees = "管理费每年0.50%。"
    query = "它想复制哪类市场表现？"

    def fake_embed(texts: list[str]) -> list[list[float]]:
        vectors = {
            query: [1.0, 0.0],
            objective: [0.9, 0.1],
            fees: [0.0, 1.0],
        }
        return [vectors[text] for text in texts]

    repository = KnowledgeRepository(
        tmp_path / "knowledge.sqlite3",
        embed_texts=fake_embed,
    )
    repository.save(
        filename="objective.md",
        file_bytes=objective.encode("utf-8"),
        text=objective,
    )
    repository.save(
        filename="fees.md",
        file_bytes=fees.encode("utf-8"),
        text=fees,
    )

    assert repository.search_vectors(query, limit=1)[0].source_name == (
        "objective.md"
    )
    assert repository.search_hybrid(query, limit=1)[0].source_name == (
        "objective.md"
    )


def test_vector_search_requires_embedder(tmp_path) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")

    with pytest.raises(RuntimeError, match="未配置向量模型"):
        repository.search_vectors("投资目标")


def test_repository_finds_document_by_content_sha256(tmp_path) -> None:
    repository = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    file_bytes = b"official fund document"
    saved = repository.save(
        filename="official.txt",
        file_bytes=file_bytes,
        text="official fund document",
        source_url="https://fund.example/official.pdf",
        published_at="2026-05-29",
    )

    found = repository.get_by_content_sha256(saved.content_sha256)

    assert found is not None
    assert found.document_id == saved.document_id
    assert found.source_url == "https://fund.example/official.pdf"
    assert found.published_at == "2026-05-29"
