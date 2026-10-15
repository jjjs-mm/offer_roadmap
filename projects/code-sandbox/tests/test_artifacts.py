import io
import tarfile

from code_sandbox.artifacts import parse_workspace_archive


def test_rejects_archive_path_outside_workspace() -> None:
    archive = io.BytesIO()
    content = b"secret"

    with tarfile.open(fileobj=archive, mode="w") as tar:
        entry = tarfile.TarInfo("workspace/../outside.txt")
        entry.size = len(content)
        tar.addfile(entry, io.BytesIO(content))

    artifacts, skipped = parse_workspace_archive(archive.getvalue())

    assert artifacts == []
    assert skipped is True
