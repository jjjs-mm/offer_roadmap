"""Tune semantic similarity threshold on the retrieval dev split."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from mini_agent.knowledge_repository import KnowledgeRepository
from mini_agent.retrieval_dataset import load_retrieval_dataset
from mini_agent.retrieval_evaluation import (
    RetrievalEvalCase,
    evaluate_retrieval,
)
from mini_agent.semantic_retrieval import get_default_embedder


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = (
    PROJECT_DIR / "data" / "retrieval_eval_dev.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=[0.55, 0.60, 0.65, 0.70, 0.75],
    )
    parser.add_argument("--limit", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_retrieval_dataset(args.dataset.resolve())
    cases = [
        RetrievalEvalCase(
            query=case.query,
            expected_sources=set(case.expected_sources),
        )
        for case in dataset.cases
    ]

    with TemporaryDirectory() as directory:
        repository = KnowledgeRepository(
            Path(directory) / "knowledge.sqlite3",
            embed_texts=get_default_embedder().embed,
        )
        for document in dataset.documents:
            repository.save(
                filename=document.filename,
                file_bytes=document.content.encode("utf-8"),
                text=document.content,
            )

        results: dict[str, dict] = {}
        for threshold in args.thresholds:
            report = evaluate_retrieval(
                cases,
                lambda query, limit, value=threshold: (
                    repository.search_hybrid(
                        query,
                        limit=limit,
                        minimum_vector_score=value,
                    )
                ),
                limit=args.limit,
            )
            metrics = asdict(report)
            metrics["balanced_score"] = round(
                (
                    2
                    * report.hit_at_1
                    * report.rejection_rate
                    / (report.hit_at_1 + report.rejection_rate)
                )
                if report.hit_at_1 + report.rejection_rate
                else 0.0,
                6,
            )
            results[f"{threshold:.2f}"] = metrics

    print(
        json.dumps(
            {
                "dataset": dataset.name,
                "split": dataset.split,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
