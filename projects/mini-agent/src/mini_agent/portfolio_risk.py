from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from mini_agent.portfolio import PortfolioAnalysis


RiskLevel = Literal["low", "medium", "high"]


class RiskSignal(BaseModel):
    code: str
    severity: Literal["medium", "high"]
    message: str
    observed_value: Decimal = Field(ge=0, le=1)
    threshold: Decimal = Field(ge=0, le=1)


class PortfolioRiskReport(BaseModel):
    overall_level: RiskLevel
    signals: list[RiskSignal]
    disclaimer: str

class PortfolioRiskAssessment(BaseModel):
    portfolio_id: str
    report: PortfolioRiskReport

HIGH_LARGEST_POSITION = Decimal("0.5000")
MEDIUM_LARGEST_POSITION = Decimal("0.3000")

HIGH_HHI = Decimal("0.3500")
MEDIUM_HHI = Decimal("0.2500")

HIGH_EQUITY_EXPOSURE = Decimal("0.8000")
MEDIUM_EQUITY_EXPOSURE = Decimal("0.6000")

MEDIUM_CASH_EXPOSURE = Decimal("0.5000")

DISCLAIMER = (
    "本报告仅基于预设规则分析用户提供的数据，"
    "不构成投资建议。"
)


def assess_portfolio_risk(
    analysis: PortfolioAnalysis,
) -> PortfolioRiskReport:
    signals: list[RiskSignal] = []

    largest_weight = analysis.largest_position.weight

    if largest_weight >= HIGH_LARGEST_POSITION:
        signals.append(
            RiskSignal(
                code="largest_position_concentration",
                severity="high",
                message="最大单一持仓占比较高",
                observed_value=largest_weight,
                threshold=HIGH_LARGEST_POSITION,
            )
        )
    elif largest_weight >= MEDIUM_LARGEST_POSITION:
        signals.append(
            RiskSignal(
                code="largest_position_concentration",
                severity="medium",
                message="最大单一持仓占比需要关注",
                observed_value=largest_weight,
                threshold=MEDIUM_LARGEST_POSITION,
            )
        )

    hhi = analysis.concentration_hhi

    if hhi >= HIGH_HHI:
        signals.append(
            RiskSignal(
                code="hhi_concentration",
                severity="high",
                message="持仓集中度 HHI 较高",
                observed_value=hhi,
                threshold=HIGH_HHI,
            )
        )
    elif hhi >= MEDIUM_HHI:
        signals.append(
            RiskSignal(
                code="hhi_concentration",
                severity="medium",
                message="持仓集中度 HHI 需要关注",
                observed_value=hhi,
                threshold=MEDIUM_HHI,
            )
        )

    equity_exposure = analysis.asset_allocation.get(
        "equity_fund",
        Decimal("0"),
    )

    if equity_exposure >= HIGH_EQUITY_EXPOSURE:
        signals.append(
            RiskSignal(
                code="equity_exposure",
                severity="high",
                message="权益类资产占比较高",
                observed_value=equity_exposure,
                threshold=HIGH_EQUITY_EXPOSURE,
            )
        )
    elif equity_exposure >= MEDIUM_EQUITY_EXPOSURE:
        signals.append(
            RiskSignal(
                code="equity_exposure",
                severity="medium",
                message="权益类资产占比需要关注",
                observed_value=equity_exposure,
                threshold=MEDIUM_EQUITY_EXPOSURE,
            )
        )

    cash_exposure = analysis.asset_allocation.get(
        "cash",
        Decimal("0"),
    )

    if cash_exposure >= MEDIUM_CASH_EXPOSURE:
        signals.append(
            RiskSignal(
                code="cash_concentration",
                severity="medium",
                message="现金类资产占比较高",
                observed_value=cash_exposure,
                threshold=MEDIUM_CASH_EXPOSURE,
            )
        )

    if any(
        signal.severity == "high"
        for signal in signals
    ):
        overall_level: RiskLevel = "high"
    elif signals:
        overall_level = "medium"
    else:
        overall_level = "low"

    return PortfolioRiskReport(
        overall_level=overall_level,
        signals=signals,
        disclaimer=DISCLAIMER,
    )
