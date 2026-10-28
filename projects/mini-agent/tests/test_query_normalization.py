import pytest

from mini_agent.query_normalization import normalize_financial_query


@pytest.mark.parametrize(
    ("question", "expected_terms"),
    [
        ("这只债基能买股票吗？", ["投资范围", "是否投资", "股票"]),
        ("股票仓位上限是多少？", ["投资范围", "投资比例", "股票"]),
        ("这个货币基金会配置哪些投资品种？", ["投资范围", "投资于", "金融工具"]),
        ("该ETF复制的是哪条指数？", ["标的指数", "跟踪指数"]),
        ("不足7天赎回的费率是多少？", ["赎回费"]),
        ("纯债产品会参与权益市场投资吗？", ["投资范围", "投资于", "股票"]),
        ("该 ETF 对应的基准指数是哪一个？", ["标的指数", "跟踪指数"]),
        ("托管服务每年按多少比例收费？", ["托管费"]),
        ("这只基金采用怎样的资产配置思路？", ["主要投资策略", "投资策略"]),
        ("产品在筛选上市公司时采用什么思路？", ["主要投资策略", "投资策略"]),
        ("买入后七天内卖出，赎回需要付费吗？", ["赎回费"]),
        ("全球配置覆盖哪些境内外市场？", ["投资范围", "境内市场", "境外市场"]),
        ("申购和赎回需要付费吗？", ["申购费", "赎回费"]),
    ],
)
def test_normalizes_natural_fund_question_to_retrieval_terms(
    question: str,
    expected_terms: list[str],
) -> None:
    result = normalize_financial_query(question)

    assert result.original_question == question
    assert result.added_terms == expected_terms
    for term in expected_terms:
        assert term in result.retrieval_query


def test_keeps_unmatched_question_unchanged() -> None:
    result = normalize_financial_query("2028年的收益率会是多少？")

    assert result.retrieval_query == "2028年的收益率会是多少？"
    assert result.added_terms == []
