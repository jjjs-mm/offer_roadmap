"""Evaluate retrieval methods on a versioned fund dataset."""

import argparse
import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from mini_agent.knowledge import KnowledgeChunk
from mini_agent.knowledge_repository import KnowledgeRepository
from mini_agent.retrieval_dataset import (
    RetrievalDataset,
    load_retrieval_dataset,
)
from mini_agent.retrieval_evaluation import (
    RetrievalEvalCase,
    evaluate_retrieval,
)
from mini_agent.semantic_retrieval import get_default_embedder


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = (
    PROJECT_DIR / "data" / "retrieval_eval_dataset.json"
)
Search = Callable[[str, int], list[KnowledgeChunk]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--include-semantic",
        action="store_true",
        help="评测本地向量检索和 RRF 混合检索",
    )
    parser.add_argument(
        "--minimum-vector-score",
        type=float,
        default=0.65,
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def to_eval_cases(dataset: RetrievalDataset) -> list[RetrievalEvalCase]:
    return [
        RetrievalEvalCase(
            query=case.query,
            expected_sources=set(case.expected_sources),
        )
        for case in dataset.cases
    ]


def save_documents(
    repository: KnowledgeRepository,
    dataset: RetrievalDataset,
) -> None:
    for document in dataset.documents:
        repository.save(
            filename=document.filename,
            file_bytes=document.content.encode("utf-8"),
            text=document.content,
        )


def measure_latency(
    cases: list[RetrievalEvalCase],
    search: Search,
    limit: int,
    repetitions: int = 100,
) -> dict[str, float]:
    timings_ms: list[float] = []
    for _ in range(repetitions):
        for case in cases:
            started_at = perf_counter_ns()
            search(case.query, limit)
            timings_ms.append(
                (perf_counter_ns() - started_at) / 1_000_000
            )

    ordered = sorted(timings_ms)
    p95_index = int(0.95 * (len(ordered) - 1))
    return {
        "p50": round(median(ordered), 4),
        "p95": round(ordered[p95_index], 4),
    }


def evaluate_cases(
    cases: list[RetrievalEvalCase],
    search: Search,
    limit: int,
) -> dict:
    return asdict(evaluate_retrieval(cases, search, limit=limit))


def evaluate_categories(
    dataset: RetrievalDataset,
    search: Search,
    limit: int,
) -> dict[str, dict]:
    output: dict[str, dict] = {}
    categories = sorted({case.category for case in dataset.cases})

    for category in categories:
        category_cases = [
            RetrievalEvalCase(
                query=case.query,
                expected_sources=set(case.expected_sources),
            )
            for case in dataset.cases
            if case.category == category
        ]
        output[category] = evaluate_cases(
            category_cases,
            search,
            limit,
        )

    return output


def evaluate_method(
    dataset: RetrievalDataset,
    search: Search,
    limit: int,
) -> dict:
    cases = to_eval_cases(dataset)
    result = evaluate_cases(cases, search, limit)
    result["limit"] = limit
    result["by_category"] = evaluate_categories(
        dataset,
        search,
        limit,
    )
    result["latency_ms"] = measure_latency(cases, search, limit)
    return result


def main() -> None:
    args = parse_args()
    dataset_path = args.dataset.resolve()
    dataset = load_retrieval_dataset(dataset_path)

    with TemporaryDirectory() as directory:
        embed_texts = (
            get_default_embedder().embed
            if args.include_semantic
            else None
        )
        repository = KnowledgeRepository(
            Path(directory) / "knowledge.sqlite3",
            embed_texts=embed_texts,
        )
        save_documents(repository, dataset)
        methods = {
            "keyword": evaluate_method(
                dataset,
                repository.search,
                args.limit,
            ),
            "ngram": evaluate_method(
                dataset,
                repository.search_ngrams,
                args.limit,
            ),
        }
        if args.include_semantic:
            methods["vector"] = evaluate_method(
                dataset,
                lambda query, limit: repository.search_vectors(
                    query,
                    limit=limit,
                    minimum_score=args.minimum_vector_score,
                ),
                args.limit,
            )
            methods["hybrid"] = evaluate_method(
                dataset,
                lambda query, limit: repository.search_hybrid(
                    query,
                    limit=limit,
                    minimum_vector_score=(
                        args.minimum_vector_score
                    ),
                ),
                args.limit,
            )
        output = {
            "dataset": dataset.name,
            "version": dataset.version,
            "split": dataset.split,
            "document_count": len(dataset.documents),
            "case_count": len(dataset.cases),
            "minimum_vector_score": args.minimum_vector_score,
            "methods": methods,
        }

    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output is not None:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
