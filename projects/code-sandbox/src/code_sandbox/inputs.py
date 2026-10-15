import io
import tarfile
from pathlib import Path, PurePosixPath

from code_sandbox.models import InputFile


MAX_INPUT_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 4 * 1024 * 1024


def build_input_archive(input_files: list[InputFile]) -> bytes:
    archive_buffer = io.BytesIO()
    seen_paths: set[str] = set()
    total_bytes = 0

    with tarfile.open(fileobj=archive_buffer, mode="w") as archive:
        for input_file in input_files:
            path = PurePosixPath(input_file.path)

            if (
                path.is_absolute()
                or path.as_posix() in {"", "."}
                or ".." in path.parts
                or "\\" in input_file.path
                or "\0" in input_file.path
            ):
                raise ValueError(f"不安全的输入文件路径: {input_file.path}")

            normalized_path = path.as_posix()
            if normalized_path in seen_paths:
                raise ValueError(f"输入文件路径重复: {normalized_path}")
            seen_paths.add(normalized_path)

            content = input_file.content.encode("utf-8")
            if len(content) > MAX_INPUT_FILE_BYTES:
                raise ValueError(f"输入文件过大: {normalized_path}")

            total_bytes += len(content)
            if total_bytes > MAX_TOTAL_INPUT_BYTES:
                raise ValueError("输入文件总大小超过限制")

            file_info = tarfile.TarInfo(name=normalized_path)
            file_info.size = len(content)
            file_info.mode = 0o444
            file_info.uid = 0
            file_info.gid = 0
            file_info.mtime = 0

            archive.addfile(file_info, io.BytesIO(content))

    return archive_buffer.getvalue()

def materialize_input_files(
    root: Path,
    input_files: list[InputFile],
) -> None:
    archive_bytes = build_input_archive(input_files)

    with tarfile.open(
        fileobj=io.BytesIO(archive_bytes),
        mode="r:",
    ) as archive:
        archive.extractall(
            path=root,
            filter="data",
        )

    root.chmod(0o755)