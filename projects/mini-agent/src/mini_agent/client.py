import os
from typing import Any
import json
from collections.abc import AsyncIterator
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv(
    Path(__file__).resolve().parents[2] / ".env"
)
RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, httpx.TransportError):
        return True

    if isinstance(error, httpx.HTTPStatusError):
        return (
            error.response.status_code
            in RETRYABLE_STATUS_CODES
        )

    return False

class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @classmethod
    def from_env(cls) -> "LLMClient":
        api_key = os.environ.get("LLM_API_KEY")
        base_url = os.environ.get("LLM_BASE_URL")
        model = os.environ.get("LLM_MODEL")

        if not api_key:
            raise RuntimeError("缺少环境变量 LLM_API_KEY")
        if not base_url:
            raise RuntimeError("缺少环境变量 LLM_BASE_URL")
        if not model:
            raise RuntimeError("缺少环境变量 LLM_MODEL")

        return cls(api_key=api_key, base_url=base_url, model=model)

    async def chat(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
           "model": self.model,
           "messages": [
                message.model_dump() if hasattr(message, "model_dump") else message
                for message in messages
           ],
            "thinking": {"type": "disabled"},
            }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=30, trust_env=True) as http_client:
          response = await http_client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.status_code >= 400:
           print("第二次请求的 messages:")
           for item in payload["messages"]:
             print(item)
           print("HTTP错误:", response.status_code, response.text)

        response.raise_for_status()
        return response.json()["choices"][0]["message"]
    async def stream_chat(
       self,
       messages: list[Any],
       tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload = {
        "model": self.model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "stream": True,
        }
        if tools:
          payload["tools"] = tools
          payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=30, trust_env=True) as http_client:
          async with http_client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines(): #每收到一行 SSE 数据，就处理一次。
                if not line.startswith("data: "):
                    continue #忽略空行和 : keep-alive 等非数据内容。

                data = line.removeprefix("data: ")
                if data == "[DONE]":
                    break   #模型告诉我们流式响应已经结束。

                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"]

                if delta:
                  yield delta