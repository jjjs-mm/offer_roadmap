import csv
from collections import defaultdict
from decimal import (
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)
from io import StringIO

from pydantic import BaseModel, Field


REQUIRED_COLUMNS = {
    "name",
    "asset_type",
    "quantity",
    "price",
}
RATIO_QUANTUM = Decimal("0.0001")

def _round_ratio(value: Decimal) -> Decimal:
    return value.quantize(
        RATIO_QUANTUM,
        rounding=ROUND_HALF_UP,
    )

class PositionMetric(BaseModel):
    name: str
    asset_type: str
    market_value: Decimal = Field(gt=0)
    weight: Decimal = Field(gt=0, le=1)


class PortfolioAnalysis(BaseModel):
    position_count: int = Field(gt=0)
    total_market_value: Decimal = Field(gt=0)
    positions: list[PositionMetric]
    largest_position: PositionMetric
    asset_allocation: dict[str, Decimal]
    concentration_hhi: Decimal = Field(gt=0, le=1)


def analyze_portfolio_csv(
    csv_content: str,
) -> PortfolioAnalysis:
    reader = csv.DictReader(StringIO(csv_content))

    if reader.fieldnames is None:
        raise ValueError("CSV 缺少表头")

    missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CSV 缺少必要列: {missing}")

    raw_positions: list[
        tuple[str, str, Decimal]
    ] = []

    for line_number, row in enumerate(reader, start=2):
        name = (row.get("name") or "").strip()
        asset_type = (row.get("asset_type") or "").strip()

        if not name:
            raise ValueError(
                f"第 {line_number} 行的 name 不能为空"
            )

        if not asset_type:
            raise ValueError(
                f"第 {line_number} 行的 asset_type 不能为空"
            )

        try:
            quantity = Decimal(
                (row.get("quantity") or "").strip()
            )
            price = Decimal(
                (row.get("price") or "").strip()
            )
        except InvalidOperation as error:
            raise ValueError(
                f"第 {line_number} 行包含无效数字"
            ) from error

        if not quantity.is_finite() or quantity <= 0:
            raise ValueError(
                f"第 {line_number} 行的 quantity 必须大于 0"
            )

        if not price.is_finite() or price <= 0:
            raise ValueError(
                f"第 {line_number} 行的 price 必须大于 0"
            )

        market_value = quantity * price
        raw_positions.append(
            (name, asset_type, market_value)
        )

    if not raw_positions:
        raise ValueError("CSV 中没有持仓数据")

    total_market_value = sum(
        (
            market_value
            for _, _, market_value in raw_positions
        ),
        Decimal("0"),
    )

    positions = [
        PositionMetric(
            name=name,
            asset_type=asset_type,
            market_value=market_value,
            weight=_round_ratio(
            market_value / total_market_value
            ),
        )
        for name, asset_type, market_value in raw_positions
    ]

    largest_position = max(
        positions,
        key=lambda position: position.market_value,
    )

    asset_values: defaultdict[str, Decimal] = defaultdict(
        lambda: Decimal("0")
    )

    for position in positions:
        asset_values[position.asset_type] += (
            position.market_value
        )

    asset_allocation = {
    asset_type: _round_ratio(
        market_value / total_market_value
    )
    for asset_type, market_value in asset_values.items()
    }

    concentration_hhi = _round_ratio(
    sum(
        (
            (
                market_value
                / total_market_value
            )
            ** 2
            for _, _, market_value in raw_positions
        ),
        Decimal("0"),
    )
    )

    return PortfolioAnalysis(
        position_count=len(positions),
        total_market_value=total_market_value,
        positions=positions,
        largest_position=largest_position,
        asset_allocation=asset_allocation,
        concentration_hhi=concentration_hhi,
    )