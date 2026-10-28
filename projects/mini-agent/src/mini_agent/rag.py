from mini_agent.knowledge import KnowledgeChunk
from mini_agent.retrieval import rank_chunks
from mini_agent.semantic_retrieval import (
    EmbedTexts,
    rank_chunks_hybrid,
)


def retrieve_evidence(
    question: str,
    chunks: list[KnowledgeChunk],
    limit: int = 3,
    embed_texts: EmbedTexts | None = None,
    minimum_vector_score: float = 0.40,
) -> list[KnowledgeChunk]:
    if embed_texts is not None:
        return rank_chunks_hybrid(
            question,
            chunks,
            embed_texts,
            limit=limit,
            minimum_vector_score=minimum_vector_score,
        )
    return rank_chunks(
        question,
        chunks,
        limit=limit,
    )


def build_grounded_question(
    question: str,
    evidence: list[KnowledgeChunk],
) -> str:
    if not question.strip():
        raise ValueError("问题不能为空")

    if not evidence:
        raise ValueError("证据不能为空")

    evidence_text = "\n\n".join(
        (
            f"[资料 {index}]\n"
            f"{chunk.content}"
        )
        for index, chunk in enumerate(
            evidence,
            start=1,
        )
    )

    return (
        "你是基金研究助手。"
        "只能根据以下资料回答用户问题。"
        "如果资料不足，请明确说明无法回答，"
        "不要猜测，也不要使用资料之外的知识。"
        "回答应当简洁、准确。\n\n"
        f"{evidence_text}\n\n"
        f"用户问题：{question.strip()}"
    )
