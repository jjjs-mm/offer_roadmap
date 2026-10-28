from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    document_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    content: str = Field(min_length=1)


def chunk_document(
    *,
    document_id: str,
    source_name: str,
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[KnowledgeChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    if overlap < 0:
        raise ValueError("overlap 不能小于 0")

    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")

    normalized_text = text.replace("\r\n", "\n").strip()

    if not normalized_text:
        raise ValueError("文档内容不能为空")

    chunks: list[KnowledgeChunk] = []
    start = 0
    chunk_index = 0

    while start < len(normalized_text):
        end = min(start + chunk_size, len(normalized_text))

        chunks.append(
            KnowledgeChunk(
                document_id=document_id,
                source_name=source_name,
                chunk_index=chunk_index,
                content=normalized_text[start:end],
            )
        )

        if end == len(normalized_text):
            break

        start = end - overlap
        chunk_index += 1

    return chunks


def chunk_pages(
    *,
    document_id: str,
    source_name: str,
    pages: list[str],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[KnowledgeChunk]:
    """逐页切分文档，保证每个分块都能追溯到原 PDF 页码。"""
    chunks: list[KnowledgeChunk] = []

    for page_number, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue

        page_chunks = chunk_document(
            document_id=document_id,
            source_name=source_name,
            text=page_text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for page_chunk in page_chunks:
            chunks.append(
                page_chunk.model_copy(
                    update={
                        "chunk_index": len(chunks),
                        "page_number": page_number,
                    }
                )
            )

    if not chunks:
        raise ValueError("PDF 中没有可提取的文本")

    return chunks
