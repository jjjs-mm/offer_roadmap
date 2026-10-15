import json

import pytest
from mcp import Client

from code_sandbox.models import ExecutionResult, ExecutionStatus
from mini_agent import tools
from mini_agent.mcp_server import mcp
from decimal import Decimal
from mini_agent.portfolio import analyze_portfolio_csv
from mini_agent.portfolio_repository import PortfolioRepository


@pytest.mark.asyncio
async def test_mcp_lists_registered_tools():
    async with Client(mcp) as client:
        result = await client.list_tools()

    tool_names = {tool.name for tool in result.tools}

    assert tool_names == {
    "calculator",
    "read_file",
    "list_files",
    "run_python",
    "analyze_portfolio",
    "get_portfolio",
    "assess_portfolio_risk",
}


@pytest.mark.asyncio
async def test_mcp_calculator():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "calculator",
            {"expression": "3 * (7 + 2)"},
        )

    assert result.is_error is False
    assert result.content[0].text == "27.0"


@pytest.mark.asyncio
async def test_mcp_read_file_security(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    hello_file = data_dir / "hello.txt"
    hello_file.write_text("你好，MCP！", encoding="utf-8")

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("不允许读取", encoding="utf-8")

    monkeypatch.setattr(tools, "READ_ROOT", data_dir)

    async with Client(mcp) as client:
        success = await client.call_tool(
            "read_file",
            {"path": "hello.txt"},
        )
        rejected = await client.call_tool(
            "read_file",
            {"path": "../outside.txt"},
        )

    assert success.is_error is False
    assert success.content[0].text == "你好，MCP！"
    assert rejected.is_error is True


@pytest.mark.asyncio
async def test_mcp_run_python_returns_bounded_result(monkeypatch):
    class FakeDockerClient:
        def close(self):
            pass

    class FakeDockerRunner:
        def __init__(self):
            self.client = FakeDockerClient()

        def run(self, request):
            assert request.code == "print(2 + 3)"
            return ExecutionResult(
                execution_id="test-execution-id",
                status=ExecutionStatus.SUCCEEDED,
                exit_code=0,
                stdout="5\n",
                stderr="",
                duration_ms=100,
            )

    monkeypatch.setattr(tools, "DockerRunner", FakeDockerRunner)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_python",
            {"code": "print(2 + 3)"},
        )

    assert result.is_error is False
    payload = json.loads(result.content[0].text)
    assert payload["exit_code"] == 0
    assert payload["stdout"] == "5\n"
    assert payload["tool_preview_truncated"] is False
    assert payload["execution_id"] == "test-execution-id"
    assert payload["status"] == "succeeded"

@pytest.mark.asyncio
async def test_mcp_run_python_passes_input_files(monkeypatch):
    class FakeDockerClient:
        def close(self):
            pass

    class FakeDockerRunner:
        def __init__(self):
            self.client = FakeDockerClient()

        def run(self, request):
            assert request.code == (
                'from pathlib import Path\n'
                'print(Path("/inputs/portfolio.csv").read_text())'
            )

            assert len(request.input_files) == 1
            assert request.input_files[0].path == "portfolio.csv"
            assert request.input_files[0].content == (
                "name,value\nfund_a,1000"
            )

            return ExecutionResult(
                execution_id="input-file-test",
                status=ExecutionStatus.SUCCEEDED,
                exit_code=0,
                stdout="name,value\nfund_a,1000\n",
                stderr="",
                duration_ms=100,
            )

    monkeypatch.setattr(
        tools,
        "DockerRunner",
        FakeDockerRunner,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_python",
            {
                "code": (
                    'from pathlib import Path\n'
                    'print(Path("/inputs/portfolio.csv").read_text())'
                ),
                "input_files": [
                    {
                        "path": "portfolio.csv",
                        "content": "name,value\nfund_a,1000",
                    }
                ],
            },
        )

    assert result.is_error is False

    payload = json.loads(result.content[0].text)
    assert payload["status"] == "succeeded"
    assert payload["stdout"] == "name,value\nfund_a,1000\n"

@pytest.mark.asyncio
async def test_mcp_analyze_portfolio():
    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,20,100\n"
        "债券基金,bond_fund,20,50\n"
        "现金,cash,1000,1\n"
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "analyze_portfolio",
            {
                "csv_content": csv_content,
            },
        )

    assert result.is_error is False

    payload = json.loads(result.content[0].text)

    assert payload["position_count"] == 3
    assert Decimal(
        payload["total_market_value"]
    ) == Decimal("4000")

    assert payload["largest_position"]["name"] == "股票基金"
    assert Decimal(
        payload["largest_position"]["weight"]
    ) == Decimal("0.5")

    assert Decimal(
        payload["asset_allocation"]["bond_fund"]
    ) == Decimal("0.25")

    assert Decimal(
        payload["concentration_hhi"]
    ) == Decimal("0.375")

@pytest.mark.asyncio
async def test_mcp_get_portfolio(
    tmp_path,
    monkeypatch,
) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )

    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,20,100\n"
        "债券基金,bond_fund,20,50\n"
    )
    file_bytes = csv_content.encode("utf-8")
    analysis = analyze_portfolio_csv(csv_content)

    saved = repository.save(
        filename="portfolio.csv",
        file_bytes=file_bytes,
        analysis=analysis,
    )

    monkeypatch.setattr(
        tools,
        "portfolio_repository",
        repository,
        raising=False,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_portfolio",
            {
                "portfolio_id": saved.portfolio_id,
            },
        )

    assert result.is_error is False

    payload = json.loads(result.content[0].text)

    assert payload["portfolio_id"] == saved.portfolio_id
    assert payload["filename"] == "portfolio.csv"
    assert (
        payload["analysis"]["largest_position"]["name"]
        == "股票基金"
    )

@pytest.mark.asyncio
async def test_mcp_assess_portfolio_risk(
    tmp_path,
    monkeypatch,
) -> None:
    repository = PortfolioRepository(
        tmp_path / "portfolio.sqlite3"
    )

    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,50,100\n"
        "债券基金,bond_fund,25,100\n"
        "货币基金,cash,25,100\n"
    )
    analysis = analyze_portfolio_csv(csv_content)

    saved = repository.save(
        filename="portfolio.csv",
        file_bytes=csv_content.encode("utf-8"),
        analysis=analysis,
    )

    monkeypatch.setattr(
        tools,
        "portfolio_repository",
        repository,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "assess_portfolio_risk",
            {
                "portfolio_id": saved.portfolio_id,
            },
        )

    assert result.is_error is False

    payload = json.loads(result.content[0].text)

    assert payload["portfolio_id"] == saved.portfolio_id
    assert payload["report"]["overall_level"] == "high"

    signal_codes = {
        signal["code"]
        for signal in payload["report"]["signals"]
    }

    assert "largest_position_concentration" in signal_codes
    assert "hhi_concentration" in signal_codes
