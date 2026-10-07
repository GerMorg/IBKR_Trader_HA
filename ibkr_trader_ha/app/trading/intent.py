from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from app.domain.models import Decision, OrderIntent, idempotency_key, new_id
from app.domain.states import DecisionAction, OrderState


class OrderIntentBuilder:
    def __init__(self, max_slippage_bps: float) -> None:
        self.max_slippage_bps = Decimal(str(max_slippage_bps))

    def build(self, decision: Decision, price: Decimal, quantity: Decimal) -> OrderIntent:
        side = "BUY" if decision.target_position > decision.current_position else "SELL"
        action = "MKT" if decision.reduce_only else "LMT"
        limit = price if action == "LMT" else None
        return OrderIntent(
            intent_id=new_id("intent"),
            idempotency_key=idempotency_key(decision.instrument.contract.con_id, decision.action, decision.target_position),
            decision_id=decision.decision_id,
            con_id=decision.instrument.contract.con_id,
            action=decision.action,
            side=side,
            order_type=action,
            quantity=quantity,
            limit_price=limit,
            stop_price=None,
            leverage=decision.leverage,
            reduce_only=decision.reduce_only,
            max_slippage_bps=self.max_slippage_bps,
            state=OrderState.INTENT_CREATED,
        )

    @staticmethod
    def round_price(price: Decimal, tick: Decimal) -> Decimal:
        if tick <= 0:
            return price
        units = (price / tick).to_integral_value(rounding=ROUND_DOWN)
        return units * tick
