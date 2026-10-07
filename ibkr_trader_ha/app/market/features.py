from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import MarketSnapshot


D = Decimal


class FeatureEngine:
    def calculate(self, snapshot: MarketSnapshot, history: list[dict[str, Any]]) -> dict[str, Decimal]:
        closes = [D(str(row["close"])) for row in history if D(str(row.get("close", 0))) > 0]
        if len(closes) < 5:
            closes = list(snapshot.closes)
        if len(closes) < 2:
            return {"trend": D("0"), "momentum": D("0"), "volatility": D("99"), "liquidity": D("0"), "spread_bps": snapshot.spread_bps}
        ret = closes[-1] / closes[0] - D("1")
        recent = closes[-5:]
        momentum = recent[-1] / recent[0] - D("1")
        returns = [closes[i] / closes[i - 1] - D("1") for i in range(1, len(closes))]
        mean = sum(returns, D("0")) / D(len(returns))
        var = sum((x - mean) ** 2 for x in returns) / D(len(returns))
        vol = var.sqrt() * D("100")
        return {
            "trend": ret * D("100"),
            "momentum": momentum * D("100"),
            "volatility": vol,
            "liquidity": snapshot.average_daily_notional or snapshot.volume * snapshot.last,
            "spread_bps": snapshot.spread_bps,
        }
