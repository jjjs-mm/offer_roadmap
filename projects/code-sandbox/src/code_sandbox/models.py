from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RUNTIME_ERROR = "runtime_error"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class InputFile(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    content: str


class ExecutionRequest(BaseModel):
    code: str = Field(min_length=1)
    language: Literal["python"] = "python"
    timeout_seconds: float = Field(default=3.0, gt=0, le=10)
    input_files: list[InputFile] = Field(default_factory=list, max_length=10)


class FileArtifact(BaseModel):
    path: str
    size_bytes: int = Field(ge=0)
    content_base64: str


class ExecutionResult(BaseModel):
    execution_id: str
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int = Field(ge=0)
    artifacts: list[FileArtifact] = Field(default_factory=list)
    artifacts_skipped: bool = False