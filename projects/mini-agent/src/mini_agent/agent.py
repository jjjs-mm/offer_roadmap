import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from mcp import Client
from mini_agent.client import (
    LLMClient,
    is_retryable_error,
)
from mini_agent.context import (
    build_context_summary,
    collect_removed_messages,
    estimate_messages_tokens,
    trim_messages_sliding_window,
)
from mini_agent.mcp_client import (
    call_mcp_tool,
    create_mcp_client,
    load_llm_tools,
)


def _merge_stream_delta(
    message: dict[str, Any],
    delta: dict[str, Any],
) -> None:
    content = delta.get("content")
    if content:
        message["content"] += content

    for call_delta in delta.get("tool_calls") or []:
        index = call_delta["index"]

        while len(message["tool_calls"]) <= index:
            message["tool_calls"].append(
                {
                    "id": "",
                    "type": "function",
                    "function": {
                        "name": "",
                        "arguments": "",
                    },
                }
            )

        tool_call = message["tool_calls"][index]

        if call_delta.get("id"):
            tool_call["id"] = call_delta["id"]

        if call_delta.get("type"):
            tool_call["type"] = call_delta["type"]

        function_delta = call_delta.get("function") or {}

        if function_delta.get("name"):
            tool_call["function"]["name"] += function_delta["name"]

        if function_delta.get("arguments"):
            tool_call["function"]["arguments"] += function_delta["arguments"]


def _history_assistant(message: dict) -> dict:
    cleaned = {
        "role": "assistant",
        "content": message.get("content") or None,
    }
    if message.get("reasoning_content"):
        cleaned["reasoning_content"] = message["reasoning_content"]
    if message.get("tool_calls"):
        cleaned["tool_calls"] = [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["function"]["name"],
                    "arguments": call["function"]["arguments"],
                },
            }
            for call in message["tool_calls"]
        ]
    return cleaned


