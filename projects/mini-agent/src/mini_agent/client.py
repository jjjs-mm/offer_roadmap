import os

import httpx

from mini_agent.models import Message


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
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

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    async def chat(self, messages: list[Message]) -> str:
        payload = {
            "model": self.model,
            "messages": [
                message.model_dump()
                for message in messages
            ],
            "max_tokens": 200,
        }

        async with httpx.AsyncClient(timeout=30) as http_client:
            response = await http_client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        if not content:
            raise RuntimeError("模型返回了空内容")

        return content