import pytest

from mini_agent.knowledge import KnowledgeChunk
from mini_agent.retrieval import rank_chunks


CHUNKS = [
    KnowledgeChunk(
        document_id="fees",
        source_name="fees.md",
        chunk_index=0,
        content="指数基金的管理费每年0.50%，托管费每年0.10%。",
    ),
    KnowledgeChunk(
        document_id="risks",
        source_name="risks.md",
        chunk_index=0,
        content="债券基金的主要风险是利率波动。",
    ),
]


@pytest.mark.parametrize(
    ("query", "expected_source"),
    [
        ("管理费", "fees.md"),
        ("这只基金每年收多少费用？", "fees.md"),
        ("基金面临什么风险？", "risks.md"),
    ],
)
def test_rank_chunks_finds_expected_source(
    query: str,
    expected_source: str,
) -> None:
    results = rank_chunks(query, CHUNKS, limit=1)
    assert results[0].source_name == expected_source


def test_rank_chunks_returns_empty_for_unrelated_query() -> None:
    assert rank_chunks("明天会下雨吗？", CHUNKS, limit=2) == []

def test_rank_chunks_keeps_short_exact_query() -> None:
    results = rank_chunks("债券", CHUNKS, limit=1)
    assert results[0].source_name == "risks.md"

def test_rank_chunks_rejects_weak_overlap_for_long_query() -> None:
    results = rank_chunks(
        "基金经理是谁？",
        CHUNKS,
        limit=2,
    )

    assert results == []