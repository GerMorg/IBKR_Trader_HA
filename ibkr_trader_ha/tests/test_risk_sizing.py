from decimal import Decimal

from app.domain.models import Decision, Signal, PortfolioState
from app.domain.states import DecisionAction
from app.risk import LeverageEngine, PositionSizer, RiskEngine


def make_decision(equity) -> Decision:
    signal = Signal(
        1001, DecisionAction.LONG, Decimal("0.85"), Decimal("0.02"),
        Decimal("0.01"), Decimal("80"), Decimal("10"), 24, Decimal("0"),
        "test", {}, Decimal("0.95"),
    )
    return Decision("d1", equity, signal, DecisionAction.LONG, Decimal("500"),
                    Decimal("0"), Decimal("500"), Decimal("1"), False,
                    "test", "model", {})


def test_sizer_respects_position_and_order_caps(equity) -> None:
    sizer = PositionSizer(0.5, 8, 3)
    qty, notional = sizer.size(equity, Decimal("100"), Decimal("2"), Decimal("10000"))
    assert qty > 0
    assert notional <= Decimal("300")


def test_leverage_is_bounded(equity) -> None:
    lev = LeverageEngine().choose(equity, Decimal("0.95"), Decimal("1"), Decimal("10"))
    assert Decimal("1") <= lev <= Decimal("5")


def test_risk_blocks_daily_loss(equity, snapshot, config) -> None:
    risk = RiskEngine(config)
    p = PortfolioState(equity=Decimal("10000"), cash=Decimal("5000"), available_funds=Decimal("5000"), daily_pnl=Decimal("-300"))
    d = make_decision(equity)
    result = risk.evaluate(d, p, snapshot, None, 0)
    assert result.allowed is False
    assert result.reason == "daily_loss"


def test_risk_allows_safe_reduce_only(equity, snapshot, config) -> None:
    risk = RiskEngine(config)
    p = PortfolioState(equity=Decimal("10000"), cash=Decimal("5000"), available_funds=Decimal("5000"), positions={1001: Decimal("1000")})
    signal = Signal(1001, DecisionAction.EXIT, Decimal("0.9"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 1, Decimal("0"), "exit", {}, Decimal("1"))
    d = Decision("d2", equity, signal, DecisionAction.EXIT, Decimal("0"), Decimal("1000"), Decimal("1000"), Decimal("1"), True, "v", "m", {})
    result = risk.evaluate(d, p, snapshot, None, 0)
    assert result.allowed