async def _stream_agent_with_mcp(
    question: str,
    llm_client: LLMClient,
    mcp_client: Client,
    llm_tools: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
    max_context_tokens: int = 4_000,
    max_request_attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "需要计算时调用 calculator。"
                "不知道 data 目录有哪些文件时，先调用 list_files。"
                "需要读取 data 目录内的文本文件时调用 read_file，"
                "path 使用相对于 data 目录的路径，例如 hello.txt。"
                "根据工具实际返回的内容回答，不要猜测文件内容。"
                "工具失败时如实说明。其他问题直接回答。"
            ),
        },
    ]

    if history:
        messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": question,
        }
    )
    tool_result_cache: dict[tuple[str, str], str] = {}

    for _ in range(5):
        """每次请求大模型之前，检查 messages 会不会太长；
        如果太长，就删掉较旧的对话，避免超过模型的上下文限制。"""
        before_tokens = estimate_messages_tokens(messages)

        trimmed_messages = trim_messages_sliding_window(
            messages,
            max_tokens=max_context_tokens,
        )

        removed_messages = collect_removed_messages(
            original_messages=messages,
            kept_messages=trimmed_messages,
        )

        summary_message = None
        existing_summary_messages = []

        if removed_messages:
            summary_sources = list(removed_messages)

            for existing_message in list(
                trimmed_messages
            ):
                content = existing_message.get(
                    "content"
                )

                if (
                    existing_message.get("role")
                    == "system"
                    and isinstance(content, str)
                    and content.startswith(
                        "此前上下文摘要：\n"
                    )
                ):
                    existing_summary_messages.append(
                        existing_message
                    )
                    summary_sources.append(
                        existing_message
                    )
                    trimmed_messages.remove(
                        existing_message
                    )

            summary_message = build_context_summary(
                summary_sources
            )

            if summary_message is not None:
                insert_index = 0

                while (
                    insert_index
                    < len(trimmed_messages)
                    and trimmed_messages[
                        insert_index
                    ].get("role") == "system"
                ):
                    insert_index += 1

                trimmed_messages.insert(
                    insert_index,
                    summary_message,
                )

                candidate_tokens = (
                    estimate_messages_tokens(
                        trimmed_messages
                    )
                )

                if (
                    candidate_tokens >= before_tokens
                    or candidate_tokens
                    > max_context_tokens
                ):
                    trimmed_messages.pop(
                        insert_index
                    )

                    for existing_summary in (
                        existing_summary_messages
                    ):
                        trimmed_messages.insert(
                            insert_index,
                            existing_summary,
                        )
                        insert_index += 1

                    summary_message = None
                after_tokens = estimate_messages_tokens(
            trimmed_messages
        )

        if removed_messages:
            yield {
                "type": "context_trim",
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
                "removed_messages": len(
                    removed_messages
                ),
            }

        if summary_message is not None:
            yield {
                "type": "context_summary",
                "summary": summary_message["content"],
            }
        messages = trimmed_messages #用裁剪后的消息覆盖原来的 messages
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "",
            "tool_calls": [],
        }

        received_delta = False

        for attempt in range(
            1,
            max_request_attempts + 1,
        ):
            try:
                async for delta in llm_client.stream_chat(
                    messages,
                    tools=llm_tools,
                ):
                    received_delta = True

                    content = delta.get("content")

                    if content:
                        yield {
                            "type": "content",
                            "content": content,
                        }

                    _merge_stream_delta(message, delta)

                break

            except (
                httpx.HTTPError,
                json.JSONDecodeError,
                KeyError,
            ) as error:
                can_retry = (
                    not received_delta
                    and is_retryable_error(error)
                    and attempt < max_request_attempts
                )

                if not can_retry:
                    yield {
                        "type": "error",
                        "message": (
                            "模型流式请求失败："
                            f"{type(error).__name__}: "
                            f"{error}"
                        ),
                    }
                    return

                delay_seconds = (
                    retry_delay_seconds
                    * 2 ** (attempt - 1)
                )

                yield {
                    "type": "retry",
                    "next_attempt": attempt + 1,
                    "max_attempts": max_request_attempts,
                    "delay_seconds": delay_seconds,
                    "reason": type(error).__name__,
                }

                await asyncio.sleep(delay_seconds)

        messages.append(_history_assistant(message))

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return

        for call in tool_calls:
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]

            cache_key = (name, arguments)

            if cache_key in tool_result_cache:
                result = tool_result_cache[cache_key]
            else:
                yield {
                    "type": "tool_start",
                    "tool_call_id": call["id"],
                    "name": name,
                    "arguments": arguments,
                }

                try:
                    result = await call_mcp_tool(
                    mcp_client,
                    name,
                    arguments,
               )
                except Exception as error:
                    result = (
                        "MCP 工具调用失败："
                        f"{type(error).__name__}: {error}"
                    )

                tool_result_cache[cache_key] = result
                yield {
                    "type": "tool_end",
                    "tool_call_id": call["id"],
                    "name": name,
                    "result": result,
                }
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                }
            )

    yield {
        "type": "error",
        "message": "超出最大步数",
    }


async def stream_agent(
    question: str,
    history: list[dict[str, Any]] | None = None,
    max_context_tokens: int = 4_000,
    max_request_attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    try:
        llm_client = LLMClient.from_env()
    except RuntimeError as error:
        yield {
            "type": "error",
            "message": str(error),
        }
        return

    try:
        async with create_mcp_client() as mcp_client:
            llm_tools = await load_llm_tools(
                mcp_client
            )

            async for event in _stream_agent_with_mcp(
                question,
                llm_client,
                mcp_client,
                llm_tools,
                history,
                max_context_tokens,
                max_request_attempts,
                retry_delay_seconds,
            ):
                yield event
    except Exception as error:
        yield {
            "type": "error",
            "message": (
                "MCP 会话失败："
                f"{type(error).__name__}: {error}"
            ),
        }