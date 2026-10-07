from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Any


class OrderTranslator:
    SUPPORTED = {"MKT", "LMT", "STP", "STP LMT", "TRAIL"}

    @staticmethod
    def round_price(price: Decimal, tick: Decimal) -> Decimal:
        if price <= 0:
            raise ValueError("PRICE_INVALID")
        if tick <= 0:
            return price
        return (price / tick).to_integral_value(rounding=ROUND_DOWN) * tick

    @classmethod
    def translate(cls, intent: Any, instrument: Any, transmit: bool = True) -> dict[str, Any]:
        order_type = str(intent.order_type).upper()
        if order_type not in cls.SUPPORTED:
            raise ValueError(f"UNSUPPORTED_ORDER_TYPE:{order_type}")
        price = intent.limit_price
        if price is not None:
            price = cls.round_price(price, instrument.contract.min_tick)
        return {
            "side": intent.side,
            "order_type": order_type,
            "quantity": intent.quantity,
            "limit_price": price,
            "stop_price": intent.stop_price,
            "order_ref": intent.idempotency_key,
            "transmit": transmit,
            "tif": "DAY",
        }
