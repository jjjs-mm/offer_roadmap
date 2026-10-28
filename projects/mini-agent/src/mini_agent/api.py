from pathlib import Path
from collections.abc import AsyncIterable
from datetime import date
import logging
import time

from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Response,
    UploadFile,
    status,
    Query,
    Form,
)
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from typing import Literal
from mini_agent.agent import stream_agent
from mini_agent.portfolio import (
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
from mini_agent.knowledge_repository import (
    DEFAULT_KNOWLEDGE_DATABASE_PATH,
    KnowledgeDocumentRecord,
    KnowledgeRepository,
)
from mini_agent.knowledge import KnowledgeChunk
from mini_agent.ingestion_repository import (
    DEFAULT_INGESTION_DATABASE_PATH,
    IngestionJobRecord,
    IngestionRepository,
)
from mini_agent.pdf_ingestion import extract_pdf_pages
from mini_agent.fund_evidence import (
    FEE_TERMS,
    find_fee_rate,
    missing_fee_terms,
)
from mini_agent.rag import (
    build_grounded_question,
    retrieve_evidence,
)
from mini_agent.semantic_retrieval import get_default_embedder
from mini_agent.evidence_sufficiency import (
    assess_evidence_sufficiency,
)
from mini_agent.query_normalization import normalize_financial_query
from mini_agent.rag_trace import (
    DEFAULT_RAG_TRACE_DATABASE_PATH,
    RagTraceMetrics,
    RagTraceRecord,
    RagTraceRepository,
)


app = FastAPI(title="mini-agent")
STATIC_DIR = Path(__file__).parent / "static"
MAX_PORTFOLIO_FILE_BYTES = 1 * 1024 * 1024
portfolio_repository = PortfolioRepository(
    DEFAULT_PORTFOLIO_DATABASE_PATH
)
MAX_KNOWLEDGE_FILE_BYTES = 10 * 1024 * 1024

knowledge_repository = KnowledgeRepository(
    DEFAULT_KNOWLEDGE_DATABASE_PATH,
    embed_texts=get_default_embedder().embed,
)
rag_trace_repository = RagTraceRepository(
    DEFAULT_RAG_TRACE_DATABASE_PATH
)
ingestion_repository = IngestionRepository(
    DEFAULT_INGESTION_DATABASE_PATH
)
logger = logging.getLogger(__name__)

@app.get("/", response_class=FileResponse)
async def chat_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

conversation_histories: dict[
    str,
    list[dict[str, str]],
] = {}

@app.get(
    "/knowledge/search",
    response_model=list[KnowledgeChunk],
    response_model_exclude_none=True,
)
async def search_knowledge(
    q: str,
    limit: int = Query(default=5, ge=1, le=20),
    mode: Literal[
        "keyword",
        "ngram",
        "vector",
        "hybrid",
    ] = "keyword",
) -> list[KnowledgeChunk]:
    keyword = q.strip()

    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="查询词不能为空",
        )

    if mode == "ngram":
        return knowledge_repository.search_ngrams(
            keyword,
            limit=limit,
        )

    if mode == "vector":
        return knowledge_repository.search_vectors(
            keyword,
            limit=limit,
        )

    if mode == "hybrid":
        return knowledge_repository.search_hybrid(
            keyword,
            limit=limit,
        )

    return knowledge_repository.search(
        keyword,
        limit=limit,
    )

class ChatRequest(BaseModel):
    question: str
    conversation_id: str = "default"
    knowledge_document_id: str | None = None


@app.get(
    "/traces/metrics",
    response_model=RagTraceMetrics,
)
async def get_rag_trace_metrics(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
) -> RagTraceMetrics:
    """提供不含用户内容的 RAG 运行指标，供面板和告警消费。"""
    return rag_trace_repository.get_metrics(
        window_hours=window_hours,
    )


