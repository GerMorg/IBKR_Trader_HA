from decimal import Decimal
import time

from app.domain.models import MarketSnapshot
from app.domain.states import AssetClass
from app.strategy import StrategyDispatcher


def test_equity_strategy_produces_long_bias(equity) -> None:
    snap = MarketSnapshot(1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1"))
    pair = StrategyDispatcher().evaluate(
        equity, snap,
        {"trend": Decimal("2"), "momentum": Decimal("1"), "volatility": Decimal("1"), "spread_bps": Decimal("20")},
        "trend", Decimal("15"), Decimal("5"),
    )
    assert pair is not None
    assert pair[0].action.value == "LONG"
    assert pair[0].gross_edge_bps > 0


def test_unknown_strategy_returns_none(equity) -> None:
    unknown = __import__("dataclasses").replace(equity, asset_class=AssetClass.UNKNOWN)
    snap = MarketSnapshot(1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1"))
    assert StrategyDispatcher().evaluate(unknown, snap, {}, "range", Decimal("0"), Decimal("0")) is None
