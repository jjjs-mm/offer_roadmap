import json
import sys
from typing import Any

from mcp import Client, StdioServerParameters


def create_mcp_client() -> Client:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mini_agent.mcp_server"],
    )

    return Client(server)


async def load_llm_tools(
    client: Client,
) -> list[dict[str, Any]]:
    result = await client.list_tools()

    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in result.tools
    ]


async def call_mcp_tool(
    client: Client,
    name: str,
    arguments: str,
) -> str:
    try:
        payload = json.loads(arguments)
        result = await client.call_tool(
            name,
            payload,
        )
    except Exception as error:
        return f"工具执行失败: {error}"

    text_parts = [
        content.text
        for content in result.content
        if hasattr(content, "text")
    ]
    text = "\n".join(text_parts)

    if result.is_error:
        return f"工具执行失败: {text}"

    return text