import json
from typing import Any


def estimate_text_tokens(text: str) -> int:
    ascii_count = sum(
        1
        for character in text
        if character.isascii()
    )
    non_ascii_count = len(text) - ascii_count

    ascii_tokens = (ascii_count + 3) // 4
    return ascii_tokens + non_ascii_count


def estimate_messages_tokens(
    messages: list[dict[str, Any]],
) -> int:
    total = 0

    for message in messages:
        serialized = json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        total += estimate_text_tokens(serialized)

    return total
def _group_non_system_messages(
    messages: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []

    for message in messages:
        if message.get("role") == "system":
            continue

        if message.get("role") == "tool" and groups:
            previous_group = groups[-1]
            first_message = previous_group[0]

            if (
                first_message.get("role") == "assistant"
                and first_message.get("tool_calls")
            ):
                previous_group.append(message)
                continue

        groups.append([message])

    return groups

def collect_removed_messages(
    original_messages: list[dict[str, Any]],
    kept_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept_message_ids = {
        id(message)
        for message in kept_messages
    }

    return [
        message
        for message in original_messages
        if id(message) not in kept_message_ids
    ]
def build_context_summary( #生成摘要消息
    removed_messages: list[dict[str, Any]],
    max_chars: int = 800,
) -> dict[str, Any] | None:
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")

    if not removed_messages:
        return None

    summary_lines: list[str] = []

    for message in removed_messages:
        role = message.get("role", "unknown")
        content = message.get("content")

        if content:
            details = str(content)
        elif message.get("tool_calls"):
            tool_names = [
                call.get("function", {}).get(
                    "name",
                    "unknown",
                )
                for call in message["tool_calls"]
            ]
            details = (
                "调用工具："
                + ", ".join(tool_names)
            )
        else:
            details = "无文本内容"

        summary_lines.append(
            f"{role}: {details}"
        )

    summary_body = "\n".join(summary_lines)

    if len(summary_body) > max_chars:
        summary_body = (
            summary_body[:max_chars - 1]
            + "…"
        )

    return {
        "role": "system",
        "content": (
            "此前上下文摘要：\n"
            + summary_body
        ),
    }

def trim_messages_sliding_window(
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> list[dict[str, Any]]:
    if max_tokens <= 0:
        raise ValueError("max_tokens 必须大于 0")

    if estimate_messages_tokens(messages) <= max_tokens:
        return list(messages)

    system_messages = [
        message
        for message in messages
        if message.get("role") == "system"
    ]

    latest_user_index = None
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            latest_user_index = index
            break

    base_messages = list(system_messages)

    if latest_user_index is not None:
        base_messages.append(messages[latest_user_index])
        tail_messages = messages[latest_user_index + 1:]
    else:
        tail_messages = [
            message
            for message in messages
            if message.get("role") != "system"
        ]

    message_groups = _group_non_system_messages(
        tail_messages
    )
    recent_groups: list[list[dict[str, Any]]] = []

    for group in reversed(message_groups):
        candidate_groups = [group] + recent_groups
        candidate_messages = base_messages + [
            message
            for candidate_group in candidate_groups
            for message in candidate_group
        ]

        if (
            recent_groups
            and estimate_messages_tokens(candidate_messages)
            > max_tokens
        ):
            break

        recent_groups.insert(0, group)

    recent_messages = [
        message
        for group in recent_groups
        for message in group
    ]

    return base_messages + recent_messages