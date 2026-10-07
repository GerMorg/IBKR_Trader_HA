from __future__ import annotations

from app.domain.states import OrderState


BROKER_STATUS_MAP = {
    "PENDINGSUBMIT": OrderState.SUBMITTING,
    "PRESUBMITTED": OrderState.ACKNOWLEDGED,
    "SUBMITTED": OrderState.LIVE,
    "API CANCELED": OrderState.CANCELED,
    "CANCELED": OrderState.CANCELED,
    "FILLED": OrderState.FILLED,
    "PARTIALLY FILLED": OrderState.PARTIALLY_FILLED,
    "INACTIVE": OrderState.REJECTED,
    "REJECTED": OrderState.REJECTED,
    "APICANCELLED": OrderState.CANCELED,
    "EXPIRED": OrderState.EXPIRED,
}


def map_broker_order_state(status: str, filled: str = "0", remaining: str = "0") -> OrderState:
    normalized = " ".join(str(status or "").upper().split())
    if normalized in BROKER_STATUS_MAP:
        return BROKER_STATUS_MAP[normalized]
    try:
        if float(filled) > 0 and float(remaining) > 0:
            return OrderState.PARTIALLY_FILLED
        if float(filled) > 0 and float(remaining) <= 0:
            return OrderState.FILLED
    except (TypeError, ValueError):
        pass
    return OrderState.UNKNOWN_RECONCILING
