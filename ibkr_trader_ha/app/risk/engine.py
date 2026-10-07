from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import Decision, MarketSnapshot, PortfolioState, RiskResult

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

        checks = {
            "positive_equity": eq > 0,
            "direction_capability": direction_allowed,
            "account_eligible": instrument.capability.account_eligible,
            "tradable_now": instrument.capability.tradable_now,
            "market_data": market.age_seconds <= self.config.max_market_data_age_seconds and market.last > 0,
            "spread": market.spread_bps <= D(str(self.config.max_spread_bps)),
            "data_quality": market.bid > 0 and market.ask > 0,
            "daily_loss": portfolio.daily_pnl >= -(eq * D(str(self.config.risk_daily_loss_pct)) / D("100")) if eq > 0 else False,
            "drawdown": portfolio.drawdown_pct <= D(str(self.config.risk_max_drawdown_pct)),
            "position_limit": abs(decision.target_position) <= eq * D(str(self.config.risk_max_position_pct)) / D("100") if eq > 0 else False,
            "order_limit": abs(desired_delta) <= eq * D(str(self.config.risk_max_order_pct)) / D("100") if eq > 0 else False,
            "gross_limit": resulting_gross <= eq * D(str(self.config.risk_max_gross_pct)) / D("100") if eq > 0 else False,
            "net_limit": abs(resulting_net) <= eq * D(str(self.config.risk_max_net_pct)) / D("100") if eq > 0 else False,
            "cash_reserve": portfolio.cash >= eq * D(str(self.config.risk_cash_reserve_pct)) / D("100") if desired_delta > 0 else True,
            "open_position_limit": decision.current_position != 0 or len(portfolio.positions) < self.config.risk_max_open_positions,
            "orders_per_day": orders_today < self.config.risk_max_orders_per_day,
            "leverage": decision.leverage <= min(self.SAFETY_MAX_LEVERAGE, D(str(self.config.risk_max_leverage))),
            "edge": decision.reduce_only or decision.signal.net_edge_bps >= D(str(self.config.strategy_min_edge_bps)),
            "confidence": decision.reduce_only or decision.signal.confidence >= D(str(self.config.strategy_min_confidence)),
        }

        if short and not decision.reduce_only:
            shortable = market.shortable_shares is not None and market.shortable_shares > 0
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
