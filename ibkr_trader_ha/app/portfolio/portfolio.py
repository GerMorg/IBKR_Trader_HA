from __future__ import annotations

from decimal import Decimal
import time
from typing import Any

from app.domain.models import Instrument, MarketSnapshot, PortfolioState
from .currency import CurrencyConverter


D = Decimal
ZERO = D("0")


class PortfolioEngine:
    def __init__(self, base_currency: str = "EUR") -> None:
        self.base_currency = base_currency.upper()
        self.converter = CurrencyConverter()

    @staticmethod
    def _d(value: Any) -> D:
        try:
            return D(str(value))
        except (TypeError, ValueError):
            return D("0")

    def build(
        self,
        account: dict[str, str],
        raw_positions: list[dict[str, Any]],
        instruments: dict[int, Instrument],
        snapshots: dict[int, MarketSnapshot],
        fx_rates: dict[str, D],
        previous_peak: D = ZERO,
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
        complete = True

        for row in raw_positions:
            con_id = int(row.get("con_id", 0) or 0)
            inst = instruments.get(con_id)
            if not inst:
                complete = False
                continue

            quantity = self._d(row.get("quantity"))
            state.position_quantities[con_id] = quantity
            state.position_currency[con_id] = inst.currency
            state.position_asset_class[con_id] = inst.asset_class
            state.position_sector[con_id] = inst.sector

            snapshot = snapshots.get(con_id)
            mark = snapshot.last if snapshot and snapshot.last > 0 else self._d(row.get("average_cost"))
            if snapshot is None or mark <= 0:
                complete = False

            multiplier = inst.contract.multiplier if inst.contract.multiplier > 0 else D("1")
            local_value = quantity * mark * multiplier
            try:
                value_base = self.converter.to_base(
                    local_value, inst.currency, self.base_currency, fx_rates
                )
            except ValueError:
                complete = False
                value_base = D("0")

            state.positions[con_id] = value_base
            gross += abs(value_base)
            net += value_base

        state.gross_exposure = gross
        state.net_exposure = net
        state.valuation_complete = complete
        state.peak_equity = max(previous_peak, state.equity)
        state.source_timestamp = time.time()
        return state
