from decimal import Decimal
import time
from dataclasses import replace

import pytest

from app.domain.models import MarketSnapshot
from app.domain.states import AssetClass
from app.strategy import StrategyDispatcher


@pytest.mark.parametrize("asset_class", [
    AssetClass.EQUITY, AssetClass.ETF, AssetClass.FX, AssetClass.FUTURES,
    AssetClass.OPTION, AssetClass.FUTURES_OPTION, AssetClass.BOND, AssetClass.FUND,
])
def test_each_supported_asset_class_has_strategy(equity, asset_class) -> None:
    instrument = replace(equity, asset_class=asset_class)
    snap = MarketSnapshot(
        1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1"),
        implied_volatility=Decimal("0.35"),
        delta=Decimal("0.5"), gamma=Decimal("0.1"),
        theta=Decimal("-0.1"), vega=Decimal("0.2"),
    )
    pair = StrategyDispatcher().evaluate(
        instrument, snap,
        {"trend": Decimal("1.5"), "momentum": Decimal("0.8"),
         "volatility": Decimal("1.2"), "spread_bps": Decimal("20")},
        "trend", Decimal("10"), Decimal("5"),
    )
    assert pair is not None
    assert pair[0].con_id == 1001
    assert pair[1].con_id == 1001


def test_equity_strategy_produces_long_bias(equity) -> None:
    snap = MarketSnapshot(
        1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1")
    )
    pair = StrategyDispatcher().evaluate(
        equity, snap,
        {"trend": Decimal("2"), "momentum": Decimal("1"), "volatility": Decimal("1"), "spread_bps": Decimal("20")},
        "trend", Decimal("15"), Decimal("5"),
    )
    assert pair is not None
    assert pair[0].action.value == "LONG"
    assert pair[0].gross_edge_bps > 0


def test_unknown_strategy_returns_none(equity) -> None:
    unknown = replace(equity, asset_class=AssetClass.UNKNOWN)
    snap = MarketSnapshot(1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1"))
    assert StrategyDispatcher().evaluate(unknown, snap, {}, "range", Decimal("0"), Decimal("0")) is None
