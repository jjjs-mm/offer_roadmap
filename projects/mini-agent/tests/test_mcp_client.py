import pytest

from mini_agent.mcp_client import (
    call_mcp_tool,
    create_mcp_client,
    load_llm_tools,
)


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