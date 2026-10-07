from __future__ import annotations

from decimal import Decimal
import json
import time
from typing import Any

from app.domain.models import Decision, MarketSnapshot, idempotency_key
from app.domain.states import OrderState
from app.execution.lifecycle import map_broker_order_state
from app.trading.intent import OrderIntentBuilder
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
            "con_id": c.con_id,
            "symbol": c.symbol,
            "local_symbol": c.local_symbol,
            "security_type": c.security_type,
            "exchange": c.exchange,
            "primary_exchange": c.primary_exchange,
            "currency": c.currency,
            "trading_class": c.trading_class,
            "expiry": c.expiry,
            "strike": c.strike,
            "right": c.right,
            "multiplier": c.multiplier,
        }

    def execute(
        self,
        decision: Decision,
        market: MarketSnapshot,
        margin: dict[str, Any] | None,
        orders_today: int,
        cycle_id: str = "",
    ) -> dict[str, Any]:
        if self.config.kill_switch:
            return {"state": "BLOCKED", "reason": "KILL_SWITCH"}
        if not self.config.trading_enabled:
            return {"state": "BLOCKED", "reason": "TRADING_DISABLED"}
        if self.config.trading_mode not in {"paper", "live"}:
            return {"state": "BLOCKED", "reason": "INVALID_TRADING_MODE"}
        if self.config.trading_mode == "live" and not getattr(self.config, "ibkr_account", ""):
            return {"state": "BLOCKED", "reason": "IBKR_ACCOUNT_REQUIRED"}

        notional = Decimal(str(decision.quantity_notional))
        if notional <= 0:
            return {"state": "BLOCKED", "reason": "INVALID_ORDER_SIZE"}

        is_buy = decision.target_position > decision.current_position
        reference_price = market.ask if is_buy else market.bid
        if reference_price <= 0:
            return {"state": "BLOCKED", "reason": "INVALID_MARKET_PRICE"}

        key = idempotency_key(
            decision.instrument.contract.con_id, decision.action, decision.target_position
        )
        if self.db.intent_exists(key):
            return {"state": "BLOCKED", "reason": "DUPLICATE_INTENT"}

        multiplier = (
            decision.instrument.contract.multiplier
            if decision.instrument.contract.multiplier > 0
            else Decimal("1")
        )
        quantity = notional / (reference_price * multiplier)
        intent = OrderIntentBuilder(self.config.execution_max_slippage_bps).build(
            decision, reference_price, quantity
        )
        portfolio = self._portfolio_from_db()

        initial_risk = self.risk.evaluate(
            decision, portfolio, market, margin, orders_today
        )
        self.db.risk_event(cycle_id, decision.instrument.contract.con_id, initial_risk)
        if not initial_risk.allowed:
            self.audit.emit(
                "ORDER_BLOCKED_RISK",
                "WARNING",
                con_id=decision.instrument.contract.con_id,
                reason=initial_risk.reason,
            )
            return {
                "state": "BLOCKED",
                "reason": initial_risk.reason,
                "checks": initial_risk.checks,
            }

        if not self.db.save_intent(intent):
            return {"state": "BLOCKED", "reason": "DUPLICATE_INTENT"}

        translated = self.translator.translate(intent, decision.instrument, transmit=False)
        margin_result = margin
        if self.config.require_what_if:
            try:
                margin_result = self.ibkr.what_if(
                    self._query(decision.instrument), translated
                )
                status = str(margin_result.get("status", "")).upper()
                if status in {"REJECTED", "INACTIVE"}:
                    raise RuntimeError(f"WHAT_IF_{status}")
            except Exception as exc:
                self.db.update_intent_state(intent.intent_id, OrderState.REJECTED.value)
                self.audit.emit(
                    "ORDER_PRECHECK_FAILED",
                    "WARNING",
                    reason="WHAT_IF_FAILED",
                    error=type(exc).__name__,
                )
                return {"state": "BLOCKED", "reason": "WHAT_IF_FAILED"}

            final_risk = self.risk.evaluate(
                decision, portfolio, market, margin_result, orders_today
            )
            self.db.risk_event(
                cycle_id, decision.instrument.contract.con_id, final_risk
            )
            if not final_risk.allowed:
                    self.db.update_intent_state(intent.intent_id, OrderState.REJECTED.value)
                    return {
                        "state": "BLOCKED",
                        "reason": final_risk.reason,
                        "checks": final_risk.checks,
                    }

        self.db.update_intent_state(intent.intent_id, OrderState.PRECHECK_PASSED.value)
        self.audit.emit(
            "ORDER_PRECHECK_PASSED",
            "INFO",
            con_id=decision.instrument.contract.con_id,
            intent_id=intent.intent_id,
            what_if=bool(self.config.require_what_if),
        )

        try:
            broker_order_id = self.ibkr.place_order(
                self._query(decision.instrument),
                self.translator.translate(intent, decision.instrument, transmit=True),
            )
        except Exception as exc:
            self.db.update_intent_state(intent.intent_id, OrderState.REJECTED.value)
            self.audit.emit(
                "ORDER_SUBMIT_FAILED",
                "ERROR",
                con_id=decision.instrument.contract.con_id,
                error=type(exc).__name__,
            )
            return {"state": "BLOCKED", "reason": "ORDER_SUBMIT_FAILED"}

        self.db.update_intent_state(intent.intent_id, OrderState.SUBMITTING.value)
        self.db.save_order(
            broker_order_id, intent, {"decision_id": decision.decision_id}, OrderState.SUBMITTING.value
        )
        self.audit.emit(
            "ORDER_SUBMITTED",
            "INFO",
            broker_order_id=broker_order_id,
            intent_id=intent.intent_id,
        )

        observed = self.ibkr.order_status(broker_order_id)
        state = map_broker_order_state(
            observed.get("status", ""), observed.get("filled", "0"), observed.get("remaining", "0")
        )
        if state != OrderState.UNKNOWN_RECONCILING:
            self.db.update_intent_state(intent.intent_id, state.value)
            self.db.save_order(
                broker_order_id, intent, observed, state.value
            )
        else:
            state = OrderState.SUBMITTING

        return {
            "state": state.value,
            "broker_order_id": broker_order_id,
            "intent_id": intent.intent_id,
            "order_status": observed,
        }

    def reconcile(self) -> dict[str, int]:
        rows = self.db.query(
            "SELECT broker_order_id,intent_id,state FROM orders "
            "WHERE state IN ('SUBMITTING','ACKNOWLEDGED','LIVE','PARTIALLY_FILLED','UNKNOWN_RECONCILING')"
        )
        counts: dict[str, int] = {}
        for row in rows:
            broker_id = int(row["broker_order_id"])
            observed = self.ibkr.order_status(broker_id)
            state = map_broker_order_state(
                observed.get("status", ""), observed.get("filled", "0"), observed.get("remaining", "0")
            )
            if state == OrderState.UNKNOWN_RECONCILING:
                counts[state.value] = counts.get(state.value, 0) + 1
                continue
            self.db.update_intent_state(str(row["intent_id"]), state.value)
            self.db.execute(
                "UPDATE orders SET state=?,payload_json=?,updated_at=? WHERE broker_order_id=?",
                (state.value, json.dumps(observed, default=str, sort_keys=True), time.time(), broker_id),
            )
            counts[state.value] = counts.get(state.value, 0) + 1
        return counts

    def _portfolio_from_db(self) -> Any:
        from app.domain.models import PortfolioState

        row = self.db.one(
            "SELECT payload_json FROM portfolio_snapshots ORDER BY id DESC LIMIT 1"
        )
        if not row:
            return PortfolioState()
        data = json.loads(row["payload_json"])
        portfolio = PortfolioState()
        for key in ("account_id", "currency"):
            setattr(portfolio, key, data.get(key, getattr(portfolio, key)))
        decimal_fields = (
            "equity", "cash", "available_funds", "buying_power", "gross_exposure",
            "net_exposure", "margin_used", "maintenance_margin", "unrealized_pnl",
            "realized_pnl", "daily_pnl", "peak_equity",
        )
        for key in decimal_fields:
            setattr(portfolio, key, Decimal(str(data.get(key, "0"))))
        portfolio.positions = {
            int(key): Decimal(str(value)) for key, value in data.get("positions", {}).items()
        }
        portfolio.position_quantities = {
            int(key): Decimal(str(value))
            for key, value in data.get("position_quantities", {}).items()
        }
        portfolio.valuation_complete = bool(data.get("valuation_complete", False))
        return portfolio
