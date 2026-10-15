import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import os
from pydantic import BaseModel

from mini_agent.portfolio import PortfolioAnalysis

PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_PORTFOLIO_DATABASE_PATH = Path(
    os.getenv(
        "PORTFOLIO_DATABASE_PATH",
        str(PROJECT_DIR / "data" / "portfolios.sqlite3"),
    )
)

class PortfolioRecord(BaseModel):
    portfolio_id: str
    filename: str
    content_sha256: str
    created_at: datetime
    analysis: PortfolioAnalysis


class PortfolioRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolios (
                    portfolio_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    analysis_json TEXT NOT NULL
                )
                """
            )

    def save(
        self,
        filename: str,
        file_bytes: bytes,
        analysis: PortfolioAnalysis,
    ) -> PortfolioRecord:
        record = PortfolioRecord(
            portfolio_id=uuid4().hex,
            filename=filename,
            content_sha256=sha256(file_bytes).hexdigest(),
            created_at=datetime.now(timezone.utc),
            analysis=analysis,
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolios (
                    portfolio_id,
                    filename,
                    content_sha256,
                    created_at,
                    analysis_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.portfolio_id,
                    record.filename,
                    record.content_sha256,
                    record.created_at.isoformat(),
                    record.analysis.model_dump_json(),
                ),
            )

        return record

    def get(self, portfolio_id: str) -> PortfolioRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    portfolio_id,
                    filename,
                    content_sha256,
                    created_at,
                    analysis_json
                FROM portfolios
                WHERE portfolio_id = ?
                """,
                (portfolio_id,),
            ).fetchone()

        if row is None:
            return None

        return PortfolioRecord(
            portfolio_id=row["portfolio_id"],
            filename=row["filename"],
            content_sha256=row["content_sha256"],
            created_at=datetime.fromisoformat(row["created_at"]),
            analysis=PortfolioAnalysis.model_validate_json(
                row["analysis_json"]
            ),
        )