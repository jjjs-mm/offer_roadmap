from mini_agent.knowledge import KnowledgeChunk
from mini_agent.semantic_retrieval import (
    rank_chunks_by_vector,
    rank_chunks_hybrid,
    reciprocal_rank_fusion,
)


OBJECTIVE = KnowledgeChunk(
    document_id="objective",
    source_name="objective.md",
    chunk_index=0,
    content="投资目标是跟踪宽基股票指数。",
)
FEES = KnowledgeChunk(
    document_id="fees",
    source_name="fees.md",
    chunk_index=0,
    content="管理费每年0.50%。",
)


def fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = {
        "它想复制哪类市场表现？": [1.0, 0.0],
        OBJECTIVE.content: [0.9, 0.1],
        FEES.content: [0.0, 1.0],
        "管理成本是多少？": [0.1, 0.9],
    }
    return [vectors[text] for text in texts]


def test_vector_search_handles_semantic_paraphrase() -> None:
    results = rank_chunks_by_vector(
        "它想复制哪类市场表现？",
        [FEES, OBJECTIVE],
        fake_embed,
        limit=1,
        minimum_score=0.5,
    )

    assert results == [OBJECTIVE]


def test_vector_search_rejects_results_below_threshold() -> None:
    results = rank_chunks_by_vector(
        "它想复制哪类市场表现？",
        [FEES],
        fake_embed,
        minimum_score=0.5,
    )

    assert results == []


def test_rrf_rewards_chunks_found_by_both_methods() -> None:
    results = reciprocal_rank_fusion(
        [
            [FEES, OBJECTIVE],
            [OBJECTIVE, FEES],
        ],
        limit=2,
    )

    assert {chunk.source_name for chunk in results} == {
        "fees.md",
        "objective.md",
    }


def test_hybrid_search_uses_semantic_results() -> None:
    results = rank_chunks_hybrid(
        "它想复制哪类市场表现？",
        [FEES, OBJECTIVE],
        fake_embed,
        limit=1,
        minimum_vector_score=0.5,
    )

    assert results == [OBJECTIVE]
