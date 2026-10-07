from decimal import Decimal
import time

from app.learning import LearningEngine
from app.persistence import Database
from app.monitoring import AuditLogger


def test_persistence_and_idempotency(equity, config) -> None:
    db = Database(":memory:")
    from app.domain.models import Signal, Decision
    from app.domain.states import DecisionAction
    signal = Signal(
        1001, DecisionAction.LONG, Decimal("0.8"), Decimal("0.02"),
        Decimal("0.01"), Decimal("80"), Decimal("10"), 24, Decimal("0"),
        "x", {}, Decimal("1"),
    )
    decision = Decision(
        "d1", equity, signal, DecisionAction.LONG, Decimal("100"),
        Decimal("0"), Decimal("100"), Decimal("1"), False, "v", "m", {},
    )
    from app.trading.intent import OrderIntentBuilder
    intent = OrderIntentBuilder(20).build(decision, Decimal("100"), Decimal("1"))
    assert db.save_intent(intent) is True
    assert db.save_intent(intent) is False
    assert db.intent_exists(intent.idempotency_key)


def test_learning_starts_safely_when_data_is_insufficient(config) -> None:
    db = Database(":memory:")
    engine = LearningEngine(db, config, AuditLogger(False))
    result = engine.recalibrate()
    assert result["status"] == "INSUFFICIENT_DATA"


def test_learning_marks_profitable_outcome_to_market(config) -> None:
    db = Database(":memory:")
    engine = LearningEngine(db, config, AuditLogger(False))
    signal = __import__("app.domain.models", fromlist=["Signal"]).Signal(
        1001, __import__("app.domain.states", fromlist=["DecisionAction"]).DecisionAction.LONG,
        Decimal("0.9"), Decimal("0.02"), Decimal("0.01"), Decimal("80"), Decimal("10"),
        0, Decimal("0"), "x", {}, Decimal("1"),
    )
    decision = __import__("app.domain.models", fromlist=["Decision"]).Decision(
        "d-learning", __import__("conftest").equity() if False else type("I", (), {"contract": type("C", (), {"con_id": 1001})(), "asset_class": type("A", (), {"value": "EQUITY"})()})(),
        signal, __import__("app.domain.states", fromlist=["DecisionAction"]).DecisionAction.LONG,
        Decimal("100"), Decimal("0"), Decimal("100"), Decimal("1"), False, "v", "m", {},
        created_at=time.time() - 7200,
    )
    engine.record_decision(decision, "c")
    engine.record_fill("d-learning", {"execution_id": "x", "price": "100", "commission": "1"})
    result = engine.mark_to_market({1001: Decimal("105")})
    assert result["settled"] == 1
    row = db.one("SELECT outcome_status,payload_json FROM learning_samples WHERE sample_id='d-learning'")
    assert row["outcome_status"] == "SETTLED"
    assert '"success": true' in row["payload_json"]
