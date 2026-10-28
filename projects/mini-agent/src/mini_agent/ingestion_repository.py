import os
import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel


PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_INGESTION_DATABASE_PATH = Path(
    os.getenv(
        "INGESTION_DATABASE_PATH",
        str(PROJECT_DIR / "data" / "ingestions.sqlite3"),
    )
)

IngestionStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
]


class IngestionJobRecord(BaseModel):
    ingestion_id: str
    filename: str
    content_sha256: str
    status: IngestionStatus
    attempt_count: int
    source_url: str | None = None
    published_at: str | None = None
    document_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class IngestionRepository:
    """持久化上传原文件和导入状态，支持幂等提交与失败重试。"""

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
                CREATE TABLE IF NOT EXISTS knowledge_ingestions (
                    ingestion_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL UNIQUE,
                    file_bytes BLOB NOT NULL,
                    source_url TEXT,
                    published_at TEXT,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    document_id TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
                """
            )

    def enqueue(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        source_url: str | None,
        published_at: str | None,
    ) -> tuple[IngestionJobRecord, bool]:
        """返回任务与是否新建；相同内容只会创建一条导入任务。"""
        content_sha256 = sha256(file_bytes).hexdigest()
        now = datetime.now(timezone.utc)
        record = IngestionJobRecord(
            ingestion_id=uuid4().hex,
            filename=filename,
            content_sha256=content_sha256,
            source_url=source_url,
            published_at=published_at,
            status="queued",
            attempt_count=0,
            created_at=now,
        )

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO knowledge_ingestions (
                        ingestion_id, filename, content_sha256, file_bytes,
                        source_url, published_at, status, attempt_count,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.ingestion_id,
                        record.filename,
                        record.content_sha256,
                        file_bytes,
                        record.source_url,
                        record.published_at,
                        record.status,
                        record.attempt_count,
                        record.created_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.get_by_content_sha256(content_sha256)
            if existing is None:
                raise RuntimeError("导入任务冲突后无法读取已有任务")
            return existing, False

        return record, True

    def get(self, ingestion_id: str) -> IngestionJobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM knowledge_ingestions
                WHERE ingestion_id = ?
                """,
                (ingestion_id,),
            ).fetchone()
        return self._to_record(row) if row is not None else None

    def get_by_content_sha256(
        self,
        content_sha256: str,
    ) -> IngestionJobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM knowledge_ingestions
                WHERE content_sha256 = ?
                """,
                (content_sha256,),
            ).fetchone()
        return self._to_record(row) if row is not None else None

    def claim(self, ingestion_id: str) -> tuple[IngestionJobRecord, bytes] | None:
        """原子地把 queued 任务转为 running，避免重复执行。"""
        started_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE knowledge_ingestions
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    started_at = ?,
                    completed_at = NULL,
                    error_message = NULL
                WHERE ingestion_id = ? AND status = 'queued'
                """,
                (started_at.isoformat(), ingestion_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT * FROM knowledge_ingestions
                WHERE ingestion_id = ?
                """,
                (ingestion_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("已领取的导入任务不存在")
        return self._to_record(row), row["file_bytes"]

    def succeed(
        self,
        ingestion_id: str,
        *,
        document_id: str,
    ) -> IngestionJobRecord:
        return self._finish(
            ingestion_id,
            status="succeeded",
            document_id=document_id,
            error_message=None,
        )

    def fail(
        self,
        ingestion_id: str,
        *,
        error_message: str,
    ) -> IngestionJobRecord:
        return self._finish(
            ingestion_id,
            status="failed",
            document_id=None,
            error_message=error_message,
        )

    def retry(self, ingestion_id: str) -> IngestionJobRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE knowledge_ingestions
                SET status = 'queued', completed_at = NULL
                WHERE ingestion_id = ? AND status = 'failed'
                """,
                (ingestion_id,),
            )
            if cursor.rowcount == 0:
                raise ValueError("只有失败的导入任务可以重试")

        record = self.get(ingestion_id)
        if record is None:
            raise RuntimeError("重试成功但无法读取导入任务")
        return record

    def _finish(
        self,
        ingestion_id: str,
        *,
        status: Literal["succeeded", "failed"],
        document_id: str | None,
        error_message: str | None,
    ) -> IngestionJobRecord:
        completed_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE knowledge_ingestions
                SET status = ?, document_id = ?, error_message = ?,
                    completed_at = ?
                WHERE ingestion_id = ? AND status = 'running'
                """,
                (
                    status,
                    document_id,
                    error_message,
                    completed_at.isoformat(),
                    ingestion_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("导入任务不处于执行中状态")

        record = self.get(ingestion_id)
        if record is None:
            raise RuntimeError("更新成功但无法读取导入任务")
        return record

    @staticmethod
    def _to_record(row: sqlite3.Row) -> IngestionJobRecord:
        return IngestionJobRecord(
            ingestion_id=row["ingestion_id"],
            filename=row["filename"],
            content_sha256=row["content_sha256"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            source_url=row["source_url"],
            published_at=row["published_at"],
            document_id=row["document_id"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"])
                if row["started_at"] is not None
                else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"] is not None
                else None
            ),
        )
