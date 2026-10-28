import math
from collections.abc import Callable
from functools import lru_cache

from fastembed import TextEmbedding

from mini_agent.knowledge import KnowledgeChunk
from mini_agent.retrieval import rank_chunks


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_MINIMUM_VECTOR_SCORE = 0.65
EmbedTexts = Callable[[list[str]], list[list[float]]]


class LocalTextEmbedder:
    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.model_name = model_name
        self._model: TextEmbedding | None = None
        self._query_cache: dict[str, list[float]] = {}
        self._passage_cache: dict[str, list[float]] = {}

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            self._model = TextEmbedding(
                model_name=self.model_name,
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        query = texts[0]
        passages = texts[1:]

        if query not in self._query_cache:
            query_vector = next(
                iter(self._get_model().query_embed(query))
            )
            self._query_cache[query] = query_vector.tolist()

        missing_passages = [
            text for text in dict.fromkeys(passages)
            if text not in self._passage_cache
        ]
        if missing_passages:
            passage_vectors = self._get_model().passage_embed(
                missing_passages
            )
            for text, vector in zip(
                missing_passages,
                passage_vectors,
                strict=True,
            ):
                self._passage_cache[text] = vector.tolist()

        return [self._query_cache[query]] + [
            self._passage_cache[text] for text in passages
        ]


@lru_cache(maxsize=1)
def get_default_embedder() -> LocalTextEmbedder:
    return LocalTextEmbedder()


def _cosine_similarity(
    left: list[float],
    right: list[float],
) -> float:
    if len(left) != len(right):
        raise ValueError("向量维度不一致")

    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def rank_chunks_by_vector(
    query: str,
    chunks: list[KnowledgeChunk],
    embed_texts: EmbedTexts,
    limit: int = 5,
    minimum_score: float = DEFAULT_MINIMUM_VECTOR_SCORE,
) -> list[KnowledgeChunk]:
    if not query.strip():
        raise ValueError("查询词不能为空")
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if not 0 <= minimum_score <= 1:
        raise ValueError("minimum_score 必须在 0 到 1 之间")
    if not chunks:
        return []

    vectors = embed_texts(
        [query] + [chunk.content for chunk in chunks]
    )
    query_vector = vectors[0]
    ranked: list[tuple[float, int, KnowledgeChunk]] = []

    for position, (chunk, vector) in enumerate(
        zip(chunks, vectors[1:], strict=True)
    ):
        score = _cosine_similarity(query_vector, vector)
        if score >= minimum_score:
            ranked.append((-score, position, chunk))

    ranked.sort()
    return [chunk for _, _, chunk in ranked[:limit]]


def reciprocal_rank_fusion(
    rankings: list[list[KnowledgeChunk]],
    limit: int = 5,
    rank_constant: int = 60,
) -> list[KnowledgeChunk]:
    if limit < 1:
        raise ValueError("limit 必须大于 0")
    if rank_constant < 1:
        raise ValueError("rank_constant 必须大于 0")

    scores: dict[tuple[str, int], float] = {}
    chunks_by_key: dict[tuple[str, int], KnowledgeChunk] = {}
    first_seen: dict[tuple[str, int], int] = {}
    order = 0

    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            key = (chunk.document_id, chunk.chunk_index)
            chunks_by_key[key] = chunk
            if key not in first_seen:
                first_seen[key] = order
                order += 1
            scores[key] = scores.get(key, 0.0) + (
                1 / (rank_constant + rank)
            )

    ordered_keys = sorted(
        scores,
        key=lambda key: (-scores[key], first_seen[key]),
    )
    return [chunks_by_key[key] for key in ordered_keys[:limit]]


def rank_chunks_hybrid(
    query: str,
    chunks: list[KnowledgeChunk],
    embed_texts: EmbedTexts,
    limit: int = 5,
    minimum_vector_score: float = DEFAULT_MINIMUM_VECTOR_SCORE,
) -> list[KnowledgeChunk]:
    lexical = rank_chunks(query, chunks, limit=len(chunks) or 1)
    semantic = rank_chunks_by_vector(
        query,
        chunks,
        embed_texts,
        limit=len(chunks) or 1,
        minimum_score=minimum_vector_score,
    )
    return reciprocal_rank_fusion(
        [lexical, semantic],
        limit=limit,
    )
