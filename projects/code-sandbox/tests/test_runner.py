from code_sandbox.models import ExecutionRequest, ExecutionStatus, InputFile
from code_sandbox.runner import DockerRunner, MAX_OUTPUT_BYTES
from docker.errors import DockerException

def test_executes_python_code() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(code='print("hello sandbox")')
    )

    assert result.exit_code == 0
    assert result.stdout == "hello sandbox\n"
    assert result.stderr == ""
    assert result.status is ExecutionStatus.SUCCEEDED
    assert len(result.execution_id) == 32
    assert result.duration_ms >= 0


def test_runs_user_code_as_non_root() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(code="import os; print(os.getuid())")
    )

    assert result.exit_code == 0
    assert result.stdout == "65534\n"

def test_reads_input_file_inside_sandbox() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code=(
                "from pathlib import Path\n"
                'print(Path("/inputs/portfolio.csv").read_text(encoding="utf-8"))'
            ),
            input_files=[
                InputFile(
                    path="portfolio.csv",
                    content="name,value\nfund_a,1000",
                )
            ],
        )
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.stdout == "name,value\nfund_a,1000\n"

def test_returns_python_error() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(code="1 / 0")
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "ZeroDivisionError" in result.stderr
    assert result.status is ExecutionStatus.RUNTIME_ERROR


def test_stops_code_that_exceeds_timeout() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code="import time\ntime.sleep(5)",
            timeout_seconds=0.2,
        )
    )

    assert result.exit_code == -1
    assert result.status is ExecutionStatus.TIMED_OUT
    assert "timed out" in result.stderr

def test_blocks_writes_to_read_only_filesystem() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code='open("/blocked.txt", "w").write("should fail")'
        )
    )

    assert result.exit_code != 0
    assert "OSError" in result.stderr

def test_blocks_network_access() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code=(
                "import socket\n"
                'socket.create_connection(("1.1.1.1", 80), timeout=1)'
            )
        )
    )

    assert result.exit_code != 0
    assert "OSError" in result.stderr


def test_returns_file_artifact() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code='from pathlib import Path; Path("hello.txt").write_text("hi")'
        )
    )

    assert result.exit_code == 0
    assert result.artifacts_skipped is False
    assert len(result.artifacts) == 1
    assert result.artifacts[0].path == "hello.txt"
    assert result.artifacts[0].size_bytes == 2
    assert result.artifacts[0].content_base64 == "aGk="


def test_does_not_return_symlink_target() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code='from pathlib import Path; Path("link").symlink_to("/etc/passwd")'
        )
    )

    assert result.exit_code == 0
    assert result.artifacts == []
    assert result.artifacts_skipped is True


def test_skips_file_over_artifact_size_limit() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code='from pathlib import Path; Path("big.bin").write_bytes(b"x" * (1024 * 1024 + 1))'
        )
    )

    assert result.exit_code == 0
    assert result.artifacts == []
    assert result.artifacts_skipped is True


def test_stops_code_that_exceeds_stdout_limit() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(code=f'print("x" * {MAX_OUTPUT_BYTES + 1}, end="")')
    )

    assert result.exit_code == -1
    assert result.status is ExecutionStatus.OUTPUT_LIMIT_EXCEEDED
    assert len(result.stdout.encode()) == MAX_OUTPUT_BYTES
    assert result.artifacts == []


def test_stdout_and_stderr_share_output_limit() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code=(
                "import sys\n"
                'sys.stdout.write("x" * 40000)\n'
                "sys.stdout.flush()\n"
                'sys.stderr.write("e" * 40000)\n'
                "sys.stderr.flush()\n"
            )
        )
    )

    assert result.exit_code == -1
    assert result.status is ExecutionStatus.OUTPUT_LIMIT_EXCEEDED
    assert len(result.stdout.encode()) + len(result.stderr.encode()) == MAX_OUTPUT_BYTES

def test_returns_infrastructure_error(monkeypatch) -> None:
    class FailingContainers:
        def run(self, **kwargs):
            raise DockerException("daemon unavailable")

    class FakeDockerClient:
        containers = FailingContainers()

    monkeypatch.setattr(
        "code_sandbox.runner.docker.from_env",
        lambda: FakeDockerClient(),
    )

    runner = DockerRunner()
    result = runner.run(
        ExecutionRequest(code='print("hello")')
    )

    assert result.status is ExecutionStatus.INFRASTRUCTURE_ERROR
    assert result.exit_code == -1
    assert "daemon unavailable" in result.stderr
    assert len(result.execution_id) == 32

def test_input_file_is_read_only() -> None:
    runner = DockerRunner()

    result = runner.run(
        ExecutionRequest(
            code=(
                "from pathlib import Path\n"
                'Path("/inputs/portfolio.csv").write_text("changed")'
            ),
            input_files=[
                InputFile(
                    path="portfolio.csv",
                    content="original",
                )
            ],
        )
    )

    assert result.status is ExecutionStatus.RUNTIME_ERROR
    assert "Read-only file system" in result.stderr
