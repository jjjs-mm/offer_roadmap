"""Evaluate retrieval against real fund-company PDF disclosures."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from mini_agent.knowledge import KnowledgeChunk
from mini_agent.evidence_sufficiency import assess_evidence_sufficiency
from mini_agent.fund_evidence import FEE_TERMS
from mini_agent.knowledge_repository import KnowledgeRepository
from mini_agent.pdf_ingestion import extract_pdf_pages
from mini_agent.query_normalization import normalize_financial_query
from mini_agent.retrieval import rank_chunks
from mini_agent.semantic_retrieval import (
    get_default_embedder,
    rank_chunks_by_vector,
    rank_chunks_hybrid,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_DIR / "data" / "public_funds" / "manifest.json"
DEFAULT_DATASET = PROJECT_DIR / "data" / "public_fund_eval_dev.json"
DEFAULT_RAW_DIR = PROJECT_DIR / "data" / "public_funds" / "raw"


def normalize_search(search):
    """Evaluate the same retrieval query normalization used by the API."""
    def normalized(query: str, limit: int) -> list[KnowledgeChunk]:
        return search(
            normalize_financial_query(query).retrieval_query,
            limit,
        )

    return normalized


def evaluate(
    cases: list[dict],
    search,
    limit: int,
) -> dict[str, float | int]:
    answerable = [case for case in cases if case["expected_source"]]
    unanswerable = [case for case in cases if not case["expected_source"]]
    source_hit_1 = source_hit_k = page_hit_k = rejected = 0
    reciprocal_rank = 0.0

    for case in cases:
        results: list[KnowledgeChunk] = search(case["query"], limit)
        if case["expected_source"] is None:
            rejected += int(not results)
            continue

        matching_rank: int | None = None
        matching_chunks: list[KnowledgeChunk] = []
        for rank, chunk in enumerate(results, start=1):
            if chunk.source_name == case["expected_source"]:
                matching_chunks.append(chunk)
                if matching_rank is None:
                    matching_rank = rank

        if matching_rank is not None:
            source_hit_k += 1
            reciprocal_rank += 1 / matching_rank
            source_hit_1 += int(matching_rank == 1)

        expected_pages = set(case["expected_pages"])
        if any(chunk.page_number in expected_pages for chunk in matching_chunks):
            page_hit_k += 1

    answerable_count = len(answerable)
    unanswerable_count = len(unanswerable)
    return {
        "total_cases": len(cases),
        "answerable_cases": answerable_count,
        "unanswerable_cases": unanswerable_count,
        "source_hit_at_1": source_hit_1 / answerable_count,
        "source_hit_at_k": source_hit_k / answerable_count,
        "source_mrr": reciprocal_rank / answerable_count,
        "page_hit_at_k": page_hit_k / answerable_count,
        "rejection_rate": rejected / unanswerable_count,
    }


def evaluate_selected_documents(
    cases: list[dict],
    records: dict[str, object],
    limit: int,
    ranker=rank_chunks,
) -> dict[str, float | int]:
    answerable = [case for case in cases if case["expected_pages"]]
    unanswerable = [case for case in cases if not case["expected_pages"]]
    page_hit_1 = page_hit_k = rejected = 0
    correct_gate = answerable_passed = unanswerable_rejected = 0
    answerable_rejected_case_ids: list[str] = []
    unanswerable_accepted_case_ids: list[str] = []
    page_miss_case_ids: list[str] = []

    for case in cases:
        record = records[case["selected_source"]]
        normalized_query = normalize_financial_query(case["query"])
        results = ranker(
            normalized_query.retrieval_query,
            record.chunks,
            limit,
        )
        expected_pages = set(case["expected_pages"])
        # The API resolves explicit fee questions against the selected
        # document's fee tables before generic top-k RAG.  Use the same path
        # here, otherwise this report would evaluate a different system.
        evidence_for_gate = (
            record.chunks
            if any(term in normalized_query.retrieval_query for term in FEE_TERMS)
            else results
        )
        assessment = assess_evidence_sufficiency(
            normalized_query.retrieval_query,
            evidence_for_gate,
        )
        expected_answerable = bool(expected_pages)
        correct_gate += int(assessment.sufficient == expected_answerable)
        if expected_answerable:
            answerable_passed += int(assessment.sufficient)
            if not assessment.sufficient:
                answerable_rejected_case_ids.append(case["case_id"])
        else:
            unanswerable_rejected += int(not assessment.sufficient)
            if assessment.sufficient:
                unanswerable_accepted_case_ids.append(case["case_id"])
        if not expected_pages:
            rejected += int(not results)
            continue
        if results and results[0].page_number in expected_pages:
            page_hit_1 += 1
        if any(chunk.page_number in expected_pages for chunk in results):
            page_hit_k += 1
        else:
            page_miss_case_ids.append(case["case_id"])

    return {
        "total_cases": len(cases),
        "answerable_cases": len(answerable),
        "unanswerable_cases": len(unanswerable),
        "page_hit_at_1": page_hit_1 / len(answerable),
        "page_hit_at_k": page_hit_k / len(answerable),
        "rejection_rate": rejected / len(unanswerable),
        "evidence_gate_accuracy": correct_gate / len(cases),
        "answerable_pass_rate": answerable_passed / len(answerable),
        "unanswerable_rejection_rate": (
            unanswerable_rejected / len(unanswerable)
        ),
        "false_answer_rate": (
            1 - unanswerable_rejected / len(unanswerable)
        ),
        "answerable_rejected_case_ids": answerable_rejected_case_ids,
        "unanswerable_accepted_case_ids": unanswerable_accepted_case_ids,
        "page_miss_case_ids": page_miss_case_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--include-semantic", action="store_true")
    parser.add_argument("--minimum-vector-score", type=float, default=0.65)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))

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
        records = {}
        fund_names = {}
        for document in manifest["documents"]:
            file_bytes = (args.raw_dir / document["filename"]).read_bytes()
            pages = extract_pdf_pages(file_bytes)
            records[document["filename"]] = repository.save(
                filename=document["filename"],
                file_bytes=file_bytes,
                text="\n\n".join(pages),
                pages=pages,
                source_url=document["source_url"],
                published_at=document["published_at"],
            )

            fund_names[document["filename"]] = document["fund_name"]

        started_at = perf_counter_ns()
        discovery_cases = [
            {
                **case,
                "query": (
                    fund_names[case["selected_source"]]
                    + " "
                    + case["query"]
                    if case["expected_source"] is not None
                    else case["query"]
                ),
            }
            for case in dataset["cases"]
        ]
        methods = {
            "catalog_ngram": evaluate(
                discovery_cases,
                normalize_search(repository.search_ngrams),
                args.limit,
            ),
            "selected_document_ngram": evaluate_selected_documents(
                dataset["cases"],
                records,
                args.limit,
            ),
        }
        if embed_texts is not None:
            methods["catalog_vector"] = evaluate(
                discovery_cases,
                lambda query, limit: repository.search_vectors(
                    normalize_financial_query(query).retrieval_query,
                    limit=limit,
                    minimum_score=args.minimum_vector_score,
                ),
                args.limit,
            )
            methods["catalog_hybrid"] = evaluate(
                discovery_cases,
                lambda query, limit: repository.search_hybrid(
                    normalize_financial_query(query).retrieval_query,
                    limit=limit,
                    minimum_vector_score=args.minimum_vector_score,
                ),
                args.limit,
            )
            methods["selected_document_vector"] = (
                evaluate_selected_documents(
                    dataset["cases"],
                    records,
                    args.limit,
                    ranker=lambda query, chunks, limit: (
                        rank_chunks_by_vector(
                            query,
                            chunks,
                            embed_texts,
                            limit=limit,
                            minimum_score=args.minimum_vector_score,
                        )
                    ),
                )
            )
            methods["selected_document_hybrid"] = (
                evaluate_selected_documents(
                    dataset["cases"],
                    records,
                    args.limit,
                    ranker=lambda query, chunks, limit: (
                        rank_chunks_hybrid(
                            query,
                            chunks,
                            embed_texts,
                            limit=limit,
                            minimum_vector_score=args.minimum_vector_score,
                        )
                    ),
                )
            )
        elapsed_ms = (perf_counter_ns() - started_at) / 1_000_000

    report = {
        "dataset": dataset["name"],
        "version": dataset["version"],
        "split": dataset["split"],
        "document_count": len(manifest["documents"]),
        "case_count": len(dataset["cases"]),
        "limit": args.limit,
        "query_normalization": "conservative_fund_aliases_v1",
        "evaluation_time_ms": round(elapsed_ms, 4),
        "methods": methods,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
