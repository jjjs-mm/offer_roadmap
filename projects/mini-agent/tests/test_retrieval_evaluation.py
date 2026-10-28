import pytest

from mini_agent.knowledge import KnowledgeChunk
from mini_agent.retrieval_evaluation import (
    RetrievalEvalCase,
    evaluate_retrieval,
)


def make_chunk(source_name: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        document_id=f"id-{source_name}",
        source_name=source_name,
        chunk_index=0,
        content=f"{source_name} 的内容",
    )


def test_evaluate_retrieval_metrics() -> None:
    results_by_query = {
        "费用是多少": [
            make_chunk("risks.md"),
            make_chunk("fees.md"),
        ],
        "有什么风险": [
            make_chunk("risks.md"),
        ],
        "赎回费是多少": [],
    }

    def search(
        query: str,
        limit: int,
    ) -> list[KnowledgeChunk]:
        return results_by_query[query][:limit]

    cases = [
        RetrievalEvalCase(
            query="费用是多少",
            expected_sources={"fees.md"},
        ),
        RetrievalEvalCase(
            query="有什么风险",
            expected_sources={"risks.md"},
        ),
        RetrievalEvalCase(
            query="赎回费是多少",
            expected_sources=set(),
        ),
    ]

    report = evaluate_retrieval(
        cases,
        search,
        limit=3,
    )

    assert report.total_cases == 3
    assert report.answerable_cases == 2
    assert report.unanswerable_cases == 1

    assert report.hit_at_1 == pytest.approx(0.5)
    assert report.hit_at_k == pytest.approx(1.0)
    assert report.mrr == pytest.approx(0.75)
    assert report.rejection_rate == pytest.approx(1.0)