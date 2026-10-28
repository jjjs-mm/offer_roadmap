import json
from pathlib import Path

import pytest

from mini_agent.public_fund_corpus import summarize_manifest, validate_manifest


PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_manifest() -> dict:
    return json.loads(
        (PROJECT_DIR / "data/public_funds/manifest.json").read_text(
            encoding="utf-8"
        )
    )


def test_summarize_manifest_reports_corpus_coverage() -> None:
    summary = summarize_manifest(load_manifest())

    assert summary["document_count"] == 24
    assert summary["fund_manager_count"] == 9
    assert summary["asset_type_count"] >= 10
    assert summary["published_at_range"] == {
        "earliest": "2020-08-27",
        "latest": "2026-10-27",
    }


def test_validate_manifest_rejects_missing_raw_pdf(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="缺少原始 PDF"):
        validate_manifest(load_manifest(), tmp_path)
