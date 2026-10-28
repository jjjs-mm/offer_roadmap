from datetime import datetime, timezone
from pathlib import Path

import pytest

from mini_agent.rag_trace import RagTraceRepository


def test_starts_and_finishes_trace(tmp_path: Path) -> None:
    repository = RagTraceRepository(tmp_path / "traces.sqlite3")

    started = repository.start(
        conversation_id="conversation-1",
        question="管理费是多少？",
        knowledge_document_id="document-1",
    )

    assert started.status == "started"
    assert started.completed_at is None

    finished = repository.finish(
        started.trace_id,
        status="succeeded",
        retrieval_method="hybrid",
        retrieved_chunk_count=2,
        evidence_sufficient=True,
        evidence_reason_code="explicit_fee_found",
        retrieval_duration_ms=12,
        generation_duration_ms=34,
        total_duration_ms=50,
    )

    assert finished.status == "succeeded"
    assert finished.retrieved_chunk_count == 2
    assert finished.evidence_sufficient is True
    assert finished.evidence_reason_code == "explicit_fee_found"
    assert finished.total_duration_ms == 50
    assert finished.completed_at is not None


def test_rejected_trace_preserves_reason(tmp_path: Path) -> None:
    repository = RagTraceRepository(tmp_path / "traces.sqlite3")
    started = repository.start(
        conversation_id="conversation-2",
        question="2027 年收益率是多少？",
        knowledge_document_id="document-2",
    )

    repository.finish(
        started.trace_id,
        status="rejected",
        retrieval_method="hybrid",
        retrieved_chunk_count=1,
        evidence_sufficient=False,
        evidence_reason_code="missing_time_constraint",
        total_duration_ms=8,
    )

    loaded = repository.get(started.trace_id)
    assert loaded is not None
    assert loaded.status == "rejected"
    assert loaded.evidence_sufficient is False
    assert loaded.evidence_reason_code == "missing_time_constraint"


def test_finish_rejects_unknown_trace(tmp_path: Path) -> None:
    repository = RagTraceRepository(tmp_path / "traces.sqlite3")

    with pytest.raises(KeyError, match="未知 trace_id"):
        repository.finish("missing", status="failed")


def test_metrics_exposes_rates_latency_and_in_flight_count(
    tmp_path: Path,
) -> None:
    repository = RagTraceRepository(tmp_path / "traces.sqlite3")
    succeeded = repository.start(
        conversation_id="metrics-1",
        question="投资目标是什么？",
        knowledge_document_id="document-1",
    )
    rejected = repository.start(
        conversation_id="metrics-2",
        question="2029 年收益率是多少？",
        knowledge_document_id="document-1",
    )
    repository.start(
        conversation_id="metrics-3",
        question="仍在执行的问题",
        knowledge_document_id="document-1",
    )
    repository.finish(
        succeeded.trace_id,
        status="succeeded",
        total_duration_ms=100,
    )
    repository.finish(
        rejected.trace_id,
        status="rejected",
        total_duration_ms=300,
    )

    metrics = repository.get_metrics(
        window_hours=1,
        now=datetime.now(timezone.utc),
    )

    assert metrics.request_count == 3
    assert metrics.completed_count == 2
    assert metrics.in_flight_count == 1
    assert metrics.success_rate == 0.5
    assert metrics.rejection_rate == 0.5
    assert metrics.failure_rate == 0.0
    assert metrics.total_latency_p50_ms == 200.0
    assert metrics.total_latency_p95_ms == 290.0
