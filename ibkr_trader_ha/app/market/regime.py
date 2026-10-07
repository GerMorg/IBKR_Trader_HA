from __future__ import annotations

from decimal import Decimal


class RegimeEngine:
    def detect(self, features: dict[str, Decimal]) -> str:
        vol = features.get("volatility", Decimal("99"))
        trend = abs(features.get("trend", Decimal("0")))
        momentum = abs(features.get("momentum", Decimal("0")))
        if vol >= Decimal("5"):
            return "crisis/event" if vol >= Decimal("10") else "high volatility"
        if trend > Decimal("1.5") and momentum > Decimal("0.5"):
            return "trend"
        if trend < Decimal("0.5") and momentum < Decimal("0.3"):
            return "range"
        return "low volatility"
