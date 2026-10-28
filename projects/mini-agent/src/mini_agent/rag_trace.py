import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel


PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_RAG_TRACE_DATABASE_PATH = Path(
    os.getenv(
        "RAG_TRACE_DATABASE_PATH",
        str(PROJECT_DIR / "data" / "rag_traces.sqlite3"),
    )
)

TraceStatus = Literal[
    "started",
    "succeeded",
    "rejected",
    "failed",
]


class RagTraceRecord(BaseModel):
    trace_id: str
    conversation_id: str
    question: str
    knowledge_document_id: str | None = None
    status: TraceStatus
    retrieval_method: str | None = None
    retrieved_chunk_count: int = 0
    evidence_sufficient: bool | None = None
    evidence_reason_code: str | None = None
    retrieval_duration_ms: int | None = None
    generation_duration_ms: int | None = None
    total_duration_ms: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RagTraceMetrics(BaseModel):
    """窗口内 RAG 请求的聚合指标，不包含问题、回答或密钥。"""

    window_started_at: datetime
    generated_at: datetime
    request_count: int
    completed_count: int
    in_flight_count: int
    succeeded_count: int
    rejected_count: int
    failed_count: int
    success_rate: float | None = None
    rejection_rate: float | None = None
    failure_rate: float | None = None
    total_latency_p50_ms: float | None = None
    total_latency_p95_ms: float | None = None


class RagTraceRepository:
    """持久化 RAG 请求的阶段结果，不保存 Prompt、答案或密钥。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_traces (
                    trace_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    knowledge_document_id TEXT,
                    status TEXT NOT NULL,
                    retrieval_method TEXT,
                    retrieved_chunk_count INTEGER NOT NULL DEFAULT 0,
                    evidence_sufficient INTEGER,
                    evidence_reason_code TEXT,
                    retrieval_duration_ms INTEGER,
                    generation_duration_ms INTEGER,
                    total_duration_ms INTEGER,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

    def start(
        self,
        *,
        conversation_id: str,
        question: str,
        knowledge_document_id: str | None,
    ) -> RagTraceRecord:
        record = RagTraceRecord(
            trace_id=uuid4().hex,
            conversation_id=conversation_id,
            question=question,
            knowledge_document_id=knowledge_document_id,
            status="started",
            created_at=datetime.now(timezone.utc),
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rag_traces (
                    trace_id,
                    conversation_id,
                    question,
                    knowledge_document_id,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trace_id,
                    record.conversation_id,
                    record.question,
                    record.knowledge_document_id,
                    record.status,
                    record.created_at.isoformat(),
                ),
            )

        return record

    def finish(
        self,
        trace_id: str,
        *,
        status: Literal["succeeded", "rejected", "failed"],
        retrieval_method: str | None = None,
        retrieved_chunk_count: int = 0,
        evidence_sufficient: bool | None = None,
        evidence_reason_code: str | None = None,
        retrieval_duration_ms: int | None = None,
        generation_duration_ms: int | None = None,
        total_duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> RagTraceRecord:
        completed_at = datetime.now(timezone.utc)

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE rag_traces
                SET
                    status = ?,
                    retrieval_method = ?,
                    retrieved_chunk_count = ?,
                    evidence_sufficient = ?,
                    evidence_reason_code = ?,
                    retrieval_duration_ms = ?,
                    generation_duration_ms = ?,
                    total_duration_ms = ?,
                    error_message = ?,
                    completed_at = ?
                WHERE trace_id = ?
                """,
                (
                    status,
                    retrieval_method,
                    retrieved_chunk_count,
                    (
                        None
                        if evidence_sufficient is None
                        else int(evidence_sufficient)
                    ),
                    evidence_reason_code,
                    retrieval_duration_ms,
                    generation_duration_ms,
                    total_duration_ms,
                    error_message,
                    completed_at.isoformat(),
                    trace_id,
                ),
            )

            if cursor.rowcount == 0:
                raise KeyError(f"未知 trace_id: {trace_id}")

        record = self.get(trace_id)
        if record is None:
            raise RuntimeError("Trace 更新成功但读取失败")
        return record

    def get(self, trace_id: str) -> RagTraceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM rag_traces
                WHERE trace_id = ?
                """,
                (trace_id,),
            ).fetchone()

        if row is None:
            return None

        evidence_sufficient = row["evidence_sufficient"]
        return RagTraceRecord(
            trace_id=row["trace_id"],
            conversation_id=row["conversation_id"],
            question=row["question"],
            knowledge_document_id=row["knowledge_document_id"],
            status=row["status"],
            retrieval_method=row["retrieval_method"],
            retrieved_chunk_count=row["retrieved_chunk_count"],
            evidence_sufficient=(
                None
                if evidence_sufficient is None
                else bool(evidence_sufficient)
            ),
            evidence_reason_code=row["evidence_reason_code"],
            retrieval_duration_ms=row["retrieval_duration_ms"],
            generation_duration_ms=row["generation_duration_ms"],
            total_duration_ms=row["total_duration_ms"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"] is not None
                else None
            ),
        )

    def get_metrics(
        self,
        *,
        window_hours: int,
        now: datetime | None = None,
    ) -> RagTraceMetrics:
        """为运行面板和告警系统聚合指定时间窗口的请求指标。"""
        generated_at = now or datetime.now(timezone.utc)
        window_started_at = generated_at - timedelta(
            hours=window_hours
        )

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT status, total_duration_ms
                FROM rag_traces
                WHERE created_at >= ?
                """,
                (window_started_at.isoformat(),),
            ).fetchall()

        request_count = len(rows)
        succeeded_count = sum(
            row["status"] == "succeeded" for row in rows
        )
        rejected_count = sum(
            row["status"] == "rejected" for row in rows
        )
        failed_count = sum(
            row["status"] == "failed" for row in rows
        )
        completed_count = (
            succeeded_count + rejected_count + failed_count
        )
        durations = sorted(
            row["total_duration_ms"]
            for row in rows
            if row["total_duration_ms"] is not None
        )

        return RagTraceMetrics(
            window_started_at=window_started_at,
            generated_at=generated_at,
            request_count=request_count,
            completed_count=completed_count,
            in_flight_count=request_count - completed_count,
            succeeded_count=succeeded_count,
            rejected_count=rejected_count,
            failed_count=failed_count,
            success_rate=self._rate(succeeded_count, completed_count),
            rejection_rate=self._rate(
                rejected_count,
                completed_count,
            ),
            failure_rate=self._rate(failed_count, completed_count),
            total_latency_p50_ms=self._percentile(durations, 0.50),
            total_latency_p95_ms=self._percentile(durations, 0.95),
        )

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float | None:
        if denominator == 0:
            return None
        return numerator / denominator

    @staticmethod
    def _percentile(
        values: list[int],
        percentile: float,
    ) -> float | None:
        if not values:
            return None

        index = (len(values) - 1) * percentile
        lower_index = int(index)
        upper_index = min(lower_index + 1, len(values) - 1)
        fraction = index - lower_index
        return (
            values[lower_index]
            + (values[upper_index] - values[lower_index]) * fraction
        )
