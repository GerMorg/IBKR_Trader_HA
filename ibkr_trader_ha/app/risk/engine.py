from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import Decision, MarketSnapshot, PortfolioState, RiskResult
from app.domain.states import DecisionAction
from app.market.hours import is_liquid_now

D = Decimal


class RiskEngine:
    SAFETY_MAX_LEVERAGE = D("5")

    def __init__(self, config: Any) -> None:
        self.config = config

    def evaluate(
        self,
        decision: Decision,
        portfolio: PortfolioState,
        market: MarketSnapshot,
        margin: dict[str, Any] | None,
        orders_today: int,
    ) -> RiskResult:
        instrument = decision.instrument
        long = decision.action.value == "LONG"
        short = decision.action.value == "SHORT"
        direction_allowed = (
            instrument.capability.can_long if long else
            instrument.capability.can_short if short else
            decision.reduce_only
        )
        desired_delta = decision.target_position - decision.current_position
        resulting_gross = portfolio.gross_exposure - abs(decision.current_position) + abs(decision.target_position)
        resulting_net = portfolio.net_exposure - decision.current_position + decision.target_position
        eq = portfolio.equity
        is_reduce = decision.reduce_only or decision.action in {DecisionAction.EXIT, DecisionAction.REBALANCE}

        sector_exposure = sum(
            abs(value) for con_id, value in portfolio.positions.items()
            if portfolio.position_sector.get(con_id, "") and portfolio.position_sector.get(con_id, "") == instrument.sector
        )
        if instrument.sector:
            sector_exposure += abs(decision.target_position)
        sector_limit = eq * D(str(self.config.risk_max_sector_exposure_pct)) / D("100") if eq > 0 else D("0")

        currency_exposure = sum(
            abs(value) for con_id, value in portfolio.positions.items()
            if portfolio.position_currency.get(con_id, "") == instrument.currency
        )
        if instrument.currency:
            currency_exposure -= abs(decision.current_position)
            currency_exposure += abs(decision.target_position)
        currency_limit = eq * D(str(self.config.risk_max_currency_exposure_pct)) / D("100") if eq > 0 else D("0")

        correlation_proxy = sector_exposure
        correlation_limit = eq * D(str(self.config.risk_max_correlation_exposure_pct)) / D("100") if eq > 0 else D("0")

        checks = {
            "positive_equity": eq > 0,
            "direction_capability": direction_allowed,
            "account_eligible": instrument.capability.account_eligible,
            "tradable_now": instrument.capability.tradable_now,
            "market_hours": is_liquid_now(instrument.contract.liquid_hours, instrument.contract.time_zone_id) if instrument.contract.liquid_hours else True,
            "market_data": market.age_seconds <= self.config.max_market_data_age_seconds and market.last > 0,
            "spread": market.spread_bps <= D(str(self.config.max_spread_bps)),
            "data_quality": market.bid > 0 and market.ask > 0,
            "daily_loss": portfolio.daily_pnl >= -(eq * D(str(self.config.risk_daily_loss_pct)) / D("100")) if eq > 0 else False,
            "drawdown": portfolio.drawdown_pct <= D(str(self.config.risk_max_drawdown_pct)),
            "position_limit": abs(decision.target_position) <= eq * D(str(self.config.risk_max_position_pct)) / D("100") if eq > 0 else False,
            "order_limit": abs(desired_delta) <= eq * D(str(self.config.risk_max_order_pct)) / D("100") if eq > 0 else False,
            "gross_limit": resulting_gross <= eq * D(str(self.config.risk_max_gross_pct)) / D("100") if eq > 0 else False,
            "net_limit": abs(resulting_net) <= eq * D(str(self.config.risk_max_net_pct)) / D("100") if eq > 0 else False,
            "portfolio_valuation": portfolio.valuation_complete or is_reduce,
            "cash_reserve": portfolio.available_funds >= eq * D(str(self.config.risk_cash_reserve_pct)) / D("100") if desired_delta > 0 and not is_reduce else True,
            "open_position_limit": decision.current_position != 0 or len(portfolio.positions) < self.config.risk_max_open_positions,
            "sector_concentration": sector_exposure <= sector_limit if instrument.sector and eq > 0 else True,
            "currency_concentration": currency_exposure <= currency_limit if instrument.currency and eq > 0 else True,
            "correlation_proxy": correlation_proxy <= correlation_limit if instrument.sector and eq > 0 else True,
            "orders_per_day": orders_today < self.config.risk_max_orders_per_day,
            "leverage": decision.leverage <= min(self.SAFETY_MAX_LEVERAGE, D(str(self.config.risk_max_leverage))),
            "edge": is_reduce or decision.signal.net_edge_bps >= D(str(self.config.strategy_min_edge_bps)),
            "confidence": is_reduce or decision.signal.confidence >= D(str(self.config.strategy_min_confidence)),
        }

        if short and not decision.reduce_only:
            shortable = (
                market.shortable_shares is not None and market.shortable_shares > 0
            ) or (
                market.shortability is not None and market.shortability > D("2.5")
            )
            checks["shortable"] = shortable

        if decision.leverage > 1:
            checks["margin_data"] = margin is not None
            if margin is not None:
                try:
                    init = D(str(margin.get("init_margin_change") or "0"))
                    available = portfolio.available_funds
                    checks["margin_sufficient"] = init >= 0 and available >= init
                except Exception:
                    checks["margin_sufficient"] = False

        failed = next((key for key, value in checks.items() if not value), None)
        return RiskResult(
            allowed=failed is None,
            reason=failed or "RISK_OK",
            checks=checks,
            effective_leverage=decision.leverage,
            margin_required=D(str((margin or {}).get("init_margin_change") or "0")),
        )
