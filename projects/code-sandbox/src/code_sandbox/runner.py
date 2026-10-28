from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import suppress
from dataclasses import dataclass
import time
from uuid import uuid4
import docker
from docker.errors import DockerException
from code_sandbox.inputs import materialize_input_files
from pathlib import Path
from tempfile import TemporaryDirectory

from code_sandbox.artifacts import (
    parse_workspace_archive,
    read_workspace_archive,
)
from code_sandbox.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


MAX_OUTPUT_BYTES = 64 * 1024


@dataclass
class CodeExecution:
    exit_code: int
    stdout: bytes
    stderr: bytes
    output_truncated: bool = False


class DockerRunner:
    def __init__(self, image: str = "python:3.12-slim") -> None:
        self.client = docker.from_env()
        self.image = image

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        started_at = time.perf_counter()
        execution_id = uuid4().hex
        container = None
        input_directory = None

        try:
            volumes = {}

            if request.input_files:
                input_directory = TemporaryDirectory(
                    prefix="code-sandbox-input-"
                )
                input_path = Path(input_directory.name).resolve()
                materialize_input_files(input_path, request.input_files)

                volumes[str(input_path)] = {
                    "bind": "/inputs",
                    "mode": "ro",
                }
            container = self.client.containers.run(
                image=self.image,
                command=["sleep", "infinity"],
                working_dir="/workspace",
                detach=True,
                network_disabled=True,
                read_only=True,
                mem_limit="128m",
                nano_cpus=500_000_000,
                pids_limit=64,
                volumes=volumes,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                tmpfs={
                    "/tmp": "rw,noexec,nosuid,size=16m",
                    "/workspace": "rw,noexec,nosuid,size=16m,mode=1777",
                },
            )

            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    self._execute,
                    container.id,
                    request.code,
                )
                try:
                    execution = future.result(timeout=request.timeout_seconds)
                except FutureTimeoutError:
                    container.kill()
                    return ExecutionResult(  #超时分支
                       execution_id=execution_id,
                       status=ExecutionStatus.TIMED_OUT,
                       exit_code=-1,
                       stdout="",
                       stderr=(
                       f"Execution timed out after "
                       f"{request.timeout_seconds} seconds."
                       ),
                        duration_ms=self._duration_ms(started_at),
                    )

            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            if execution.output_truncated:
                return ExecutionResult(    #超输出限额分支
                   execution_id=execution_id,
                   status=ExecutionStatus.OUTPUT_LIMIT_EXCEEDED,
                   exit_code=-1,
                   stdout=execution.stdout.decode("utf-8", errors="replace"),
                   stderr=execution.stderr.decode("utf-8", errors="replace"),
                   duration_ms=self._duration_ms(started_at),
                )

            archive = read_workspace_archive(container)
            if archive is None:
                artifacts = []
                artifacts_skipped = True
            else:
                artifacts, artifacts_skipped = parse_workspace_archive(archive)

            return ExecutionResult(
                exit_code=execution.exit_code,
                stdout=execution.stdout.decode("utf-8", errors="replace"),
                stderr=execution.stderr.decode("utf-8", errors="replace"),
                duration_ms=self._duration_ms(started_at),
                artifacts=artifacts,
                artifacts_skipped=artifacts_skipped,
                execution_id=execution_id,
                status=(
                   ExecutionStatus.SUCCEEDED
                   if execution.exit_code == 0
                   else ExecutionStatus.RUNTIME_ERROR
                ),
            )
        except DockerException as error:
            return ExecutionResult(     #docker异常分支
                execution_id=execution_id,
                status=ExecutionStatus.INFRASTRUCTURE_ERROR,
                exit_code=-1,
                stdout="",
                stderr=f"Docker error: {error}",
                duration_ms=self._duration_ms(started_at),
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass
            if input_directory is not None:
                input_directory.cleanup()

    @staticmethod
    def _execute(container_id: str, code: str) -> CodeExecution:
        client = docker.from_env()
        output = None
        try:
            container = client.containers.get(container_id)
            created = client.api.exec_create(
                container.id,
                ["python", "-c", code],
                stdout=True,
                stderr=True,
                user="65534:65534",
                workdir="/workspace",
            )
            output = client.api.exec_start(created["Id"], stream=True, demux=True)
            stdout = bytearray()
            stderr = bytearray()

            for stdout_chunk, stderr_chunk in output:
                for chunk, destination in (
                    (stdout_chunk, stdout),
                    (stderr_chunk, stderr),
                ):
                    if not chunk:
                        continue
                    remaining = MAX_OUTPUT_BYTES - len(stdout) - len(stderr)
                    destination.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        container.kill()
                        return CodeExecution(
                            -1,
                            bytes(stdout),
                            bytes(stderr),
                            True,
                        )

            exit_code = client.api.exec_inspect(created["Id"])["ExitCode"]
            return CodeExecution(exit_code, bytes(stdout), bytes(stderr))
        finally:
            if output is not None:
                with suppress(OSError, DockerException):
                    output.close()
            client.close()

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return int((time.perf_counter() - started_at) * 1000)