@app.get(
    "/traces/{trace_id}",
    response_model=RagTraceRecord,
    response_model_exclude_none=True,
)
async def get_rag_trace(trace_id: str) -> RagTraceRecord:
    record = rag_trace_repository.get(trace_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到 RAG Trace",
        )

    return record


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def process_knowledge_ingestion(ingestion_id: str) -> None:
    """执行一条已持久化任务；重复调度只会有一个 worker 成功领取。"""
    claimed = ingestion_repository.claim(ingestion_id)
    if claimed is None:
        return

    job, file_bytes = claimed
    try:
        suffix = Path(job.filename).suffix.lower()
        pages: list[str] | None = None
        if suffix == ".pdf":
            pages = extract_pdf_pages(file_bytes)
            text = "\n\n".join(pages)
        else:
            try:
                text = file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError as error:
                raise ValueError("知识文档必须使用 UTF-8 编码") from error

        existing_document = knowledge_repository.get_by_content_sha256(
            job.content_sha256
        )
        if existing_document is not None:
            document_id = existing_document.document_id
        else:
            document = knowledge_repository.save(
                filename=job.filename,
                file_bytes=file_bytes,
                text=text,
                pages=pages,
                source_url=job.source_url,
                published_at=job.published_at,
            )
            document_id = document.document_id

        ingestion_repository.succeed(
            ingestion_id,
            document_id=document_id,
        )
    except ValueError as error:
        ingestion_repository.fail(
            ingestion_id,
            error_message=str(error),
        )
    except Exception:
        logger.exception(
            "知识文档异步导入失败",
            extra={"ingestion_id": ingestion_id},
        )
        ingestion_repository.fail(
            ingestion_id,
            error_message="导入执行失败，请稍后重试",
        )


def _validate_ingestion_metadata(
    *,
    filename: str,
    source_url: str | None,
    published_at: str | None,
) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="只支持 TXT、Markdown 或 PDF 文件",
        )

    if source_url is not None and not source_url.startswith(
        ("https://", "http://")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source_url 必须是 HTTP(S) 地址",
        )

    if published_at is not None:
        try:
            date.fromisoformat(published_at)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="published_at 必须是 YYYY-MM-DD",
            ) from error


@app.post(
    "/knowledge/ingestions",
    response_model=IngestionJobRecord,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_knowledge_ingestion(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    source_url: str | None = Form(default=None),
    published_at: str | None = Form(default=None),
) -> IngestionJobRecord:
    """持久化原文件后快速返回任务 ID，解析和向量化转入后台。"""
    filename = file.filename or ""
    _validate_ingestion_metadata(
        filename=filename,
        source_url=source_url,
        published_at=published_at,
    )

    try:
        file_bytes = await file.read(MAX_KNOWLEDGE_FILE_BYTES + 1)
    finally:
        await file.close()

    if len(file_bytes) > MAX_KNOWLEDGE_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="知识文档不能超过 10 MiB",
        )

    job, created = ingestion_repository.enqueue(
        filename=filename,
        file_bytes=file_bytes,
        source_url=source_url,
        published_at=published_at,
    )
    if created or job.status == "queued":
        background_tasks.add_task(
            process_knowledge_ingestion,
            job.ingestion_id,
        )
    return job


@app.get(
    "/knowledge/ingestions/{ingestion_id}",
    response_model=IngestionJobRecord,
    response_model_exclude_none=True,
)
async def get_knowledge_ingestion(
    ingestion_id: str,
) -> IngestionJobRecord:
    job = ingestion_repository.get(ingestion_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到知识导入任务",
        )
    return job


@app.post(
    "/knowledge/ingestions/{ingestion_id}/retry",
    response_model=IngestionJobRecord,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_knowledge_ingestion(
    ingestion_id: str,
    background_tasks: BackgroundTasks,
) -> IngestionJobRecord:
    try:
        job = ingestion_repository.retry(ingestion_id)
    except ValueError as error:
        current = ingestion_repository.get(ingestion_id)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到知识导入任务",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    background_tasks.add_task(
        process_knowledge_ingestion,
        job.ingestion_id,
    )
    return job

