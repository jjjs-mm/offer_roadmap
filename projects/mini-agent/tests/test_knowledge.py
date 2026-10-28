import pytest

from mini_agent.knowledge import chunk_document, chunk_pages


def test_chunk_document_preserves_metadata_and_overlap() -> None:
    chunks = chunk_document(
        document_id="doc-001",
        source_name="fund_report.txt",
        text="甲乙丙丁戊己庚辛壬癸",
        chunk_size=4,
        overlap=1,
    )

    assert [chunk.content for chunk in chunks] == [
        "甲乙丙丁",
        "丁戊己庚",
        "庚辛壬癸",
    ]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]

    assert all(
        chunk.document_id == "doc-001"
        for chunk in chunks
    )
    assert all(
        chunk.source_name == "fund_report.txt"
        for chunk in chunks
    )


def test_chunk_document_rejects_empty_text() -> None:
    with pytest.raises(
        ValueError,
        match="文档内容不能为空",
    ):
        chunk_document(
            document_id="doc-001",
            source_name="empty.txt",
            text="   ",
            chunk_size=100,
            overlap=10,
        )


def test_chunk_document_rejects_invalid_overlap() -> None:
    with pytest.raises(
        ValueError,
        match="overlap 必须小于 chunk_size",
    ):
        chunk_document(
            document_id="doc-001",
            source_name="fund_report.txt",
            text="测试文档",
            chunk_size=4,
            overlap=4,
        )


def test_chunk_pages_preserves_pdf_page_numbers() -> None:
    chunks = chunk_pages(
        document_id="doc-pdf",
        source_name="fund.pdf",
        pages=["第一页内容", "", "第三页内容"],
        chunk_size=100,
        overlap=10,
    )

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.page_number for chunk in chunks] == [1, 3]
    assert [chunk.content for chunk in chunks] == [
        "第一页内容",
        "第三页内容",
    ]
