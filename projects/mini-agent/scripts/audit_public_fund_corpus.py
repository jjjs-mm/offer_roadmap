"""Print validated coverage information for the public-fund PDF corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mini_agent.public_fund_corpus import summarize_manifest, validate_manifest


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_DIR / "data" / "public_funds" / "manifest.json"
DEFAULT_RAW_DIRECTORY = PROJECT_DIR / "data" / "public_funds" / "raw"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验公开基金 PDF 语料并输出覆盖度摘要"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIRECTORY)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate_manifest(manifest, args.raw_dir)
    print(json.dumps(summarize_manifest(manifest), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
