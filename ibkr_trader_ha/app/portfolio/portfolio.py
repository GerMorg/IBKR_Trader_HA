from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import Instrument, MarketSnapshot, PortfolioState
from .currency import CurrencyConverter


D = Decimal


class PortfolioEngine:
    TAGS = {
        "equity": "NetLiquidation",
        "cash": "TotalCashValue",
        "buying_power": "BuyingPower",
        "available_funds": "AvailableFunds",
        "margin_used": "InitMarginReq",
        "maintenance_margin": "MaintMarginReq",
    }

    def __init__(self, base_currency: str = "EUR") -> None:
        self.base_currency = base_currency
        self.converter = CurrencyConverter()

    @staticmethod
    def _d(value: Any) -> D:
        try:
            return D(str(value))
        except Exception:
            return D("0")

    def build(
        self,
        account: dict[str, str],
        raw_positions: list[dict[str, Any]],
        instruments: dict[int, Instrument],
        snapshots: dict[int, MarketSnapshot],
        fx_rates: dict[str, D],
        previous_peak: D = D("0"),
    ) -> PortfolioState:
        state = PortfolioState(
            account_id=str(account.get("AccountId") or account.get("AccountType") or ""),
            currency=self.base_currency,
            equity=self._d(account.get("NetLiquidation")),
            cash=self._d(account.get("TotalCashValue")),
            available_funds=self._d(account.get("AvailableFunds")),
            buying_power=self._d(account.get("BuyingPower")),
            margin_used=self._d(account.get("InitMarginReq")),
            maintenance_margin=self._d(account.get("MaintMarginReq")),
        )
        gross = D("0")
        net = D("0")
        for row in raw_positions:
            con_id = int(row.get("con_id", 0) or 0)
            inst = instruments.get(con_id)
            if not inst:
                continue
            qty = self._d(row.get("quantity"))
            state.positions[con_id] = qty
            state.position_currency[con_id] = inst.currency
            state.position_asset_class[con_id] = inst.asset_class
            state.position_sector[con_id] = inst.sector

            snap = snapshots.get(con_id)
            mark = snap.last if snap and snap.last > 0 else self._d(row.get("average_cost"))
            multiplier = inst.contract.multiplier if inst.contract.multiplier > 0 else D("1")
            local_value = qty * mark * multiplier
            try:
                value_eur = self.converter.to_base(local_value, inst.currency, self.base_currency, fx_rates)
            except ValueError:
                value_eur = local_value if inst.currency.upper() == self.base_currency.upper() else D("0")
            gross += abs(value_eur)
            net += value_eur
        state.gross_exposure = gross
        state.net_exposure = net
        state.peak_equity = max(previous_peak, state.equity)
        state.source_timestamp = __import__("time").time()
        return state
