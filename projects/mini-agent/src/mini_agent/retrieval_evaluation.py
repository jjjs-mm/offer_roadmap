from collections.abc import Callable
from dataclasses import dataclass

from mini_agent.knowledge import KnowledgeChunk


Search = Callable[
    [str, int],
    list[KnowledgeChunk],
]


@dataclass(frozen=True)
class RetrievalEvalCase:
    query: str
    expected_sources: set[str]


@dataclass(frozen=True)
class RetrievalEvalReport:
    total_cases: int
    answerable_cases: int
    unanswerable_cases: int
    hit_at_1: float
    hit_at_k: float
    mrr: float
    rejection_rate: float


def evaluate_retrieval(
    cases: list[RetrievalEvalCase],
    search: Search,
    limit: int = 3,
) -> RetrievalEvalReport:
    if not cases:
        raise ValueError("评测用例不能为空")

    if limit < 1:
        raise ValueError("limit 必须大于 0")

    answerable_cases = 0
    unanswerable_cases = 0

    hit_at_1_count = 0
    hit_at_k_count = 0
    reciprocal_rank_sum = 0.0
    rejection_count = 0

    for case in cases:
        results = search(case.query, limit)

        if case.expected_sources:
            answerable_cases += 1

            matching_rank = None

            for rank, chunk in enumerate(
                results,
                start=1,
            ):
                if (
                    chunk.source_name
                    in case.expected_sources
                ):
                    matching_rank = rank
                    break

            if matching_rank is not None:
                hit_at_k_count += 1
                reciprocal_rank_sum += (
                    1 / matching_rank
                )

                if matching_rank == 1:
                    hit_at_1_count += 1
        else:
            unanswerable_cases += 1

            if not results:
                rejection_count += 1

    hit_at_1 = (
        hit_at_1_count / answerable_cases
        if answerable_cases
        else 0.0
    )
    hit_at_k = (
        hit_at_k_count / answerable_cases
        if answerable_cases
        else 0.0
    )
    mrr = (
        reciprocal_rank_sum / answerable_cases
        if answerable_cases
        else 0.0
    )
    rejection_rate = (
        rejection_count / unanswerable_cases
        if unanswerable_cases
        else 0.0
    )

    return RetrievalEvalReport(
        total_cases=len(cases),
        answerable_cases=answerable_cases,
        unanswerable_cases=unanswerable_cases,
        hit_at_1=hit_at_1,
        hit_at_k=hit_at_k,
        mrr=mrr,
        rejection_rate=rejection_rate,
    )