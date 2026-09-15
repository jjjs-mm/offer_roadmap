from mcp.server import MCPServer

from mini_agent.tools import calculator as run_calculator
from mini_agent.tools import read_file as run_read_file


mcp = MCPServer("mini-agent-tools")


@mcp.tool()
def calculator(expression: str) -> str:
    """计算只包含加、减、乘、除和括号的数学表达式。"""
    return run_calculator(expression)


@mcp.tool()
def read_file(path: str) -> str:
    """读取 mini-agent 的 data 目录中的文本文件。"""
    return run_read_file(path)


if __name__ == "__main__":
    mcp.run(transport="stdio")