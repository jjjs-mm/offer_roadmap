from decimal import Decimal

from mini_agent.portfolio import analyze_portfolio_csv
from mini_agent.portfolio_risk import assess_portfolio_risk


def test_concentrated_portfolio_is_high_risk() -> None:
    csv_content = (
        "name,asset_type,quantity,price\n"
        "股票基金,equity_fund,50,100\n"
        "债券基金,bond_fund,25,100\n"
        "货币基金,cash,25,100\n"
    )
    analysis = analyze_portfolio_csv(csv_content)

    report = assess_portfolio_risk(analysis)

    assert report.overall_level == "high"

    signals = {
        signal.code: signal
        for signal in report.signals
    }

    assert (
        signals["largest_position_concentration"].severity
        == "high"
    )
    assert (
        signals["largest_position_concentration"].observed_value
        == Decimal("0.5000")
    )
    assert signals["hhi_concentration"].severity == "high"
    assert "不构成投资建议" in report.disclaimer


def test_hhi_boundary_is_medium_risk() -> None:
    csv_content = (
        "name,asset_type,quantity,price\n"
        "基金A,bond_fund,25,100\n"
        "基金B,bond_fund,25,100\n"
        "基金C,bond_fund,25,100\n"
        "基金D,bond_fund,25,100\n"
    )
    analysis = analyze_portfolio_csv(csv_content)

    report = assess_portfolio_risk(analysis)

    assert report.overall_level == "medium"
    assert any(
        signal.code == "hhi_concentration"
        and signal.severity == "medium"
        for signal in report.signals
    )


def test_diversified_portfolio_is_low_risk() -> None:
    csv_content = (
        "name,asset_type,quantity,price\n"
        "基金A,bond_fund,20,100\n"
        "基金B,bond_fund,20,100\n"
        "基金C,bond_fund,20,100\n"
        "基金D,bond_fund,20,100\n"
        "基金E,bond_fund,20,100\n"
    )
    analysis = analyze_portfolio_csv(csv_content)

    report = assess_portfolio_risk(analysis)

    assert report.overall_level == "low"
    assert report.signals == []