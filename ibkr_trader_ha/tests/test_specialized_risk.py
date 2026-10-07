from decimal import Decimal
import time
from dataclasses import replace

from app.domain.models import MarketSnapshot, PortfolioState
from app.domain.states import AssetClass, DecisionAction
from app.risk import RiskEngine
from app.strategy import StrategyDispatcher


def test_short_requires_real_shortability(equity, snapshot, config) -> None:
    strategy_equity = replace(equity, asset_class=AssetClass.EQUITY)
    pair = StrategyDispatcher().evaluate(
        strategy_equity,
        snapshot,
        {"trend": Decimal("-2"), "momentum": Decimal("-1"), "volatility": Decimal("1")},
        "trend", Decimal("-5"), Decimal("-5"),
    )
    assert pair is not None
    decision = __import__("app.domain.models", fromlist=["Decision"]).Decision(
        "short-test", strategy_equity, pair[1], DecisionAction.SHORT, Decimal("-250"),
        Decimal("0"), Decimal("250"), Decimal("1"), False, "v", "m", {},
    )
    blocked = RiskEngine(config).evaluate(
        decision,
        PortfolioState(equity=Decimal("10000"), cash=Decimal("9000"), available_funds=Decimal("8000"), valuation_complete=True),
        snapshot,
        None,
        0,
    )
    assert blocked.allowed is False
    assert blocked.reason == "market_hours" or blocked.reason == "shortable"


def test_option_strategy_requires_greeks(equity) -> None:
    option = replace(equity, asset_class=AssetClass.OPTION)
    snapshot = MarketSnapshot(1001, time.time(), Decimal("10"), Decimal("9.9"), Decimal("10.1"))
    pair = StrategyDispatcher().evaluate(
        option, snapshot,
        {"trend": Decimal("1"), "momentum": Decimal("1"), "volatility": Decimal("2"), "spread_bps": Decimal("20")},
        "trend", Decimal("0"), Decimal("0"),
    )
    assert pair is not None
    assert pair[0].confidence < Decimal("0.10")


def test_futures_use_multiplier_in_sizing(equity) -> None:
    futures = replace(equity, asset_class=AssetClass.FUTURES, contract=replace(equity.contract, multiplier=Decimal("50"), min_size=Decimal("1"), size_increment=Decimal("1")))
    from app.risk import PositionSizer
    qty, notional = PositionSizer(0.5, 100, 100).size(futures, Decimal("100"), Decimal("1"), Decimal("500000"))
    assert qty >= 1
    assert notional % Decimal("50") == 0
