import json
import os

import pytest
from decimal import Decimal

from mini_agent.mcp_client import (
    call_mcp_tool,
    create_mcp_client,
    load_llm_tools,
)
from fastapi.testclient import TestClient

from mini_agent import api
from mini_agent.portfolio_repository import PortfolioRepository


@pytest.mark.asyncio
async def test_load_llm_tools_from_mcp_server():
    async with create_mcp_client() as client:
        tools = await load_llm_tools(client)

    tool_names = {
        tool["function"]["name"]
        for tool in tools
    }

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
async def test_call_mcp_calculator():
    async with create_mcp_client() as client:
        result = await call_mcp_tool(
            client,
            "calculator",
            '{"expression": "3*(7+2)"}',
        )

    assert result == "27.0"


@pytest.mark.asyncio
async def test_call_mcp_tool_returns_errors():
    async with create_mcp_client() as client:
        bad_json = await call_mcp_tool(
            client,
            "calculator",
            "not-json",
        )
        rejected_path = await call_mcp_tool(
            client,
            "read_file",
            '{"path": "../pyproject.toml"}',
        )

    assert bad_json.startswith(
        "工具执行失败:"
    )
    assert rejected_path.startswith(
        "工具执行失败:"
    )


@pytest.mark.asyncio
async def test_run_python_with_docker():
    if os.getenv("RUN_DOCKER_TESTS") != "1":
        pytest.skip("Set RUN_DOCKER_TESTS=1 to run Docker integration test")

    async with create_mcp_client() as client:
        response = await call_mcp_tool(
            client,
            "run_python",
            '{"code": "print(2 + 3)"}',
        )
    assert not response.startswith(
        "工具执行失败:"
    ), response
    payload = json.loads(response)
    assert payload["exit_code"] == 0
    assert payload["stdout"] == "5\n"
    assert payload["status"] == "succeeded"
    assert len(payload["execution_id"]) == 32

@pytest.mark.asyncio
async def test_run_python_reads_portfolio_file_with_docker():
    if os.getenv("RUN_DOCKER_TESTS") != "1":
        pytest.skip(
            "Set RUN_DOCKER_TESTS=1 to run Docker integration test"
        )

    arguments = json.dumps(
        {
            "code": (
                "import csv\n"
                "from pathlib import Path\n"
                "\n"
                'with Path("/inputs/portfolio.csv").open('
                'encoding="utf-8") as file:\n'
                "    rows = csv.DictReader(file)\n"
                "    total = sum(\n"
                '        float(row["shares"]) * float(row["price"])\n'
                "        for row in rows\n"
                "    )\n"
                "\n"
                'print(f"{total:.2f}")'
            ),
            "input_files": [
                {
                    "path": "portfolio.csv",
                    "content": (
                        "name,shares,price\n"
                        "fund_a,10,100\n"
                        "fund_b,20,75"
                    ),
                }
            ],
        },
        ensure_ascii=False,
    )

    async with create_mcp_client() as client:
        response = await call_mcp_tool(
            client,
            "run_python",
            arguments,
        )
    assert not response.startswith(
       "工具执行失败:"
     ), response
    payload = json.loads(response)

    assert payload["status"] == "succeeded"
    assert payload["exit_code"] == 0
    assert payload["stdout"] == "2500.00\n"

@pytest.mark.asyncio
async def test_call_mcp_analyze_portfolio():
    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,20,100\n"
        "债券基金,bond_fund,20,50\n"
        "现金,cash,1000,1\n"
    )

    arguments = json.dumps(
        {
            "csv_content": csv_content,
        },
        ensure_ascii=False,
    )

    async with create_mcp_client() as client:
        response = await call_mcp_tool(
            client,
            "analyze_portfolio",
            arguments,
        )

    payload = json.loads(response)

    assert payload["position_count"] == 3
    assert Decimal(
        payload["total_market_value"]
    ) == Decimal("4000")
    assert payload["largest_position"]["name"] == "股票基金"
    assert Decimal(
        payload["concentration_hhi"]
    ) == Decimal("0.375")

@pytest.mark.asyncio
async def test_uploaded_portfolio_can_be_loaded_by_mcp(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "portfolio.sqlite3"

    # MCP 子进程会继承这个环境变量。
    monkeypatch.setenv(
        "PORTFOLIO_DATABASE_PATH",
        str(database_path),
    )

    # API 当前已经在主进程中导入，所以直接替换其 Repository。
    monkeypatch.setattr(
        api,
        "portfolio_repository",
        PortfolioRepository(database_path),
    )

    http_client = TestClient(api.app)

    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,20,100\n"
        "债券基金,bond_fund,20,50\n"
    )

    upload_response = http_client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                csv_content.encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 200

    uploaded = upload_response.json()
    portfolio_id = uploaded["portfolio_id"]

    async with create_mcp_client() as client:
        tool_response = await call_mcp_tool(
            client,
            "get_portfolio",
            json.dumps(
                {"portfolio_id": portfolio_id}
            ),
        )

    loaded = json.loads(tool_response)

    assert loaded["portfolio_id"] == portfolio_id
    assert loaded["content_sha256"] == uploaded["content_sha256"]
    assert loaded["analysis"] == uploaded["analysis"]

@pytest.mark.asyncio
async def test_uploaded_portfolio_risk_can_be_assessed_by_mcp(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "portfolio.sqlite3"

    monkeypatch.setenv(
        "PORTFOLIO_DATABASE_PATH",
        str(database_path),
    )
    monkeypatch.setattr(
        api,
        "portfolio_repository",
        PortfolioRepository(database_path),
    )

    http_client = TestClient(api.app)

    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,50,100\n"
        "债券基金,bond_fund,25,100\n"
        "货币基金,cash,25,100\n"
    )

    upload_response = http_client.post(
        "/portfolio/analyze",
        files={
            "file": (
                "portfolio.csv",
                csv_content.encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 200

    portfolio_id = upload_response.json()["portfolio_id"]

    async with create_mcp_client() as client:
        tool_response = await call_mcp_tool(
            client,
            "assess_portfolio_risk",
            json.dumps(
                {"portfolio_id": portfolio_id}
            ),
        )

    assert not tool_response.startswith(
        "工具执行失败:"
    ), tool_response

    assessment = json.loads(tool_response)

    assert assessment["portfolio_id"] == portfolio_id
    assert assessment["report"]["overall_level"] == "high"
    assert "不构成投资建议" in (
        assessment["report"]["disclaimer"]
    )

    signal_codes = {
        signal["code"]
        for signal in assessment["report"]["signals"]
    }

    assert "largest_position_concentration" in signal_codes
    assert "hhi_concentration" in signal_codes