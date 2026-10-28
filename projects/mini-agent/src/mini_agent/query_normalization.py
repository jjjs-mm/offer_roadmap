"""Conservative normalization for common fund-research questions.

The normalizer never rewrites the user's question.  It adds a small set of
domain terms to the *internal* retrieval query so that natural wording such
as "能买股票吗" can retrieve the prospectus field "投资范围".  The original
question is still used when constructing the final grounded prompt.
"""

import re

from pydantic import BaseModel


class NormalizedFinancialQuery(BaseModel):
    """The original question plus auditable retrieval-only enrichments."""

    original_question: str
    retrieval_query: str
    added_terms: list[str]


_NORMALIZATION_RULES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(r"(?:联接基金.*(?:投向|投资).*ETF|目标ETF)"),
        ("投资范围", "目标ETF", "投资比例"),
    ),
    (
        re.compile(r"(?:能|会|是否).{0,6}(?:买|配置|投资).{0,6}股票"),
        ("投资范围", "是否投资", "股票"),
    ),
    (
        re.compile(r"(?:股票仓位|股票.{0,6}(?:上限|区间|比例))"),
        ("投资范围", "投资比例", "股票"),
    ),
    (
        re.compile(r"(?:权益类资产|权益市场|权益仓位)"),
        ("投资范围", "投资于", "股票"),
    ),
    (
        re.compile(r"(?:配置哪些投资品种|投资哪些品种|哪些投资品种)"),
        ("投资范围", "投资于", "金融工具"),
    ),
    (
        re.compile(r"(?:跟踪|复制).{0,8}(?:哪|什么).{0,4}指数"),
        ("标的指数", "跟踪指数"),
    ),
    (
        re.compile(r"(?:基准指数|对应的指数)"),
        ("标的指数", "跟踪指数"),
    ),
    (
        re.compile(r"(?:境内外市场|境内.*境外|境外.*境内)"),
        ("投资范围", "境内市场", "境外市场"),
    ),
    (
        re.compile(r"申购.{0,8}赎回.{0,8}(?:付费|收费|费用)"),
        ("申购费", "赎回费"),
    ),
    (
        re.compile(r"赎回.{0,8}(?:费率|收费|费用|付费|多少)"),
        ("赎回费",),
    ),
    (
        re.compile(r"(?:托管服务|托管成本).{0,8}(?:费率|收费|费用|比例|多少)"),
        ("托管费",),
    ),
    (
        re.compile(r"(?:资产配置思路|配置策略|筛选.{0,4}(?:公司|企业)|选股思路|完全复制|抽样复制)"),
        ("主要投资策略", "投资策略"),
    ),
    (
        re.compile(r"(?:风险收益定位|风险收益类别|风险档)"),
        ("风险收益特征", "风险水平"),
    ),
    (
        re.compile(r"(?:资产类别|配置什么资产)"),
        ("投资范围", "投资于", "金融工具"),
    ),
)


def normalize_financial_query(question: str) -> NormalizedFinancialQuery:
    """Add precise fund-domain aliases for retrieval and evidence checks.

    Rules are deliberately narrow: unmatched questions return unchanged,
    preventing query expansion from turning unsupported questions into an
    apparently answerable one.
    """
    original_question = question.strip()
    added_terms: list[str] = []

    for pattern, terms in _NORMALIZATION_RULES:
        if not pattern.search(original_question):
            continue
        for term in terms:
            if term not in added_terms:
                added_terms.append(term)

    retrieval_query = " ".join((original_question, *added_terms)).strip()
    return NormalizedFinancialQuery(
        original_question=original_question,
        retrieval_query=retrieval_query,
        added_terms=added_terms,
    )