@app.post(
    "/knowledge/documents",
    response_model=KnowledgeDocumentRecord,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_document(
    file: UploadFile,
    source_url: str | None = Form(default=None),
    published_at: str | None = Form(default=None),
) -> KnowledgeDocumentRecord:
    filename = file.filename or ""
    _validate_ingestion_metadata(
        filename=filename,
        source_url=source_url,
        published_at=published_at,
    )
    suffix = Path(filename).suffix.lower()

    try:
        file_bytes = await file.read(
            MAX_KNOWLEDGE_FILE_BYTES + 1
        )
    finally:
        await file.close()

    if len(file_bytes) > MAX_KNOWLEDGE_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="知识文档不能超过 10 MiB",
        )

    pages: list[str] | None = None
    if suffix == ".pdf":
        try:
            pages = extract_pdf_pages(file_bytes)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        text = "\n\n".join(pages)
    else:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="知识文档必须使用 UTF-8 编码",
            ) from error

    try:
        return knowledge_repository.save(
            filename=filename,
            file_bytes=file_bytes,
            text=text,
            pages=pages,
            source_url=source_url,
            published_at=published_at,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@app.get(
    "/knowledge/documents/{document_id}",
    response_model=KnowledgeDocumentRecord,
    response_model_exclude_none=True,
)
async def get_knowledge_document(
    document_id: str,
) -> KnowledgeDocumentRecord:
    record = knowledge_repository.get(document_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到知识文档",
        )

    return record

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
    agent_question = request.question
    citation_chunks: list[KnowledgeChunk] = []
    trace_started_at = time.perf_counter()
    retrieval_method: str | None = None
    retrieval_duration_ms: int | None = None
    generation_duration_ms: int | None = None
    evidence_sufficient: bool | None = None
    evidence_reason_code: str | None = None

    try:
        trace = rag_trace_repository.start(
            conversation_id=request.conversation_id,
            question=request.question,
            knowledge_document_id=request.knowledge_document_id,
        )
    except Exception:
        logger.exception("创建 RAG Trace 失败")
        trace = None

    def finish_trace(
        trace_status: Literal["succeeded", "rejected", "failed"],
        *,
        error_message: str | None = None,
    ) -> None:
        if trace is None:
            return

        try:
            rag_trace_repository.finish(
                trace.trace_id,
                status=trace_status,
                retrieval_method=retrieval_method,
                retrieved_chunk_count=len(citation_chunks),
                evidence_sufficient=evidence_sufficient,
                evidence_reason_code=evidence_reason_code,
                retrieval_duration_ms=retrieval_duration_ms,
                generation_duration_ms=generation_duration_ms,
                total_duration_ms=int(
                    (time.perf_counter() - trace_started_at) * 1000
                ),
                error_message=error_message,
            )
        except Exception:
            logger.exception(
                "完成 RAG Trace 失败",
                extra={"trace_id": trace.trace_id},
            )

    if trace is not None:
        yield ServerSentEvent(
            event="trace",
            data={
                "type": "trace",
                "trace_id": trace.trace_id,
            },
        )

    if request.knowledge_document_id is not None:
        document = knowledge_repository.get(
            request.knowledge_document_id
        )
        if document is None:
            finish_trace("failed", error_message="未找到知识文档")
            yield ServerSentEvent(
                event="error",
                data={
                    "type": "error",
                    "message": "未找到知识文档",
                },
            )
            return

        normalized_query = normalize_financial_query(request.question)
        retrieval_question = normalized_query.retrieval_query

        missing_terms = missing_fee_terms(
            retrieval_question,
            document.chunks,
        )
        if missing_terms:
            retrieval_method = "direct_fee"
            evidence_sufficient = False
            evidence_reason_code = "missing_explicit_fee"
            assistant_content = (
                "所选资料未提供"
                + "、".join(missing_terms)
                + "的明确费率，无法据此回答。"
            )
            history.extend(
                [
                    {"role": "user", "content": request.question},
                    {"role": "assistant", "content": assistant_content},
                ]
            )
            yield ServerSentEvent(
                event="content",
                data={"type": "content", "content": assistant_content},
            )
            yield ServerSentEvent(
                event="done",
                data={"type": "done"},
            )
            finish_trace("rejected")
            return

        fee_answers: list[tuple[str, str, KnowledgeChunk]] = []

        for term in FEE_TERMS:
            if term not in retrieval_question:
                continue

            found = find_fee_rate(term, document.chunks)
            if found is not None:
                rate, chunk = found
                fee_answers.append((term, rate, chunk))

        if fee_answers:
            retrieval_method = "direct_fee"
            citation_chunks = [answer[2] for answer in fee_answers]
            evidence_sufficient = True
            evidence_reason_code = "explicit_fee_found"
            assistant_content = "根据所选资料，" + "；".join(
                f"{term}为{rate}"
                for term, rate, _ in fee_answers
            ) + "。"

            history.extend(
                [
                    {"role": "user", "content": request.question},
                    {"role": "assistant", "content": assistant_content},
                ]
            )

            yield ServerSentEvent(
                event="content",
                data={
                    "type": "content",
                    "content": assistant_content,
                },
            )

            seen_sources: set[tuple[str, int]] = set()
            for _, _, chunk in fee_answers:
                source_key = (chunk.document_id, chunk.chunk_index)
                if source_key in seen_sources:
                    continue
                seen_sources.add(source_key)

                yield ServerSentEvent(
                    event="citation",
                    data={
                        "type": "citation",
                        "document_id": chunk.document_id,
                        "source_name": chunk.source_name,
                        "chunk_index": chunk.chunk_index,
                        **(
                            {"page_number": chunk.page_number}
                            if chunk.page_number is not None
                            else {}
                        ),
                    },
                )

            yield ServerSentEvent(
                event="done",
                data={"type": "done"},
            )
            finish_trace("succeeded")
            return
        retrieval_method = (
            "hybrid_normalized"
            if normalized_query.added_terms
            else "hybrid"
        )
        retrieval_started_at = time.perf_counter()
        citation_chunks = retrieve_evidence(
            retrieval_question,
            document.chunks,
            limit=3,
            embed_texts=knowledge_repository.embed_texts,
            minimum_vector_score=0.40,
        )
        retrieval_duration_ms = int(
            (time.perf_counter() - retrieval_started_at) * 1000
        )

        if not citation_chunks:
            evidence_sufficient = False
            evidence_reason_code = "no_evidence"
            assistant_content = (
                "所选资料中未检索到与问题相关的内容，"
                "无法据此回答。"
            )

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
                event="content",
                data={
                    "type": "content",
                    "content": assistant_content,
                },
            )
            yield ServerSentEvent(
                event="done",
                data={"type": "done"},
            )
            finish_trace("rejected")
            return

        evidence_check = assess_evidence_sufficiency(
            retrieval_question,
            citation_chunks,
        )
        evidence_sufficient = evidence_check.sufficient
        evidence_reason_code = evidence_check.reason_code
        yield ServerSentEvent(
            event="evidence_check",
            data={
                "type": "evidence_check",
                **evidence_check.model_dump(),
            },
        )

        if not evidence_check.sufficient:
            assistant_content = (
                "所选资料中检索到了相关内容，"
                "但未找到回答该问题所需的明确证据，"
                "无法据此回答。"
            )
            history.extend(
                [
                    {"role": "user", "content": request.question},
                    {"role": "assistant", "content": assistant_content},
                ]
            )
            yield ServerSentEvent(
                event="content",
                data={
                    "type": "content",
                    "content": assistant_content,
                },
            )
            yield ServerSentEvent(
                event="done",
                data={"type": "done"},
            )
            finish_trace("rejected")
            return

        agent_question = build_grounded_question(
            request.question,
            citation_chunks,
        )

    assistant_parts: list[str] = []

    if citation_chunks:
        agent_events = stream_agent(
            agent_question,
            history=history,
            enable_tools=False,
        )
    else:
        agent_events = stream_agent(
            agent_question,
            history=history,
        )

    generation_started_at = time.perf_counter()
    async for event in agent_events:
        if event["type"] == "content":
            assistant_parts.append(event["content"])
        yield ServerSentEvent(
            event=event["type"],
            data=event,
        )

        if event["type"] == "error":
            generation_duration_ms = int(
                (time.perf_counter() - generation_started_at) * 1000
            )
            finish_trace(
                "failed",
                error_message=event.get("message", "模型生成失败"),
            )
            return
    generation_duration_ms = int(
        (time.perf_counter() - generation_started_at) * 1000
    )
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
    for chunk in citation_chunks:
        yield ServerSentEvent(
            event="citation",
            data={
                "type": "citation",
                "document_id": chunk.document_id,
                "source_name": chunk.source_name,
                "chunk_index": chunk.chunk_index,
                **(
                    {"page_number": chunk.page_number}
                    if chunk.page_number is not None
                    else {}
                ),
            },
        )

    yield ServerSentEvent(
        event="done",
        data={"type": "done"},
    )
    finish_trace("succeeded")
