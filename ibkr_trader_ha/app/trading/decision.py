from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.domain.models import Decision, Instrument, PortfolioState, Signal, new_id
from app.domain.states import DecisionAction

D = Decimal


class DecisionEngine:
    VERSION = "decision-v1"

    def select(self, instrument: Instrument, long_signal: Signal, short_signal: Signal, portfolio: PortfolioState, model_scale: D = Decimal("1")) -> Decision | None:
        current = portfolio.positions.get(instrument.contract.con_id, D("0"))
        candidates = [
            signal for signal in (long_signal, short_signal)
            if signal.net_edge_bps > 0 and signal.confidence * model_scale >= D("0.50")
        ]
        if not candidates:
            if current != 0:
                held = long_signal if current > 0 else short_signal
                if held.net_edge_bps <= 0:
                    return Decision(
                        new_id("decision"), instrument, held,
                        DecisionAction.EXIT, D("0"), current, abs(current),
                        D("1"), True, self.VERSION, "base-v1",
                        {"reason": "negative_held_edge"},
                    )
            return None
        best = max(candidates, key=lambda s: (s.net_edge_bps, s.confidence))
        action = best.action
        if current < 0 and action == DecisionAction.LONG:
            return Decision(new_id("decision"), instrument, best, DecisionAction.REBALANCE, D("0"), current, abs(current), D("1"), True, self.VERSION, "base-v1", {"reason": "reverse_to_flat"})
        if current > 0 and action == DecisionAction.SHORT:
            return Decision(new_id("decision"), instrument, best, DecisionAction.REBALANCE, D("0"), current, abs(current), D("1"), True, self.VERSION, "base-v1", {"reason": "reverse_to_flat"})
        return Decision(
            new_id("decision"), instrument, best, action, D("0"), current, D("0"),
            D("1"), False, self.VERSION, "base-v1",
            {"selected_edge_bps": str(best.net_edge_bps), "confidence": str(best.confidence)},
        )

    @staticmethod
    def with_position(decision: Decision, target_position: D, quantity_notional: D, leverage: D, reduce_only: bool) -> Decision:
        return replace(
            decision,
            target_position=target_position,
            quantity_notional=quantity_notional,
            leverage=leverage,
            reduce_only=reduce_only,
        )
