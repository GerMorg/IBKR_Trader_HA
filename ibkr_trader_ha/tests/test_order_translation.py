from decimal import Decimal
import pytest

from app.execution import OrderTranslator
from app.domain.models import OrderIntent
from app.domain.states import DecisionAction, OrderState


def test_tick_rounding() -> None:
    assert OrderTranslator.round_price(Decimal("101.237"), Decimal("0.05")) == Decimal("101.20")


def test_unsupported_order_type_rejected(equity) -> None:
    intent = OrderIntent("i", "k", "d", 1001, DecisionAction.LONG, "BUY", "PEG", Decimal("1"), None, None, Decimal("1"), False, Decimal("20"))
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        OrderTranslator.translate(intent, equity)
