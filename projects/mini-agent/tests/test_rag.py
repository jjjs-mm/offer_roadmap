from mini_agent.knowledge import KnowledgeChunk
from mini_agent.rag import (
    build_grounded_question,
    retrieve_evidence,
)


CHUNKS = [
    KnowledgeChunk(
        document_id="fund-a",
        source_name="fund-a.md",
        chunk_index=0,
        content="投资目标：跟踪宽基股票指数。",
    ),
    KnowledgeChunk(
        document_id="fund-a",
        source_name="fund-a.md",
        chunk_index=1,
        content="风险提示：股票市场波动可能导致本金亏损。",
    ),
]


def test_retrieve_evidence_returns_relevant_chunk() -> None:
    evidence = retrieve_evidence(
        "这只基金的投资目标是什么？",
        CHUNKS,
        limit=1,
    )

    assert len(evidence) == 1
    assert evidence[0].chunk_index == 0
    assert "宽基股票指数" in evidence[0].content


def test_retrieve_evidence_returns_empty_for_unrelated_question() -> None:
    evidence = retrieve_evidence(
        "明天会下雨吗？",
        CHUNKS,
        limit=2,
    )

    assert evidence == []


def test_build_grounded_question_contains_rules_and_evidence() -> None:
    prompt = build_grounded_question(
        "这只基金的投资目标是什么？",
        [CHUNKS[0]],
    )

    assert "只能根据以下资料回答" in prompt
    assert "资料不足" in prompt
    assert "投资目标：跟踪宽基股票指数。" in prompt
    assert "这只基金的投资目标是什么？" in prompt