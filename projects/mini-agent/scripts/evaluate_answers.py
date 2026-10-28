"""Run end-to-end answer evaluation against a live mini-agent API."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import httpx

from mini_agent.answer_evaluation import (
    AnswerEvalOutput,
    evaluate_answers,
    load_answer_eval_cases,
    parse_sse_answer,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = (
    PROJECT_DIR / "data" / "answer_eval_dataset.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8003",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_documents(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("documents 不能为空")
    return documents


def upload_documents(
    client: httpx.Client,
    documents: list[dict[str, str]],
) -> dict[str, str]:
    document_ids: dict[str, str] = {}
    for document in documents:
        filename = document["filename"]
        response = client.post(
            "/knowledge/documents",
            files={
                "file": (
                    filename,
                    document["content"].encode("utf-8"),
                    "text/markdown",
                )
            },
        )
        response.raise_for_status()
        document_ids[filename] = response.json()["document_id"]
    return document_ids


def run_cases(
    client: httpx.Client,
    dataset_path: Path,
) -> tuple[list, dict[str, AnswerEvalOutput]]:
    cases = load_answer_eval_cases(dataset_path)
    documents = load_documents(dataset_path)
    document_ids = upload_documents(client, documents)
    outputs: dict[str, AnswerEvalOutput] = {}

    for case in cases:
        document_id = document_ids.get(case.document_source)
        if document_id is None:
            raise ValueError(
                f"用例 {case.case_id} 引用了未知文档: "
                f"{case.document_source}"
            )

        response = client.post(
            "/chat/stream",
            json={
                "question": case.question,
                "conversation_id": (
                    f"answer-eval-{case.case_id}-{uuid4().hex}"
                ),
                "knowledge_document_id": document_id,
            },
        )
        response.raise_for_status()
        outputs[case.case_id] = parse_sse_answer(response.text)

    return cases, outputs


def main() -> None:
    args = parse_args()
    dataset_path = args.dataset.resolve()

    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=60,
    ) as client:
        cases, outputs = run_cases(client, dataset_path)

    report = evaluate_answers(cases, outputs)
    output = {
        "dataset": dataset_path.name,
        "base_url": args.base_url,
        "report": asdict(report),
        "outputs": {
            case_id: {
                "answer": result.answer,
                "cited_sources": sorted(result.cited_sources),
                "abstained": result.abstained,
            }
            for case_id, result in outputs.items()
        },
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output is not None:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
