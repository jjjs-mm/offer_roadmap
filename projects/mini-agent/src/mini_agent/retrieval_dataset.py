import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


DatasetSplit = Literal["smoke", "dev", "test"]


@dataclass(frozen=True)
class RetrievalDocument:
    filename: str
    content: str


@dataclass(frozen=True)
class RetrievalDatasetCase:
    case_id: str
    category: str
    query: str
    expected_sources: frozenset[str]


@dataclass(frozen=True)
class RetrievalDataset:
    name: str
    version: int
    split: DatasetSplit
    documents: tuple[RetrievalDocument, ...]
    cases: tuple[RetrievalDatasetCase, ...]


def _required_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空")
    return value.strip()


def load_retrieval_dataset(path: Path) -> RetrievalDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))

    name = _required_string(payload.get("name"), "name")
    version = payload.get("version")
    split = payload.get("split")

    if not isinstance(version, int) or version < 1:
        raise ValueError("version 必须是正整数")
    if split not in {"smoke", "dev", "test"}:
        raise ValueError("split 必须是 smoke、dev 或 test")

    raw_documents = payload.get("documents")
    documents_file = payload.get("documents_file")

    if raw_documents is None and documents_file is not None:
        corpus_filename = _required_string(
            documents_file,
            "documents_file",
        )
        corpus_path = path.parent / corpus_filename
        corpus_payload = json.loads(
            corpus_path.read_text(encoding="utf-8")
        )
        raw_documents = corpus_payload.get("documents")

    if not isinstance(raw_documents, list):
        raise ValueError(
            "必须提供 documents 或有效的 documents_file"
        )

    documents: list[RetrievalDocument] = []
    filenames: set[str] = set()
    for item in raw_documents:
        filename = _required_string(item.get("filename"), "filename")
        content = _required_string(item.get("content"), "content")
        if filename in filenames:
            raise ValueError(f"重复的文档名: {filename}")
        filenames.add(filename)
        documents.append(
            RetrievalDocument(filename=filename, content=content)
        )

    if not documents:
        raise ValueError("documents 不能为空")

    cases: list[RetrievalDatasetCase] = []
    case_ids: set[str] = set()
    for item in payload.get("cases", []):
        case_id = _required_string(item.get("case_id"), "case_id")
        category = _required_string(item.get("category"), "category")
        query = _required_string(item.get("query"), "query")

        if case_id in case_ids:
            raise ValueError(f"重复的 case_id: {case_id}")
        case_ids.add(case_id)

        raw_sources = item.get("expected_sources")
        if not isinstance(raw_sources, list) or not all(
            isinstance(source, str) for source in raw_sources
        ):
            raise ValueError("expected_sources 必须是字符串列表")

        expected_sources = frozenset(raw_sources)
        unknown_sources = expected_sources - filenames
        if unknown_sources:
            names = ", ".join(sorted(unknown_sources))
            raise ValueError(f"不存在的标准来源: {names}")

        cases.append(
            RetrievalDatasetCase(
                case_id=case_id,
                category=category,
                query=query,
                expected_sources=expected_sources,
            )
        )

    if not cases:
        raise ValueError("cases 不能为空")

    return RetrievalDataset(
        name=name,
        version=version,
        split=split,
        documents=tuple(documents),
        cases=tuple(cases),
    )
