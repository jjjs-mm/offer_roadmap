import pytest
from mcp import Client

from mini_agent import tools
from mini_agent.mcp_server import mcp


@pytest.mark.asyncio
async def test_mcp_lists_registered_tools():
    async with Client(mcp) as client:
        result = await client.list_tools()

    tool_names = {tool.name for tool in result.tools}

    assert tool_names == {"calculator", "read_file"}


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