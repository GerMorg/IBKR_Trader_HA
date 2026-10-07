from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.models import Decision, MarketSnapshot
from app.domain.states import DecisionAction, OrderState
from .translator import OrderTranslator


class ExecutionEngine:
    def __init__(self, ibkr: Any, db: Any, risk: Any, config: Any, audit: Any) -> None:
        self.ibkr = ibkr
        self.db = db
        self.risk = risk
        self.config = config
        self.audit = audit
        self.translator = OrderTranslator()

    @staticmethod
    def _query(instrument: Any) -> dict[str, Any]:
        c = instrument.contract
        return {
            "con_id": c.con_id, "symbol": c.symbol, "local_symbol": c.local_symbol,
            "security_type": c.security_type, "exchange": c.exchange,
            "primary_exchange": c.primary_exchange, "currency": c.currency,
            "trading_class": c.trading_class, "expiry": c.expiry,
            "strike": c.strike, "right": c.right, "multiplier": c.multiplier,
        }

    def execute(
        self,
        decision: Decision,
        market: MarketSnapshot,
        margin: dict[str, Any] | None,
        orders_today: int,
    ) -> dict[str, Any]:
        if self.config.kill_switch:
            return {"state": "BLOCKED", "reason": "KILL_SWITCH"}
        if not self.config.trading_enabled:
            return {"state": "BLOCKED", "reason": "TRADING_DISABLED"}
        if self.config.trading_mode not in {"paper", "live"}:
            return {"state": "BLOCKED", "reason": "INVALID_TRADING_MODE"}
        quantity = Decimal(str(decision.quantity_notional))
        price = market.ask if decision.target_position > decision.current_position else market.bid
        if quantity <= 0 or price <= 0:
            return {"state": "BLOCKED", "reason": "INVALID_ORDER_SIZE"}
        if self.db.intent_exists(__import__("app.domain.models", fromlist=["idempotency_key"]).idempotency_key(
            decision.instrument.contract.con_id, decision.action, decision.target_position
        )):
            return {"state": "BLOCKED", "reason": "DUPLICATE_INTENT"}

        from app.trading.intent import OrderIntentBuilder
        intent = OrderIntentBuilder(self.config.execution_max_slippage_bps).build(
            decision, price, quantity / (
                price * (decision.instrument.contract.multiplier if decision.instrument.contract.multiplier > 0 else Decimal("1"))
            ),
        )
        risk_result = self.risk.evaluate(
            decision,
            self._portfolio_from_db(),
            market,
            margin,
            orders_today,
        )
        self.db.risk_event("", decision.instrument.contract.con_id, risk_result)
        if not risk_result.allowed:
            self.audit.emit("RISK_EVALUATION", "WARNING", con_id=decision.instrument.contract.con_id, reason=risk_result.reason)
            return {"state": "BLOCKED", "reason": risk_result.reason, "checks": risk_result.checks}

        if not self.db.save_intent(intent):
            return {"state": "BLOCKED", "reason": "DUPLICATE_INTENT"}

        translated = self.translator.translate(intent, decision.instrument, transmit=False)
        if self.config.require_what_if:
            try:
                margin = self.ibkr.what_if(self._query(decision.instrument), translated)
            except Exception as exc:
                self.db.update_intent_state(intent.intent_id, OrderState.REJECTED.value)
                self.audit.emit("ORDER_PRECHECK", "WARNING", reason="WHAT_IF_FAILED", error=type(exc).__name__)
                return {"state": "BLOCKED", "reason": "WHAT_IF_FAILED"}
        self.db.update_intent_state(intent.intent_id, OrderState.PRECHECK_PASSED.value)
        self.audit.emit("ORDER_PRECHECK", "INFO", con_id=decision.instrument.contract.con_id, intent_id=intent.intent_id)

        submitted = self.ibkr.place_order(
            self._query(decision.instrument),
            self.translator.translate(intent, decision.instrument, transmit=True),
        )
        self.db.update_intent_state(intent.intent_id, OrderState.ACKNOWLEDGED.value)
        self.db.save_order(submitted, intent, {"decision_id": decision.decision_id}, OrderState.ACKNOWLEDGED.value)
        self.audit.emit("ORDER_SUBMIT", "INFO", broker_order_id=submitted, intent_id=intent.intent_id)
        return {"state": OrderState.ACKNOWLEDGED.value, "broker_order_id": submitted, "intent_id": intent.intent_id}

    def _portfolio_from_db(self) -> Any:
        from app.domain.models import PortfolioState
        row = self.db.one("SELECT payload_json FROM portfolio_snapshots ORDER BY id DESC LIMIT 1")
        if not row:
            return PortfolioState()
        import json
        data = json.loads(row["payload_json"])
        p = PortfolioState()
        for key in ("account_id", "currency"):
            setattr(p, key, data.get(key, getattr(p, key)))
        for key in ("equity", "cash", "available_funds", "buying_power", "gross_exposure", "net_exposure", "margin_used", "maintenance_margin", "unrealized_pnl", "realized_pnl", "daily_pnl", "peak_equity"):
            setattr(p, key, Decimal(str(data.get(key, "0"))))
        p.positions = {int(k): Decimal(str(v)) for k, v in data.get("positions", {}).items()}
        return p
