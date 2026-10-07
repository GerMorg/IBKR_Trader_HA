from decimal import Decimal
import json

from app.learning import LearningEngine
from app.persistence import Database


def test_persistence_and_idempotency(equity, config) -> None:
    db = Database(":memory:")
    from app.domain.models import Signal, Decision
    from app.domain.states import DecisionAction
    signal = Signal(1001, DecisionAction.LONG, Decimal("0.8"), Decimal("0.02"), Decimal("0.01"), Decimal("80"), Decimal("10"), 24, Decimal("0"), "x", {}, Decimal("1"))
    decision = Decision("d1", equity, signal, DecisionAction.LONG, Decimal("100"), Decimal("0"), Decimal("100"), Decimal("1"), False, "v", "m", {})
    from app.trading.intent import OrderIntentBuilder
    intent = OrderIntentBuilder(20).build(decision, Decimal("100"), Decimal("1"))
    assert db.save_intent(intent) is True
    assert db.save_intent(intent) is False
    assert db.intent_exists(intent.idempotency_key)


def test_learning_starts_safely_when_data_is_insufficient(config) -> None:
    db = Database(":memory:")
    logger = type("L", (), {"emit": lambda *args, **kwargs: None})()
    engine = LearningEngine(db, config, logger)
    result = engine.recalibrate()
    assert result["status"] == "INSUFFICIENT_DATA"
