import re

from mini_agent.knowledge import KnowledgeChunk


FEE_TERMS = (
    "管理费",
    "托管费",
    "申购费",
    "赎回费",
)

PERCENT_RATE = re.compile(r"\d+(?:\.\d+)?\s*[%％]")


def find_fee_rate(
    term: str,
    chunks: list[KnowledgeChunk],
) -> tuple[str, KnowledgeChunk] | None:
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", chunk.content)

        # “不收取申购费用和赎回费用”也是明确答案，不应被当作缺失。
        for clause in re.split(r"[。；;]", normalized):
            if term in clause and "不收取" in clause:
                return "不收取", chunk

        search_start = 0
        while True:
            term_position = normalized.find(term, search_start)
            if term_position == -1:
                break

            rate_start = term_position + len(term)
            # PDF 表格经常把名称、说明和费率拆成多行，因此允许在
            # 费用词后有限窗口内查找，但不能跨到下一种费用。
            window = normalized[rate_start:rate_start + 240]
            match = PERCENT_RATE.search(window)
            if match is not None:
                between = window[:match.start()]
                crossed_other_fee = any(
                    other_term in between
                    for other_term in FEE_TERMS
                    if other_term != term
                )
                explicitly_missing = any(
                    marker in between
                    for marker in ("未披露", "未提供")
                )
                if not crossed_other_fee and not explicitly_missing:
                    return match.group(), chunk

            search_start = rate_start

    return None


def missing_fee_terms(
    question: str,
    chunks: list[KnowledgeChunk],
) -> list[str]:
    return [
        term
        for term in FEE_TERMS
        if term in question
        and find_fee_rate(term, chunks) is None
    ]
