import asyncio

from mini_agent.client import LLMClient
from mini_agent.models import Message


async def main() -> None:
    client = LLMClient.from_env()

    messages = [
        Message(
            role="system",
            content="You are a helpful assistant.",
        ),
        Message(
            role="user",
            content="请用一句话解释什么是AI Agent。",
        ),
    ]

    answer = await client.chat(messages)
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())