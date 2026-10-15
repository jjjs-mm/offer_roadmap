import argparse

from code_sandbox.models import ExecutionRequest
from code_sandbox.runner import DockerRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Python code inside a restricted Docker container."
    )
    parser.add_argument(
        "code",
        help="Python code to execute.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Maximum execution time in seconds.",
    )
    args = parser.parse_args()

    runner = DockerRunner()
    result = runner.run(
        ExecutionRequest(
            code=args.code,
            timeout_seconds=args.timeout,
        )
    )
    print(result.model_dump_json(indent=2))