import unicodedata

from mini_agent.knowledge import KnowledgeChunk


def _bigrams(text: str) -> set[str]:
    normalized = "".join(
        char.lower()
        for char in unicodedata.normalize("NFKC", text)
        if char.isalnum()
    )
    return {
        normalized[index:index + 2]
        for index in range(len(normalized) - 1)
    }


def rank_chunks(
    query: str,
    chunks: list[KnowledgeChunk],
    limit: int = 5,
) -> list[KnowledgeChunk]:
    if not query.strip():
        raise ValueError("查询词不能为空")
    if limit < 1:
        raise ValueError("limit 必须大于 0")

    query_grams = _bigrams(query)

    minimum_score = (
       1
       if len(query_grams) <= 2
        else 2
    )

    ranked: list[
       tuple[int, int, KnowledgeChunk]
    ] = []

    for position, chunk in enumerate(chunks):
        score = len(query_grams & _bigrams(chunk.content))
        if score >= minimum_score:
           ranked.append(
           (-score, position, chunk)
        )

    ranked.sort()
    return [chunk for _, _, chunk in ranked[:limit]]