import base64
import io
import tarfile
from contextlib import suppress
from pathlib import PurePosixPath

from docker.models.containers import Container

from code_sandbox.models import FileArtifact


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_FILE_BYTES = 4 * 1024 * 1024
ARCHIVE_SCRIPT = (
    "import sys, tarfile\n"
    "with tarfile.open(fileobj=sys.stdout.buffer, mode='w|', dereference=False) as tar:\n"
    "    tar.add('/workspace', arcname='workspace')\n"
)


def read_workspace_archive(container: Container) -> bytes | None:
    api = container.client.api
    created = api.exec_create(
        container.id,
        ["python", "-c", ARCHIVE_SCRIPT],
        stdout=True,
        stderr=True,
        user="0:0",
        workdir="/",
    )
    chunks = api.exec_start(created["Id"], stream=True, demux=True)
    archive = bytearray()
    oversized = False

    try:
        for stdout_chunk, _stderr_chunk in chunks:
            if not stdout_chunk:
                continue
            if len(archive) + len(stdout_chunk) > MAX_ARCHIVE_BYTES:
                oversized = True
                break
            archive.extend(stdout_chunk)
    finally:
        with suppress(OSError):
            chunks.close()

    if oversized:
        return None

    exit_code = api.exec_inspect(created["Id"])["ExitCode"]
    return None if exit_code != 0 else bytes(archive)


def parse_workspace_archive(archive: bytes) -> tuple[list[FileArtifact], bool]:
    artifacts: list[FileArtifact] = []
    total_bytes = 0
    skipped = False

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar:
            if member.isdir():
                continue

            if not member.isfile():
                skipped = True
                continue

            path = PurePosixPath(member.name)
            parts = path.parts
            if (
                path.is_absolute()
                or len(parts) < 2
                or parts[0] != "workspace"
                or ".." in parts
                or "\\" in member.name
            ):
                skipped = True
                continue

            if (
                len(artifacts) >= MAX_FILES
                or member.size < 0
                or member.size > MAX_FILE_BYTES
                or total_bytes + member.size > MAX_TOTAL_FILE_BYTES
            ):
                skipped = True
                continue

            file_obj = tar.extractfile(member)
            if file_obj is None:
                skipped = True
                continue

            content = file_obj.read(MAX_FILE_BYTES + 1)
            if len(content) != member.size:
                skipped = True
                continue

            artifacts.append(
                FileArtifact(
                    path="/".join(parts[1:]),
                    size_bytes=len(content),
                    content_base64=base64.b64encode(content).decode("ascii"),
                )
            )
            total_bytes += len(content)

    return artifacts, skipped
