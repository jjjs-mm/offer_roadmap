import json
from pathlib import Path

import pytest

from mini_agent.retrieval_dataset import (
    load_retrieval_dataset,
)


def test_load_retrieval_dataset(tmp_path) -> None:
    dataset_path = tmp_path / "dataset.json"

    dataset_path.write_text(
        json.dumps(
            {
                "name": "fund-retrieval-dev",
                "version": 1,
                "split": "dev",
                "documents": [
                    {
                        "filename": "fees.md",
                        "content": "管理费每年0.50%。",
                    }
                ],
                "cases": [
                    {
                        "case_id": "fee-paraphrase-001",
                        "category": "paraphrase",
                        "query": "每年收多少管理费用？",
                        "expected_sources": ["fees.md"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dataset = load_retrieval_dataset(dataset_path)

    assert dataset.name == "fund-retrieval-dev"
    assert dataset.version == 1
    assert dataset.split == "dev"
    assert len(dataset.documents) == 1
    assert len(dataset.cases) == 1
    assert dataset.cases[0].case_id == "fee-paraphrase-001"


def test_rejects_unknown_expected_source(tmp_path) -> None:
    dataset_path = tmp_path / "dataset.json"

    dataset_path.write_text(
        json.dumps(
            {
                "name": "invalid-dataset",
                "version": 1,
                "split": "test",
                "documents": [
                    {
                        "filename": "fees.md",
                        "content": "管理费每年0.50%。",
                    }
                ],
                "cases": [
                    {
                        "case_id": "unknown-source-001",
                        "category": "paraphrase",
                        "query": "投资目标是什么？",
                        "expected_sources": ["missing.md"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="不存在的标准来源"):
        load_retrieval_dataset(dataset_path)


def test_rejects_duplicate_case_ids(tmp_path) -> None:
    dataset_path = tmp_path / "dataset.json"

    case = {
        "case_id": "duplicate-001",
        "category": "exact",
        "query": "管理费",
        "expected_sources": ["fees.md"],
    }

    dataset_path.write_text(
        json.dumps(
            {
                "name": "invalid-dataset",
                "version": 1,
                "split": "dev",
                "documents": [
                    {
                        "filename": "fees.md",
                        "content": "管理费每年0.50%。",
                    }
                ],
                "cases": [case, case],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="重复的 case_id"):
        load_retrieval_dataset(dataset_path)


def test_loads_documents_from_shared_corpus(tmp_path) -> None:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "filename": "fees.md",
                        "content": "管理费每年0.50%。",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "name": "shared-corpus-dev",
                "version": 1,
                "split": "dev",
                "documents_file": "corpus.json",
                "cases": [
                    {
                        "case_id": "fee-001",
                        "category": "exact",
                        "query": "管理费",
                        "expected_sources": ["fees.md"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dataset = load_retrieval_dataset(dataset_path)

    assert dataset.documents[0].filename == "fees.md"


def test_checked_in_datasets_are_split_and_disjoint() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    datasets = [
        load_retrieval_dataset(
            data_dir / "retrieval_eval_dataset.json"
        ),
        load_retrieval_dataset(
            data_dir / "retrieval_eval_dev.json"
        ),
        load_retrieval_dataset(
            data_dir / "retrieval_eval_test.json"
        ),
    ]

    assert [dataset.split for dataset in datasets] == [
        "smoke",
        "dev",
        "test",
    ]
    assert [len(dataset.cases) for dataset in datasets] == [
        12,
        40,
        24,
    ]

    case_ids = [
        case.case_id
        for dataset in datasets
        for case in dataset.cases
    ]
    assert len(case_ids) == 76
    assert len(case_ids) == len(set(case_ids))
