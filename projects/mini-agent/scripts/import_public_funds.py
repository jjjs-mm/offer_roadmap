import argparse
import json
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

from mini_agent.knowledge_repository import (
    DEFAULT_KNOWLEDGE_DATABASE_PATH,
    KnowledgeRepository,
)
from mini_agent.pdf_ingestion import extract_pdf_pages


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_DIR / "data" / "public_funds" / "manifest.json"
DEFAULT_DOWNLOAD_DIR = PROJECT_DIR / "data" / "public_funds" / "raw"
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024


def download_pdf(url: str) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "mini-agent-public-fund-importer/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get_content_type()
        file_bytes = response.read(MAX_DOWNLOAD_BYTES + 1)

    if len(file_bytes) > MAX_DOWNLOAD_BYTES:
        raise ValueError("公开 PDF 超过 10 MiB 限制")
    if content_type != "application/pdf" and not file_bytes.startswith(b"%PDF"):
        raise ValueError(f"下载结果不是 PDF：{content_type}")
    return file_bytes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下载、校验并导入基金公司官网公开 PDF"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--download-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_KNOWLEDGE_DATABASE_PATH,
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.download_dir.mkdir(parents=True, exist_ok=True)
    repository = KnowledgeRepository(args.database)
    imported: list[dict[str, object]] = []

    for document in manifest["documents"]:
        file_path = args.download_dir / document["filename"]
        file_bytes = file_path.read_bytes() if file_path.exists() else download_pdf(
            document["source_url"]
        )
        actual_sha256 = sha256(file_bytes).hexdigest()
        if actual_sha256 != document["sha256"]:
            raise ValueError(
                f"{document['filename']} 的 SHA-256 与清单不一致"
            )
        if not file_path.exists():
            file_path.write_bytes(file_bytes)

        pages = extract_pdf_pages(file_bytes)
        record = repository.get_by_content_sha256(actual_sha256)
        already_imported = record is not None
        if record is None:
            record = repository.save(
                filename=document["filename"],
                file_bytes=file_bytes,
                text="\n\n".join(pages),
                pages=pages,
                source_url=document["source_url"],
                published_at=document["published_at"],
            )
        imported.append(
            {
                "document_id": record.document_id,
                "filename": record.filename,
                "page_count": len(pages),
                "chunk_count": record.chunk_count,
                "sha256": record.content_sha256,
                "already_imported": already_imported,
            }
        )

    print(json.dumps(imported, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
