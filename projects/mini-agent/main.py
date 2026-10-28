import asyncio

from mini_agent.agent import stream_agent


async def main() -> None:
    async for event in stream_agent("3 * (7 + 2) 等于多少？"):
        event_type = event["type"]

        if event_type == "content":
            print(event["content"], end="", flush=True)

        elif event_type == "tool_start":
            print(
                f"\n[工具开始] {event['name']} "
                f"{event['arguments']}"
            )

        elif event_type == "tool_end":
            print(
                f"[工具结束] {event['name']} "
                f"结果：{event['result']}"
            )

        elif event_type == "context_trim":
            print(
                "\n[上下文裁剪] "
                f"{event['before_tokens']} → "
                f"{event['after_tokens']} tokens，"
                f"删除 {event['removed_messages']} 条消息"
            )
        elif event_type == "context_summary":
            print(
                "\n[上下文摘要]\n"
                f"{event['summary']}"
            )
        elif event_type == "retry":
            print(
                "\n[请求重试] "
                f"准备第 {event['next_attempt']} 次请求"
                f"（最多 {event['max_attempts']} 次），"
                f"{event['delay_seconds']} 秒后重试；"
                f"原因：{event['reason']}"
            )

        elif event_type == "error":
            print(f"\n[错误] {event['message']}")

    print()


if __name__ == "__main__":
    asyncio.run(main())