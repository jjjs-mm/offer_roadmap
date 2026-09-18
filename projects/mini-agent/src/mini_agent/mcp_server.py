from mcp.server import MCPServer

from mini_agent.tools import calculator as run_calculator
from mini_agent.tools import read_file as run_read_file
from mini_agent.tools import list_files as run_list_files

mcp = MCPServer("mini-agent-tools")


@mcp.tool()
def calculator(expression: str) -> str:
    """计算只包含加、减、乘、除和括号的数学表达式。"""
    return run_calculator(expression)


@mcp.tool()
def read_file(path: str) -> str:
    """读取 mini-agent 的 data 目录中的文本文件。"""
    return run_read_file(path)


@mcp.tool()
def list_files() -> str:
    """列出 mini-agent 的 data 目录中可读取的文件路径。"""
    return run_list_files()


if __name__ == "__main__":
    mcp.run(transport="stdio")