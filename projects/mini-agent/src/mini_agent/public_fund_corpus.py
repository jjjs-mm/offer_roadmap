"""Validation and coverage summaries for the reproducible public-fund corpus."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any


def validate_manifest(
    manifest: dict[str, Any],
    raw_directory: Path | None = None,
) -> None:
    """Validate reproducibility metadata and, when present, raw PDF bytes."""
    documents = manifest.get("documents", [])
    if not documents:
        raise ValueError("公开基金语料清单不能为空")

    filenames = [document["filename"] for document in documents]
    hashes = [document["sha256"] for document in documents]
    if len(filenames) != len(set(filenames)):
        raise ValueError("公开基金语料文件名不能重复")
    if len(hashes) != len(set(hashes)):
        raise ValueError("公开基金语料 SHA-256 不能重复")

    required_fields = {
        "filename",
        "fund_name",
        "fund_manager",
        "fund_code",
        "asset_type",
        "published_at",
        "source_url",
        "sha256",
    }
    for document in documents:
        missing = required_fields - document.keys()
        if missing:
            raise ValueError(f"语料清单缺少字段：{sorted(missing)}")
        if not document["source_url"].startswith("https://"):
            raise ValueError("公开基金资料必须使用 HTTPS 来源")
        if len(document["sha256"]) != 64:
            raise ValueError("公开基金资料 SHA-256 长度必须为 64")

        if raw_directory is None:
            continue
        file_path = raw_directory / document["filename"]
        if not file_path.exists():
            raise ValueError(f"缺少原始 PDF：{document['filename']}")
        actual_hash = sha256(file_path.read_bytes()).hexdigest()
        if actual_hash != document["sha256"]:
            raise ValueError(f"原始 PDF 指纹不匹配：{document['filename']}")


def summarize_manifest(manifest: dict[str, Any]) -> dict[str, object]:
    """Return stable corpus coverage metrics for reports and README updates."""
    validate_manifest(manifest)
    documents = manifest["documents"]
    managers = Counter(document["fund_manager"] for document in documents)
    asset_types = Counter(document["asset_type"] for document in documents)
    dates = sorted(document["published_at"] for document in documents)

    return {
        "document_count": len(documents),
        "fund_manager_count": len(managers),
        "fund_managers": dict(sorted(managers.items())),
        "asset_type_count": len(asset_types),
        "asset_types": dict(sorted(asset_types.items())),
        "published_at_range": {
            "earliest": dates[0],
            "latest": dates[-1],
        },
    }
