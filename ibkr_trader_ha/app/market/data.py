from __future__ import annotations

from decimal import Decimal
import time
from typing import Any

from app.domain.models import Instrument, MarketSnapshot
from app.domain.states import AssetClass


class MarketDataEngine:
    def __init__(self, ibkr: Any, config: Any) -> None:
        self.ibkr = ibkr
        self.config = config
        self.cache: dict[int, tuple[float, MarketSnapshot]] = {}
        self.history_cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}

    def snapshot(self, instrument: Instrument) -> MarketSnapshot | None:
        cached = self.cache.get(instrument.contract.con_id)
        if cached and time.time() - cached[0] < self.config.market_data_cache_seconds:
            return cached[1]
        try:
            raw = self.ibkr.market_snapshot(
                {
                    "con_id": instrument.contract.con_id,
                    "symbol": instrument.symbol,
                    "local_symbol": instrument.contract.local_symbol,
                    "security_type": instrument.contract.security_type,
                    "exchange": instrument.contract.exchange,
                    "primary_exchange": instrument.contract.primary_exchange,
                    "currency": instrument.currency,
                    "trading_class": instrument.contract.trading_class,
                    "expiry": instrument.contract.expiry,
                    "strike": instrument.contract.strike,
                    "right": instrument.contract.right,
                },
                instrument.asset_class.value,
            )
        except Exception:
            return None
        def d(key: str, default: str = "0") -> Decimal:
            try:
                return Decimal(str(raw.get(key, default)))
            except Exception:
                return Decimal(default)
        bid, ask, last = d("1"), d("2"), d("4")
        if last <= 0:
            last = (bid + ask) / Decimal("2") if bid > 0 and ask > 0 else Decimal("0")
        if last <= 0:
            return None
        snapshot = MarketSnapshot(
            instrument.contract.con_id,
            time.time(),
            last,
            bid,
            ask,
            volume=d("8"),
            implied_volatility=d("implied_volatility") if raw.get("implied_volatility") else None,
            delta=d("delta") if raw.get("delta") else None,
            gamma=d("gamma") if raw.get("gamma") else None,
            theta=d("theta") if raw.get("theta") else None,
            vega=d("vega") if raw.get("vega") else None,
            rho=d("rho") if raw.get("rho") else None,
            shortable_shares=d("89") if raw.get("89") is not None else None,
            shortability=d("236") if raw.get("236") is not None else None,
            etf_nav=d("578") if raw.get("578") is not None else None,
        )
        self.cache[instrument.contract.con_id] = (time.time(), snapshot)
        return snapshot

    def history(self, instrument: Instrument) -> list[dict[str, Any]]:
        cached = self.history_cache.get(instrument.contract.con_id)
        if cached and time.time() - cached[0] < self.config.historical_cache_seconds:
            return cached[1]
        try:
            bars = self.ibkr.historical_data(
                {"con_id": instrument.contract.con_id, "symbol": instrument.symbol,
                 "local_symbol": instrument.contract.local_symbol, "security_type": instrument.contract.security_type,
                 "exchange": instrument.contract.exchange, "currency": instrument.currency},
                duration="30 D",
                bar_size="1 hour",
                what_to_show="TRADES",
                use_rth=instrument.asset_class != AssetClass.FX,
            )
        except Exception:
            bars = []
        self.history_cache[instrument.contract.con_id] = (time.time(), bars)
        return bars
