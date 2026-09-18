from pathlib import Path
from collections.abc import AsyncIterable

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from mini_agent.agent import stream_agent


app = FastAPI(title="mini-agent")
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=FileResponse)
async def chat_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

conversation_histories: dict[
    str,
    list[dict[str, str]],
] = {}


class ChatRequest(BaseModel):
    question: str
    conversation_id: str = "default"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}



@app.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(
    request: ChatRequest,
) -> AsyncIterable[ServerSentEvent]:
    """- Agent 正常结束：发送 done
       - Agent 产生 error：发送错误后立即结束，不再发送 done"""
    history = conversation_histories.setdefault(
        request.conversation_id,
        [],
    )
    assistant_parts: list[str] = []
    async for event in stream_agent(
        request.question,
        history=history,
    ):
        if event["type"] == "content":
            assistant_parts.append(event["content"])
        yield ServerSentEvent(
            event=event["type"],
            data=event,
        )

        if event["type"] == "error":
            return
    assistant_content = "".join(
        assistant_parts
    ).strip()

    history.extend(
        [
            {
                "role": "user",
                "content": request.question,
            },
            {
                "role": "assistant",
                "content": assistant_content,
            },
        ]
    )

    yield ServerSentEvent(
        event="done",
        data={"type": "done"},
    )