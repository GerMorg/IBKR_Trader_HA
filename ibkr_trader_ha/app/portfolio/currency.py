from __future__ import annotations

from decimal import Decimal


D = Decimal


class CurrencyConverter:
    def to_base(self, amount: D, currency: str, base: str, rates: dict[str, D]) -> D:
        currency = currency.upper()
        base = base.upper()
        if currency == base:
            return amount
        direct = rates.get(f"{currency}{base}")
        if direct and direct > 0:
            return amount * direct
        inverse = rates.get(f"{base}{currency}")
        if inverse and inverse > 0:
            return amount / inverse
        raise ValueError(f"FX_RATE_UNAVAILABLE:{currency}->{base}")
