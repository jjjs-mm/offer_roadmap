from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


def extract_pdf_pages(file_bytes: bytes) -> list[str]:
    """从 PDF 中提取逐页文本；扫描版 PDF 会被明确拒绝。"""
    try:
        reader = PdfReader(BytesIO(file_bytes))
    except (PdfReadError, ValueError) as error:
        raise ValueError("无法解析 PDF 文件") from error

    if reader.is_encrypted:
        raise ValueError("暂不支持加密 PDF")

    pages = [
        (page.extract_text() or "").strip()
        for page in reader.pages
    ]

    if not any(pages):
        raise ValueError(
            "PDF 中没有可提取文本，扫描版文件需要先进行 OCR"
        )

    return pages
