from __future__ import annotations

from decimal import Decimal
from typing import Any

D = Decimal


class LeverageEngine:
    SAFETY_MAX = D("5")

    def choose(self, instrument: Any, confidence: D, volatility: D, configured_max: D) -> D:
        if not instrument.capability.can_margin:
            return D("1")
        broker_hint = instrument.contract.metadata.get("max_leverage")
        available = D(str(broker_hint)) if broker_hint not in (None, "") else self.SAFETY_MAX
        maximum = min(self.SAFETY_MAX, D(str(configured_max)), max(D("1"), available))
        if volatility >= D("8") or confidence < D("0.75"):
            return D("1")
        if confidence < D("0.85"):
            return min(D("2"), maximum)
        return maximum
