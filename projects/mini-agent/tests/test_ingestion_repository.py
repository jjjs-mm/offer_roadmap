from mini_agent.ingestion_repository import IngestionRepository


def test_enqueue_is_idempotent_by_file_hash(tmp_path) -> None:
    repository = IngestionRepository(tmp_path / "ingestions.sqlite3")

    first, first_created = repository.enqueue(
        filename="fund.md",
        file_bytes=b"investment objective",
        source_url="https://fund.example/fund.md",
        published_at="2026-10-28",
    )
    second, second_created = repository.enqueue(
        filename="renamed-fund.md",
        file_bytes=b"investment objective",
        source_url=None,
        published_at=None,
    )

    assert first_created is True
    assert second_created is False
    assert second.ingestion_id == first.ingestion_id
    assert second.status == "queued"


def test_job_can_fail_then_retry_and_succeed(tmp_path) -> None:
    repository = IngestionRepository(tmp_path / "ingestions.sqlite3")
    job, _ = repository.enqueue(
        filename="fund.md",
        file_bytes=b"investment objective",
        source_url=None,
        published_at=None,
    )

    claimed = repository.claim(job.ingestion_id)
    assert claimed is not None
    running, file_bytes = claimed
    assert running.status == "running"
    assert running.attempt_count == 1
    assert file_bytes == b"investment objective"

    failed = repository.fail(
        job.ingestion_id,
        error_message="PDF 无法解析",
    )
    assert failed.status == "failed"
    assert failed.error_message == "PDF 无法解析"

    queued = repository.retry(job.ingestion_id)
    assert queued.status == "queued"
    assert queued.attempt_count == 1

    assert repository.claim(job.ingestion_id) is not None
    succeeded = repository.succeed(
        job.ingestion_id,
        document_id="document-1",
    )
    assert succeeded.status == "succeeded"
    assert succeeded.attempt_count == 2
    assert succeeded.document_id == "document-1"
