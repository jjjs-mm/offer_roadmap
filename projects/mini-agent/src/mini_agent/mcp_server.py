from mcp.server import MCPServer
from mini_agent.tools import (
    analyze_portfolio as run_analyze_portfolio,
)
from mini_agent.tools import calculator as run_calculator
from mini_agent.tools import read_file as run_read_file
from mini_agent.tools import list_files as run_list_files
from mini_agent.tools import run_python as run_run_python
from mini_agent.tools import (
    get_portfolio as run_get_portfolio,
)
from mini_agent.tools import (
    assess_portfolio_risk as run_assess_portfolio_risk,
)

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
def analyze_portfolio(csv_content: str) -> str:
    """
    分析基金或其他资产的持仓 CSV。

    CSV 必须包含 name、asset_type、quantity、price 四列。
    返回总市值、各持仓权重、最大持仓、资产配置比例和 HHI 集中度。
    """
    return run_analyze_portfolio(csv_content)

@mcp.tool()
def get_portfolio(portfolio_id: str) -> str:
    """
    根据 portfolio_id 查询已经保存的持仓分析。

    当用户已经上传过持仓文件并提供分析 ID 时使用，
    不需要用户再次提交完整 CSV。
    """
    return run_get_portfolio(portfolio_id)

@mcp.tool()
def assess_portfolio_risk(
    portfolio_id: str,
) -> str:
    """
    根据 portfolio_id 生成确定性持仓风险报告。

    返回整体规则等级、触发的风险信号、实际观测值、
    触发阈值和免责声明。风险数值由代码计算，不由模型推测。
    """
    return run_assess_portfolio_risk(portfolio_id)

@mcp.tool()
def list_files() -> str:
    """列出 mini-agent 的 data 目录中可读取的文件路径。"""
    return run_list_files()


@mcp.tool()
def run_python(
    code: str,
    input_files: list[dict[str, str]] | None = None,
) -> str:
    """
    在本机受限 Docker 沙箱中执行 Python 代码。

    输入文件通过 input_files 传入，并以只读方式挂载到 /inputs。
    每个文件包含 path 和 content 两个字段。
    只在用户明确要求运行代码时使用。
    """
    return run_run_python(
        code=code,
        input_files=input_files,
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")
