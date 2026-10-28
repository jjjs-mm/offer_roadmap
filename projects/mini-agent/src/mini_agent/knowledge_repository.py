import os
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from mini_agent.knowledge import (
    KnowledgeChunk,
    chunk_document,
    chunk_pages,
)
from mini_agent.retrieval import rank_chunks
from mini_agent.semantic_retrieval import (
    DEFAULT_MINIMUM_VECTOR_SCORE,
    rank_chunks_by_vector,
    rank_chunks_hybrid,
)


PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_KNOWLEDGE_DATABASE_PATH = Path(
    os.getenv(
        "KNOWLEDGE_DATABASE_PATH",
        str(PROJECT_DIR / "data" / "knowledge.sqlite3"),
    )
)


class KnowledgeDocumentRecord(BaseModel):
    document_id: str
    filename: str
    content_sha256: str
    created_at: datetime
    source_url: str | None = None
    published_at: str | None = None
    chunk_count: int
    chunks: list[KnowledgeChunk]


class KnowledgeRepository:
    def __init__(
        self,
        database_path: Path,
        embed_texts: Callable[
            [list[str]],
            list[list[float]],
        ] | None = None,
    ) -> None:
        self.database_path = database_path
        self.embed_texts = embed_texts
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_database(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL
                )
                """
            )

            document_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(knowledge_documents)"
                )
            }
            if "source_url" not in document_columns:
                connection.execute(
                    "ALTER TABLE knowledge_documents "
                    "ADD COLUMN source_url TEXT"
                )
            if "published_at" not in document_columns:
                connection.execute(
                    "ALTER TABLE knowledge_documents "
                    "ADD COLUMN published_at TEXT"
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY (
                        document_id,
                        chunk_index
                    ),
                    FOREIGN KEY (document_id)
                        REFERENCES knowledge_documents(document_id)
                        ON DELETE CASCADE
                )
                """
            )

            chunk_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(knowledge_chunks)"
                )
            }
            if "page_number" not in chunk_columns:
                connection.execute(
                    "ALTER TABLE knowledge_chunks "
                    "ADD COLUMN page_number INTEGER"
                )

    def save(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        text: str,
        pages: list[str] | None = None,
        source_url: str | None = None,
        published_at: str | None = None,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> KnowledgeDocumentRecord:
        document_id = uuid4().hex

        if pages is None:
            chunks = chunk_document(
                document_id=document_id,
                source_name=filename,
                text=text,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        else:
            chunks = chunk_pages(
                document_id=document_id,
                source_name=filename,
                pages=pages,
                chunk_size=chunk_size,
                overlap=overlap,
            )

        record = KnowledgeDocumentRecord(
            document_id=document_id,
            filename=filename,
            content_sha256=sha256(file_bytes).hexdigest(),
            created_at=datetime.now(timezone.utc),
            source_url=source_url,
            published_at=published_at,
            chunk_count=len(chunks),
            chunks=chunks,
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id,
                    filename,
                    content_sha256,
                    created_at,
                    source_url,
                    published_at,
                    chunk_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.document_id,
                    record.filename,
                    record.content_sha256,
                    record.created_at.isoformat(),
                    record.source_url,
                    record.published_at,
                    record.chunk_count,
                ),
            )

            connection.executemany(
                """
                INSERT INTO knowledge_chunks (
                    document_id,
                    chunk_index,
                    page_number,
                    content
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.page_number,
                        chunk.content,
                    )
                    for chunk in record.chunks
                ],
            )

        return record

    def get(
        self,
        document_id: str,
    ) -> KnowledgeDocumentRecord | None:
        with self._connect() as connection:
            document_row = connection.execute(
                """
                SELECT
                    document_id,
                    filename,
                    content_sha256,
                    created_at,
                    source_url,
                    published_at,
                    chunk_count
                FROM knowledge_documents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()

            if document_row is None:
                return None

            chunk_rows = connection.execute(
                """
                SELECT
                    chunk_index,
                    page_number,
                    content
                FROM knowledge_chunks
                WHERE document_id = ?
                ORDER BY chunk_index
                """,
                (document_id,),
            ).fetchall()

        chunks = [
            KnowledgeChunk(
                document_id=document_row["document_id"],
                source_name=document_row["filename"],
                chunk_index=row["chunk_index"],
                page_number=row["page_number"],
                content=row["content"],
            )
            for row in chunk_rows
        ]

        return KnowledgeDocumentRecord(
            document_id=document_row["document_id"],
            filename=document_row["filename"],
            content_sha256=document_row["content_sha256"],
            created_at=datetime.fromisoformat(
                document_row["created_at"]
            ),
            source_url=document_row["source_url"],
            published_at=document_row["published_at"],
            chunk_count=document_row["chunk_count"],
            chunks=chunks,
        )

    def get_by_content_sha256(
        self,
        content_sha256: str,
    ) -> KnowledgeDocumentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id
                FROM knowledge_documents
                WHERE content_sha256 = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (content_sha256,),
            ).fetchone()

        if row is None:
            return None
        return self.get(row["document_id"])

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[KnowledgeChunk]:
        keyword = query.strip()

        if not keyword:
            raise ValueError("查询词不能为空")

        if limit < 1:
            raise ValueError("limit 必须大于 0")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    chunks.document_id,
                    documents.filename,
                    chunks.chunk_index,
                    chunks.page_number,
                    chunks.content
                FROM knowledge_chunks AS chunks
                JOIN knowledge_documents AS documents
                    ON documents.document_id = chunks.document_id
                WHERE instr(chunks.content, ?) > 0
                ORDER BY
                    documents.created_at DESC,
                    chunks.document_id,
                    chunks.chunk_index
                LIMIT ?
                """,
                (keyword, limit),
            ).fetchall()

        return [
            KnowledgeChunk(
                document_id=row["document_id"],
                source_name=row["filename"],
                chunk_index=row["chunk_index"],
                page_number=row["page_number"],
                content=row["content"],
            )
            for row in rows
        ]

    def search_ngrams(
        self,
        query: str,
        limit: int = 5,
    ) -> list[KnowledgeChunk]:
        if not query.strip():
            raise ValueError("查询词不能为空")
        if limit < 1:
            raise ValueError("limit 必须大于 0")

        chunks = self._all_chunks()
        return rank_chunks(query, chunks, limit=limit)

    def _all_chunks(self) -> list[KnowledgeChunk]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    chunks.document_id,
                    documents.filename,
                    chunks.chunk_index,
                    chunks.page_number,
                    chunks.content
                FROM knowledge_chunks AS chunks
                JOIN knowledge_documents AS documents
                    ON documents.document_id = chunks.document_id
                ORDER BY
                    documents.created_at DESC,
                    chunks.document_id,
                    chunks.chunk_index
                """
            ).fetchall()

        return [
            KnowledgeChunk(
                document_id=row["document_id"],
                source_name=row["filename"],
                chunk_index=row["chunk_index"],
                page_number=row["page_number"],
                content=row["content"],
            )
            for row in rows
        ]

    def search_vectors(
        self,
        query: str,
        limit: int = 5,
        minimum_score: float = DEFAULT_MINIMUM_VECTOR_SCORE,
    ) -> list[KnowledgeChunk]:
        if self.embed_texts is None:
            raise RuntimeError("未配置向量模型")
        return rank_chunks_by_vector(
            query,
            self._all_chunks(),
            self.embed_texts,
            limit=limit,
            minimum_score=minimum_score,
        )

    def search_hybrid(
        self,
        query: str,
        limit: int = 5,
        minimum_vector_score: float = DEFAULT_MINIMUM_VECTOR_SCORE,
    ) -> list[KnowledgeChunk]:
        if self.embed_texts is None:
            raise RuntimeError("未配置向量模型")
        return rank_chunks_hybrid(
            query,
            self._all_chunks(),
            self.embed_texts,
            limit=limit,
            minimum_vector_score=minimum_vector_score,
        )
