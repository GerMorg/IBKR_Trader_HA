from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Any


D = Decimal


class PositionSizer:
    def __init__(self, risk_per_trade_pct: float, max_position_pct: float, max_order_pct: float) -> None:
        self.risk_per_trade_pct = D(str(risk_per_trade_pct))
        self.max_position_pct = D(str(max_position_pct))
        self.max_order_pct = D(str(max_order_pct))

    def size(self, instrument: Any, price: D, volatility_pct: D, equity: D) -> tuple[D, D]:
        if price <= 0 or equity <= 0:
            return D("0"), D("0")
        stop_distance = max(D("0.0075"), volatility_pct / D("100") * D("1.5"))
        risk_budget = equity * self.risk_per_trade_pct / D("100")
        risk_notional = risk_budget / stop_distance
        cap = equity * self.max_position_pct / D("100")
        order_cap = equity * self.max_order_pct / D("100")
        notional = min(risk_notional, cap, order_cap)
        unit_notional = price * max(D("0.00000001"), instrument.contract.multiplier)
        raw_qty = notional / unit_notional
        increment = instrument.contract.size_increment if instrument.contract.size_increment > 0 else D("1")
        qty = (raw_qty / increment).to_integral_value(rounding=ROUND_DOWN) * increment
        if qty < instrument.contract.min_size:
            return D("0"), D("0")
        return qty, qty * unit_notional
