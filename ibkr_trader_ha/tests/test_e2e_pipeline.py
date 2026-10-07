from __future__ import annotations

from decimal import Decimal
import time

from app.domain.models import MarketSnapshot
from app.learning import LearningEngine
from app.market import FeatureEngine, RegimeEngine
from app.monitoring import AuditLogger
from app.persistence import Database
from app.risk import RiskEngine
from app.strategy import StrategyDispatcher
from app.trading import DecisionEngine


class FakeConfig:
    strategy_min_edge_bps = 25
    strategy_min_confidence = 0.60
    risk_daily_loss_pct = 2
    risk_max_drawdown_pct = 6
    risk_max_position_pct = 8
    risk_max_order_pct = 3
    risk_max_gross_pct = 60
    risk_max_net_pct = 40
    risk_cash_reserve_pct = 20
    risk_max_open_positions = 8
    risk_max_orders_per_day = 12
    risk_max_leverage = 5
    max_market_data_age_seconds = 30
    max_spread_bps = 60


def test_discovery_analysis_decision_risk_learning_pipeline(equity) -> None:
    db = Database(":memory:")
    features = FeatureEngine().calculate(
        MarketSnapshot(1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1"),
                       closes=tuple(Decimal(str(v)) for v in [95, 97, 99, 101, 104, 106])),
        [{"close": str(v)} for v in [95, 97, 99, 101, 104, 106]],
    )
    snapshot = MarketSnapshot(
        1001, time.time(), Decimal("100"), Decimal("99.9"), Decimal("100.1"),
        closes=(Decimal("95"), Decimal("97"), Decimal("99"), Decimal("101"), Decimal("104"), Decimal("106")),
    )
    pair = StrategyDispatcher().evaluate(
        equity, snapshot, features, RegimeEngine().detect(features), Decimal("10"), Decimal("5")
    )
    assert pair is not None
    decision = DecisionEngine().select(
        equity, pair[0], pair[1],
        __import__("app.domain.models", fromlist=["PortfolioState"]).PortfolioState(
            equity=Decimal("10000"), cash=Decimal("9000"), available_funds=Decimal("8000"),
            valuation_complete=True,
        ),
    )
    assert decision is not None
    decision = DecisionEngine.with_position(decision, Decimal("250"), Decimal("250"), Decimal("1"), False)
    risk = RiskEngine(FakeConfig()).evaluate(
        decision,
        __import__("app.domain.models", fromlist=["PortfolioState"]).PortfolioState(
            equity=Decimal("10000"), cash=Decimal("9000"), available_funds=Decimal("8000"),
            valuation_complete=True,
        ),
        snapshot, None, 0,
    )
    assert risk.allowed
    db.save_decision("c1", decision)
    learner = LearningEngine(db, type("C", (), {"learning_enabled": True, "learning_min_samples": 100, "learning_validation_fraction": 0.3, "learning_min_improvement": 0.01, "learning_auto_promotion": True})(), AuditLogger(False))
    learner.record_decision(decision, "c1")
    assert db.one("SELECT decision_id FROM learning_samples WHERE decision_id=?", (decision.decision_id,)) is not None
