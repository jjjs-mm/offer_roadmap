from pathlib import Path
from collections.abc import AsyncIterable

from fastapi import (
    FastAPI,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from mini_agent.agent import stream_agent
from mini_agent.portfolio import (
    PortfolioAnalysis,
    analyze_portfolio_csv,
)
from mini_agent.portfolio_repository import (
    DEFAULT_PORTFOLIO_DATABASE_PATH,
    PortfolioRecord,
    PortfolioRepository,
)
from mini_agent.portfolio_risk import (
    PortfolioRiskAssessment,
    assess_portfolio_risk,
)


app = FastAPI(title="mini-agent")
STATIC_DIR = Path(__file__).parent / "static"
MAX_PORTFOLIO_FILE_BYTES = 1 * 1024 * 1024
portfolio_repository = PortfolioRepository(
    DEFAULT_PORTFOLIO_DATABASE_PATH
)

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

@app.post(
    "/portfolio/analyze",
    response_model=PortfolioAnalysis,
)
@app.post(
    "/portfolio/analyze",
    response_model=PortfolioRecord,
)
async def analyze_portfolio_upload(
    file: UploadFile,
) -> PortfolioRecord:
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="只支持 CSV 文件",
        )

    try:
        file_bytes = await file.read(
            MAX_PORTFOLIO_FILE_BYTES + 1
        )
    finally:
        await file.close()

    if len(file_bytes) > MAX_PORTFOLIO_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="持仓 CSV 不能超过 1 MiB",
        )

    try:
        csv_content = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="持仓 CSV 必须使用 UTF-8 编码",
        ) from error

    try:
        analysis = analyze_portfolio_csv(csv_content)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return portfolio_repository.save(
        filename=filename,
        file_bytes=file_bytes,
        analysis=analysis,
    )

@app.get(
    "/portfolio/{portfolio_id}",
    response_model=PortfolioRecord,
)
async def get_portfolio(
    portfolio_id: str,
) -> PortfolioRecord:
    record = portfolio_repository.get(portfolio_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到持仓分析记录",
        )

    return record

@app.get(
    "/portfolio/{portfolio_id}/risk",
    response_model=PortfolioRiskAssessment,
)
async def get_portfolio_risk(
    portfolio_id: str,
) -> PortfolioRiskAssessment:
    record = portfolio_repository.get(portfolio_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到持仓分析记录",
        )

    report = assess_portfolio_risk(record.analysis)

    return PortfolioRiskAssessment(
        portfolio_id=portfolio_id,
        report=report,
    )

@app.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_conversation(
    conversation_id: str,
) -> Response:
    conversation_histories.pop(conversation_id, None)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )

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