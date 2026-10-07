from decimal import Decimal

from app.domain.models import idempotency_key
from app.domain.states import DecisionAction


def test_idempotency_key_is_stable() -> None:
    left = idempotency_key(10, DecisionAction.LONG, Decimal("123.450000000"))
    right = idempotency_key(10, DecisionAction.LONG, Decimal("123.45"))
    assert left == right
    assert len(left) == 40


def test_direction_changes_key() -> None:
    assert idempotency_key(10, DecisionAction.LONG, Decimal("10")) != idempotency_key(10, DecisionAction.SHORT, Decimal("10"))
