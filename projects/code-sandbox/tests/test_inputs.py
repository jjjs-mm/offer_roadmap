import io
import tarfile

import pytest

from code_sandbox.inputs import (
    MAX_INPUT_FILE_BYTES,
    build_input_archive,
)
from code_sandbox.models import InputFile


def test_builds_read_only_input_archive() -> None:
    archive_bytes = build_input_archive(
        [
            InputFile(
                path="portfolio.csv",
                content="name,value\n基金A,1000\n",
            )
        ]
    )

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        member = archive.getmember("portfolio.csv")
        file_obj = archive.extractfile(member)

        assert member.mode == 0o444
        assert file_obj is not None
        assert file_obj.read().decode("utf-8") == "name,value\n基金A,1000\n"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../secret.txt",
        "data/../../secret.txt",
        r"data\secret.txt",
    ],
)
def test_rejects_unsafe_input_path(path: str) -> None:
    with pytest.raises(ValueError, match="不安全"):
        build_input_archive([InputFile(path=path, content="secret")])


def test_rejects_duplicate_normalized_path() -> None:
    with pytest.raises(ValueError, match="重复"):
        build_input_archive(
            [
                InputFile(path="data/./portfolio.csv", content="first"),
                InputFile(path="data/portfolio.csv", content="second"),
            ]
        )


def test_rejects_oversized_input_file() -> None:
    with pytest.raises(ValueError, match="文件过大"):
        build_input_archive(
            [
                InputFile(
                    path="large.csv",
                    content="x" * (MAX_INPUT_FILE_BYTES + 1),
                )
            ]
        )