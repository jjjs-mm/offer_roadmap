from decimal import Decimal
import pytest
from mini_agent.portfolio import analyze_portfolio_csv


def test_analyze_portfolio_csv() -> None:
    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,20,100\n"
        "债券基金,bond_fund,20,50\n"
        "现金,cash,1000,1\n"
    )

    result = analyze_portfolio_csv(csv_content)

    assert result.position_count == 3
    assert result.total_market_value == Decimal("4000")

    assert result.largest_position.name == "股票基金"
    assert result.largest_position.market_value == Decimal("2000")
    assert result.largest_position.weight == Decimal("0.5")

    assert result.asset_allocation == {
        "equity_fund": Decimal("0.5"),
        "bond_fund": Decimal("0.25"),
        "cash": Decimal("0.25"),
    }

    assert result.concentration_hhi == Decimal("0.375")

@pytest.mark.parametrize(
    ("csv_content", "expected_message"),
    [
        (
            (
                "name,asset_type,quantity\n"
                "股票基金,equity_fund,20\n"
            ),
            "CSV 缺少必要列: price",
        ),
        (
            (
                "name,asset_type,quantity,price\n"
                "股票基金,equity_fund,not-a-number,100\n"
            ),
            "第 2 行包含无效数字",
        ),
        (
            (
                "name,asset_type,quantity,price\n"
                "股票基金,equity_fund,-1,100\n"
            ),
            "第 2 行的 quantity 必须大于 0",
        ),
        (
            "name,asset_type,quantity,price\n",
            "CSV 中没有持仓数据",
        ),
    ],
)
def test_analyze_portfolio_rejects_invalid_csv(
    csv_content: str,
    expected_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=expected_message,
    ):
        analyze_portfolio_csv(csv_content)