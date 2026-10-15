"""模型负责决定算什么，这段代码负责只算数学、不跑别的代码"""

import ast
import json
import operator
from pathlib import Path

from code_sandbox.models import ExecutionRequest, InputFile
from code_sandbox.runner import DockerRunner
from mini_agent.portfolio import analyze_portfolio_csv
from mini_agent.portfolio_repository import (
    DEFAULT_PORTFOLIO_DATABASE_PATH,
    PortfolioRepository,
)
from mini_agent.portfolio_risk import (
    PortfolioRiskAssessment,
    assess_portfolio_risk as build_portfolio_risk_report,
)

# 读文件工具只允许访问这个目录
READ_ROOT = Path(__file__).resolve().parents[2] / "data"
TOOL_OUTPUT_CHARS = 2000
portfolio_repository = PortfolioRepository(
    DEFAULT_PORTFOLIO_DATABASE_PATH
)

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Expr):
        return _eval(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand)
    if isinstance(node, ast.BinOp):
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):  # 这就是 * ，不能漏
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("除数不能为 0")
            return left / right
        raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
    raise ValueError(f"不支持的节点: {type(node).__name__}")


def calculator(expression: str) -> str:
    tree = ast.parse(expression, mode="eval")
    return str(_eval(tree))


def read_file(path: str) -> str:
    root = READ_ROOT.resolve()
    target = (root / path).resolve()

    if not target.is_relative_to(root):
        raise ValueError("不允许读取 data 目录之外的文件")

    return target.read_text(encoding="utf-8")


def list_files() -> str:
    root = READ_ROOT.resolve()

    paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )

    return "\n".join(paths)

def analyze_portfolio(csv_content: str) -> str:
    """
    分析持仓 CSV，返回结构化 JSON。

    CSV 必须包含：
    name、asset_type、quantity、price。
    """
    analysis = analyze_portfolio_csv(csv_content)
    return analysis.model_dump_json()

def get_portfolio(portfolio_id: str) -> str:
    """
    根据 portfolio_id 查询已经保存的持仓分析。
    """
    record = portfolio_repository.get(portfolio_id)

    if record is None:
        raise ValueError("未找到持仓分析记录")

    return record.model_dump_json()

def assess_portfolio_risk(
    portfolio_id: str,
) -> str:
    """
    根据已保存的持仓分析生成确定性风险报告。
    """
    record = portfolio_repository.get(portfolio_id)

    if record is None:
        raise ValueError("未找到持仓分析记录")

    assessment = PortfolioRiskAssessment(
        portfolio_id=portfolio_id,
        report=build_portfolio_risk_report(
            record.analysis
        ),
    )

    return assessment.model_dump_json()

def run_python(
    code: str,
    input_files: list[dict[str, str]] | None = None,
) -> str:
    """在本机受限 Docker 容器中执行 Python，并返回精简结果。"""
    files = [
        InputFile.model_validate(input_file)
        for input_file in (input_files or [])
    ]

    request = ExecutionRequest(
        code=code,
        input_files=files,
    )

    runner = DockerRunner()
    try:
        result = runner.run(request)
    finally:
        runner.client.close()

    return json.dumps(
        {
            "execution_id": result.execution_id,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "stdout": result.stdout[:TOOL_OUTPUT_CHARS],
            "stderr": result.stderr[:TOOL_OUTPUT_CHARS],
            "tool_preview_truncated": (
                len(result.stdout) > TOOL_OUTPUT_CHARS
                or len(result.stderr) > TOOL_OUTPUT_CHARS
            ),
            "duration_ms": result.duration_ms,
            "artifacts": [
                {
                    "path": artifact.path,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in result.artifacts
            ],
            "artifacts_skipped": result.artifacts_skipped,
        },
        ensure_ascii=False,
    )