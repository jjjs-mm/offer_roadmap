"""模型负责决定算什么，这段代码负责只算数学、不跑别的代码"""

import ast
import operator
from pathlib import Path
# 读文件工具只允许访问这个目录
READ_ROOT = Path(__file__).resolve().parents[2] / "data"

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