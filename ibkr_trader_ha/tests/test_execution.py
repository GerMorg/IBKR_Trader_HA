from __future__ import annotations

from decimal import Decimal

from app.config import Config
from app.domain.models import Decision, PortfolioState, Signal
from app.domain.states import DecisionAction, OrderState
from app.execution import ExecutionEngine
from app.persistence import Database


class FakeIBKR:
    def __init__(self) -> None:
        self.next_order = 100
        self.what_if_calls = 0
        self.place_calls = 0
        self.statuses: dict[int, dict[str, str]] = {}

    def what_if(self, query, order):
        self.what_if_calls += 1
        return {"status": "PreSubmitted", "init_margin_change": "100", "maint_margin_change": "50"}

    def place_order(self, query, order):
        self.place_calls += 1
        order_id = self.next_order
        self.next_order += 1
        self.statuses[order_id] = {"status": "Submitted", "filled": "0", "remaining": str(order["quantity"])}
        return order_id

    def order_status(self, order_id):
        return self.statuses.get(order_id, {})


def _decision(equity) -> Decision:
    signal = Signal(
        1001, DecisionAction.LONG, Decimal("0.90"), Decimal("0.02"),
        Decimal("0.01"), Decimal("100"), Decimal("10"), 24, Decimal("0"),
        "test", {}, Decimal("1"),
    )
    return Decision(
        "d-exec", equity, signal, DecisionAction.LONG, Decimal("300"),
        Decimal("0"), Decimal("300"), Decimal("1"), False, "v1", "m1", {},
    )


def test_execution_preflight_and_idempotency(equity, snapshot) -> None:
    config = Config.from_mapping({
        "trading_mode": "paper",
        "trading_enabled": True,
        "kill_switch": False,
        "require_what_if": True,
        "gemini_enabled": False,
        "news_enabled": False,
        "database_path": ":memory:",
    })
    db = Database(":memory:")
    db.save_portfolio(PortfolioState(
        account_id="U1", equity=Decimal("10000"), cash=Decimal("9000"),
        available_funds=Decimal("8000"), buying_power=Decimal("20000"),
        positions={}, gross_exposure=Decimal("0"), net_exposure=Decimal("0"),
        valuation_complete=True,
    ))
    fake = FakeIBKR()
    engine = ExecutionEngine(fake, db, __import__("app.risk", fromlist=["RiskEngine"]).RiskEngine(config), config, __import__("app.monitoring", fromlist=["AuditLogger"]).AuditLogger(False))
    decision = _decision(equity)
    result = engine.execute(decision, snapshot, None, 0, cycle_id="c1")
    assert result["state"] in {OrderState.ACKNOWLEDGED.value, OrderState.LIVE.value}
    assert fake.what_if_calls == 1
    assert fake.place_calls == 1
    duplicate = engine.execute(decision, snapshot, None, 0, cycle_id="c1")
    assert duplicate["reason"] == "DUPLICATE_INTENT"


def test_execution_kill_switch_blocks_before_broker_call(equity, snapshot) -> None:
    config = Config.from_mapping({
        "trading_mode": "paper",
        "trading_enabled": True,
        "kill_switch": True,
        "gemini_enabled": False,
        "news_enabled": False,
        "database_path": ":memory:",
    })
    db = Database(":memory:")
    fake = FakeIBKR()
    engine = ExecutionEngine(fake, db, __import__("app.risk", fromlist=["RiskEngine"]).RiskEngine(config), config, __import__("app.monitoring", fromlist=["AuditLogger"]).AuditLogger(False))
    result = engine.execute(_decision(equity), snapshot, None, 0)
    assert result["reason"] == "KILL_SWITCH"
    assert fake.place_calls == 0
