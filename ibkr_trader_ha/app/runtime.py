from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
import time
from typing import Any

from app.config import Config
from app.discovery import DiscoveryEngine
from app.domain.models import PortfolioState, digest_config
from app.domain.states import DecisionAction, OrderState, RuntimeStage
from app.execution import ExecutionEngine
from app.gemini import GeminiAnalyzer
from app.ibkr import IBKRClient
from app.learning import LearningEngine
from app.market import FeatureEngine, MarketDataEngine, RegimeEngine
from app.monitoring import AuditLogger
from app.news import NewsEngine
from app.persistence import Database
from app.portfolio import PortfolioEngine
from app.recovery import RecoveryManager
from app.risk import LeverageEngine, PositionSizer, RiskEngine
from app.sensors import SensorPublisher
from app.strategy import StrategyDispatcher
from app.tax import AustrianTaxLedger
from app.trading import DecisionEngine


class Runtime:
    def __init__(
        self,
        config: Config,
        db: Database,
        audit: AuditLogger,
        ibkr: IBKRClient,
        discovery: DiscoveryEngine,
        market: MarketDataEngine,
        portfolio: PortfolioEngine,
        strategies: StrategyDispatcher,
        decisions: DecisionEngine,
        risk: RiskEngine,
        sizing: PositionSizer,
        leverage: LeverageEngine,
        execution: ExecutionEngine,
        news: NewsEngine,
        gemini: GeminiAnalyzer,
        learning: LearningEngine,
        sensors: SensorPublisher,
        recovery: RecoveryManager,
        tax: AustrianTaxLedger,
    ) -> None:
        self.config = config
        self.db = db
        self.audit = audit
        self.ibkr = ibkr
        self.discovery = discovery
        self.market = market
        self.portfolio_engine = portfolio
        self.strategies = strategies
        self.decisions = decisions
        self.risk = risk
        self.sizing = sizing
        self.leverage = leverage
        self.execution = execution
        self.news = news
        self.gemini = gemini
        self.learning = learning
        self.sensors = sensors
        self.recovery = recovery
        self.tax = tax
        self.features = FeatureEngine()
        self.regimes = RegimeEngine()
        self.stage = RuntimeStage.BOOT
        self.cycle_id = ""
        self.instruments: dict[int, Any] = {}
        self.portfolio: PortfolioState = PortfolioState(currency=self.config.base_currency)
        self.stats: dict[str, Any] = {}
        self._fx_cache: dict[str, tuple[float, Decimal]] = {}

    def startup(self) -> bool:
        self.stage = RuntimeStage.CONFIG_LOADED
        self.audit.emit(
            "STARTUP_CONFIG_LOADED",
            config_hash=digest_config(self.config.__dict__),
        )
        try:
            persisted = self.db.recovery_state()
            if persisted and persisted.get("state") == "RECOVERY_REQUIRED":
                self.recovery.require(
                    str(persisted.get("detail") or "PERSISTED_RECOVERY")
                )

            self.ibkr.connect()
            self.stage = RuntimeStage.IBKR_CONNECTED
            self.audit.emit(
                "IBKR_CONNECTED",
                host=self.config.ibkr_host,
                port=self.config.ibkr_port,
            )

            account = self.ibkr.account_summary()
            raw_positions = self.ibkr.positions()
            open_orders = self.ibkr.open_orders()
            self.audit.emit(
                "PORTFOLIO_RECONCILIATION",
                "INFO",
                raw_positions=len(raw_positions),
                open_orders=len(open_orders),
            )

            discovered, discovery_stats = self.discovery.discover()
            self.instruments = {
                item.contract.con_id: item for item in discovered
            }

            for row in raw_positions:
                con_id = int(row.get("con_id", 0) or 0)
                if con_id and con_id not in self.instruments:
                    try:
                        details = self.ibkr.contract_details({"con_id": con_id})
                        if details:
                            self.instruments[con_id] = self.discovery.map_contract(
                                details[0]
                            )
                    except Exception as exc:
                        self.audit.emit(
                            "CONTRACT_DISCOVERY_FAILED",
                            "WARNING",
                            con_id=con_id,
                            error=type(exc).__name__,
                        )

            self.db.save_instruments(list(self.instruments.values()))
            snapshots: dict[int, Any] = {}
            held_ids = {
                int(row.get("con_id", 0) or 0) for row in raw_positions
            }
            for con_id in held_ids:
                instrument = self.instruments.get(con_id)
                if instrument is None:
                    continue
                snapshot = self.market.snapshot(instrument)
                if snapshot:
                    snapshots[con_id] = snapshot
                    self.db.save_market(snapshot)

            self.portfolio = self.portfolio_engine.build(
                account,
                raw_positions,
                self.instruments,
                snapshots,
                self._fx_rates([self.instruments[c] for c in held_ids if c in self.instruments]),
            )
            self.db.save_portfolio(self.portfolio)

            reconcile = self.execution.reconcile()
            self.audit.emit("ORDER_STATUS", "INFO", **reconcile)
            self._reconcile_open_orders(open_orders)

            self.stage = RuntimeStage.ACCOUNT_RECONCILED
            if reconcile.get(OrderState.UNKNOWN_RECONCILING.value, 0) > 0:
                self.recovery.require("ORDER_STATE_UNKNOWN")
            if self.recovery.required:
                self.stage = RuntimeStage.RECOVERY_REQUIRED
                self._publish()
                return False

            self.recovery.clear()
            self.stage = RuntimeStage.READY
            self._publish()
            self.audit.emit(
                "STARTUP_READY",
                instruments=len(self.instruments),
                discovered=discovery_stats["discovered"],
                eligible=discovery_stats["eligible"],
                unsupported=discovery_stats["unsupported"],
            )
            return True
        except Exception as exc:
            self.stage = RuntimeStage.SAFE_MODE
            self.recovery.require(
                f"STARTUP:{type(exc).__name__}:{str(exc)[:300]}"
            )
            self._publish()
            return False

    def run_cycle(self) -> dict[str, Any]:
        if self.stage != RuntimeStage.READY and not self.startup():
            return {"status": self.stage.value, "cycle_id": self.cycle_id}

        self.cycle_id = f"cycle_{time.time_ns()}"
        self.stage = RuntimeStage.RUNNING
        blockers: list[str] = []
        self.stats = {
            "discovered": 0,
            "data_ready": 0,
            "candidates": 0,
            "analyzed": 0,
            "decision_ready": 0,
            "approved": 0,
            "blocked": 0,
            "submitted": 0,
            "filled": 0,
        }
        config_hash = digest_config(self.config.__dict__)
        self.db.start_cycle(self.cycle_id, config_hash)
        self.audit.emit("CYCLE_START", cycle_id=self.cycle_id, config_hash=config_hash)

        try:
            account = self.ibkr.account_summary()
            raw_positions = self.ibkr.positions()
            open_orders = self.ibkr.open_orders()
            self._reconcile_open_orders(open_orders)

            discovered, discovery_stats = self.discovery.discover()
            for item in discovered:
                self.instruments[item.contract.con_id] = item
            self.db.save_instruments(list(self.instruments.values()))

            held_ids = {int(row.get("con_id", 0) or 0) for row in raw_positions}
            ranked_base = list(discovered[:max(
                self.config.max_deep_analysis_candidates * 2, 50
            )])
            present = {item.contract.con_id for item in ranked_base}
            for con_id in held_ids:
                instrument = self.instruments.get(con_id)
                if instrument and con_id not in present:
                    ranked_base.append(instrument)
                    present.add(con_id)

            snapshots: dict[int, Any] = {}
            for instrument in ranked_base:
                snapshot = self.market.snapshot(instrument)
                if snapshot:
                    snapshots[instrument.contract.con_id] = snapshot
                    self.db.save_market(snapshot)

            option_inputs = [
                (instrument, snapshots[instrument.contract.con_id].last)
                for instrument in ranked_base
                if instrument.contract.con_id in snapshots
                and instrument.asset_class.value in {"EQUITY", "ETF", "FUTURES"}
            ][: self.config.max_option_underlyings]
            options = self.discovery.discover_options(option_inputs)
            for option in options:
                self.instruments[option.contract.con_id] = option
            if options:
                self.db.save_instruments(options)
                for option in options:
                    snapshot = self.market.snapshot(option)
                    if snapshot:
                        snapshots[option.contract.con_id] = snapshot
                        self.db.save_market(snapshot)

            self.stats["discovered"] = discovery_stats["discovered"] + len(options)
            self.stats["data_ready"] = len(snapshots)

            option_slots = min(
                len(options),
                max(0, min(6, self.config.max_deep_analysis_candidates // 4)),
            )
            base_slots = max(
                0, self.config.max_deep_analysis_candidates - option_slots
            )
            analysis_candidates: list[Any] = []
            seen: set[int] = set()
            for instrument in ranked_base[:base_slots]:
                if instrument.contract.con_id not in seen:
                    analysis_candidates.append(instrument)
                    seen.add(instrument.contract.con_id)
            for instrument in options[:option_slots]:
                if instrument.contract.con_id not in seen:
                    analysis_candidates.append(instrument)
                    seen.add(instrument.contract.con_id)

            self.stats["candidates"] = len(analysis_candidates)
            self.audit.emit(
                "DISCOVERY_RESULT",
                "INFO",
                discovered=self.stats["discovered"],
                data_ready=self.stats["data_ready"],
                candidates=self.stats["candidates"],
                discovery_errors=self.discovery.last_errors[-10:],
            )
            self.audit.emit(
                "MARKET_DATA_RESULT",
                "INFO",
                data_ready=self.stats["data_ready"],
                candidates=self.stats["candidates"],
            )

            histories: dict[int, list[dict[str, Any]]] = {}
            for instrument in analysis_candidates:
                histories[instrument.contract.con_id] = self.market.history(instrument)

            self.portfolio = self.portfolio_engine.build(
                account,
                raw_positions,
                self.instruments,
                snapshots,
                self._fx_rates([self.instruments[c] for c in held_ids if c in self.instruments]),
                getattr(self.portfolio, "peak_equity", Decimal("0")),
            )
            self.db.save_portfolio(self.portfolio)

            news_items = self.news.collect() if self.config.news_enabled else []
            self.audit.emit(
                "NEWS_RESULT",
                "INFO",
                status=self.news.status if self.config.news_enabled else "DISABLED",
                items=len(news_items),
            )

            decisions: list[Any] = []
            model_scale = self.learning.confidence_scale()
            for instrument in analysis_candidates:
                snapshot = snapshots.get(instrument.contract.con_id)
                if snapshot is None:
                    self.stats["blocked"] += 1
                    blockers.append(f"{instrument.symbol}:MARKET_DATA_UNAVAILABLE")
                    continue

                feature_values = self.features.calculate(
                    snapshot,
                    histories.get(instrument.contract.con_id, []),
                )
                regime = self.regimes.detect(feature_values)
                news_impact = (
                    self.news.effect_for(instrument, news_items)
                    if news_items else Decimal("0")
                )
                ai = {
                    "effect_bps": Decimal("0"),
                    "status": "DISABLED",
                }
                if (
                    self.config.gemini_enabled
                    and self.stats["decision_ready"] < self.config.max_gemini_candidates
                ):
                    ai = self.gemini.analyze(
                        instrument, feature_values, news_impact, regime
                    )
                pair = self.strategies.evaluate(
                    instrument,
                    snapshot,
                    feature_values,
                    regime,
                    news_impact,
                    Decimal(str(ai.get("effect_bps", 0))),
                )
                self.stats["analyzed"] += 1
                if not pair:
                    self.stats["blocked"] += 1
                    blockers.append(f"{instrument.symbol}:ANALYSIS_ONLY")
                    continue

                decision = self.decisions.select(
                    instrument,
                    pair[0],
                    pair[1],
                    self.portfolio,
                    model_scale,
                )
                if decision is None:
                    continue

                decision = self._size_decision(
                    decision, snapshot, feature_values
                )
                if decision.quantity_notional <= 0:
                    blockers.append(
                        f"{instrument.symbol}:NO_REBALANCE_NEEDED"
                    )
                    continue

                self.db.save_decision(self.cycle_id, decision)
                self.learning.record_decision(decision, self.cycle_id)
                self.stats["decision_ready"] += 1
                self.audit.emit(
                    "DECISION_RESULT",
                    "INFO",
                    con_id=instrument.contract.con_id,
                    action=decision.action.value,
                    current=str(decision.current_position),
                    target=str(decision.target_position),
                    delta=str(decision.quantity_notional),
                    confidence=str(decision.signal.confidence),
                    edge=str(decision.signal.net_edge_bps),
                    model_scale=str(model_scale),
                )

                risk_result = self.risk.evaluate(
                    decision,
                    self.portfolio,
                    snapshot,
                    None,
                    self._orders_today(),
                )
                self.db.risk_event(
                    self.cycle_id,
                    instrument.contract.con_id,
                    risk_result,
                )
                self.audit.emit(
                    "RISK_EVALUATION",
                    "INFO" if risk_result.allowed else "WARNING",
                    con_id=instrument.contract.con_id,
                    reason=risk_result.reason,
                    checks=risk_result.checks,
                )
                if not risk_result.allowed:
                    self.stats["blocked"] += 1
                    blockers.append(
                        f"{instrument.symbol}:{risk_result.reason}"
                    )
                    continue

                self.stats["approved"] += 1
                decisions.append((decision, snapshot))

            for decision, snapshot in decisions:
                result = self.execution.execute(
                    decision,
                    snapshot,
                    None,
                    self._orders_today(),
                    cycle_id=self.cycle_id,
                )
                self.learning.record_order(decision.decision_id, result)
                state = str(result.get("state", ""))
                if state in {
                    OrderState.SUBMITTING.value,
                    OrderState.ACKNOWLEDGED.value,
                    OrderState.LIVE.value,
                    OrderState.PARTIALLY_FILLED.value,
                    OrderState.FILLED.value,
                }:
                    self.stats["submitted"] += 1
                if state == OrderState.FILLED.value:
                    self.stats["filled"] += 1
                elif state == "BLOCKED":
                    self.stats["blocked"] += 1
                    blockers.append(
                        f"{decision.instrument.symbol}:"
                        f"{result.get('reason', 'ORDER_BLOCKED')}"
                    )

            lifecycle = self.execution.reconcile()
            self.audit.emit("ORDER_STATUS", "INFO", **lifecycle)
            if lifecycle.get(OrderState.UNKNOWN_RECONCILING.value, 0) > 0:
                self.recovery.require("ORDER_STATE_UNKNOWN")

            self._reconcile_after_cycle()
            self.learning.mark_to_market(
                {
                    con_id: snapshot.last
                    for con_id, snapshot in snapshots.items()
                }
            )
            learning = self.learning.recalibrate()
            self.audit.emit(
                "LEARNING_RECALIBRATION",
                "INFO",
                **learning,
            )

            if self.recovery.required:
                self.db.finish_cycle(
                    self.cycle_id,
                    "RECOVERY_REQUIRED",
                    ";".join(blockers[:5]),
                )
                self.stage = RuntimeStage.RECOVERY_REQUIRED
                self._publish(learning=learning)
                return {
                    "status": self.stage.value,
                    "cycle_id": self.cycle_id,
                    **self.stats,
                    "blockers": blockers,
                }

            self.db.finish_cycle(
                self.cycle_id,
                "COMPLETED",
                ";".join(blockers[:5]),
            )
            self.stage = RuntimeStage.READY
            self._publish(learning=learning)
            self.audit.emit(
                "CYCLE_COMPLETE",
                cycle_id=self.cycle_id,
                **self.stats,
                blockers=blockers[:10],
            )
            return {
                "status": "COMPLETED",
                "cycle_id": self.cycle_id,
                **self.stats,
                "blockers": blockers,
            }
        except Exception as exc:
            self.db.finish_cycle(
                self.cycle_id,
                "FAILED",
                type(exc).__name__,
            )
            self.recovery.require(
                f"CYCLE:{type(exc).__name__}:{str(exc)[:300]}"
            )
            self.stage = RuntimeStage.RECOVERY_REQUIRED
            self._publish()
            self.audit.emit(
                "CYCLE_FAILED",
                "ERROR",
                cycle_id=self.cycle_id,
                error=type(exc).__name__,
            )
            return {
                "status": "FAILED",
                "cycle_id": self.cycle_id,
                "error": type(exc).__name__,
            }

    def _size_decision(
        self,
        decision: Any,
        snapshot: Any,
        features: dict[str, Decimal],
    ) -> Any:
        if decision.action in {DecisionAction.EXIT, DecisionAction.REBALANCE}:
            return self.decisions.with_position(
                decision,
                Decimal("0"),
                abs(decision.current_position),
                Decimal("1"),
                True,
            )

        price = (
            snapshot.ask
            if decision.action == DecisionAction.LONG
            else snapshot.bid
        )
        quantity, target_notional = self.sizing.size(
            decision.instrument,
            price,
            features.get("volatility", Decimal("5")),
            self.portfolio.equity,
        )
        if quantity <= 0 or target_notional <= 0:
            return self.decisions.with_position(
                decision,
                decision.current_position,
                Decimal("0"),
                Decimal("1"),
                True,
            )

        leverage = self.leverage.choose(
            decision.instrument,
            decision.signal.confidence,
            features.get("volatility", Decimal("5")),
            Decimal(str(self.config.risk_max_leverage)),
        )
        desired_target = (
            target_notional
            if decision.action == DecisionAction.LONG
            else -target_notional
        )
        desired_delta = abs(desired_target - decision.current_position)
        multiplier = (
            decision.instrument.contract.multiplier
            if decision.instrument.contract.multiplier > 0
            else Decimal("1")
        )
        increment = (
            decision.instrument.contract.size_increment
            if decision.instrument.contract.size_increment > 0
            else Decimal("1")
        )
        delta_quantity = (
            desired_delta / (price * multiplier)
            if price > 0
            else Decimal("0")
        )
        delta_quantity = (
            delta_quantity / increment
        ).to_integral_value(rounding=ROUND_DOWN) * increment
        if delta_quantity < decision.instrument.contract.min_size:
            return self.decisions.with_position(
                decision,
                decision.current_position,
                Decimal("0"),
                leverage,
                True,
            )

        actual_delta = delta_quantity * price * multiplier
        if decision.action == DecisionAction.LONG:
            target = decision.current_position + actual_delta
        else:
            target = decision.current_position - actual_delta

        same_long_reduce = (
            decision.current_position > 0
            and 0 <= target < decision.current_position
        )
        same_short_reduce = (
            decision.current_position < 0
            and 0 >= target > decision.current_position
        )
        reduce_only = same_long_reduce or same_short_reduce
        if target == 0 and decision.current_position != 0:
            reduce_only = True

        return self.decisions.with_position(
            decision,
            target,
            actual_delta,
            leverage,
            reduce_only,
        )

    def _orders_today(self) -> int:
        now = time.time()
        start = now - (now % 86400)
        row = self.db.one(
            "SELECT COUNT(*) AS n FROM orders WHERE submitted_at>=?",
            (start,),
        )
        return int(row["n"]) if row else 0

    def _reconcile_open_orders(
        self,
        open_orders: list[dict[str, Any]],
    ) -> None:
        broker_ids = {
            int(row.get("order_id", 0)) for row in open_orders
        }
        local = self.db.query(
            "SELECT broker_order_id,state FROM orders "
            "WHERE state IN "
            "('SUBMITTING','ACKNOWLEDGED','LIVE','PARTIALLY_FILLED',"
            "'UNKNOWN_RECONCILING')"
        )
        for row in local:
            order_id = int(row["broker_order_id"])
            if order_id not in broker_ids and not self.ibkr.order_status(order_id):
                self.recovery.require(
                    f"ORDER_STATE_UNKNOWN:{order_id}"
                )

    def _reconcile_after_cycle(self) -> None:
        import json as _json

        executions = self.ibkr.executions()
        new_count = 0
        for execution in executions:
            execution_id = str(execution.get("execution_id") or "")
            if not execution_id:
                continue
            if self.db.one(
                "SELECT execution_id FROM executions WHERE execution_id=?",
                (execution_id,),
            ):
                continue

            self.db.save_execution_raw(execution)
            self.tax.record_fill(execution)
            order_id = int(execution.get("order_id", 0) or 0)
            order_row = self.db.one(
                "SELECT payload_json FROM orders WHERE broker_order_id=?",
                (order_id,),
            )
            if order_row:
                payload = _json.loads(order_row["payload_json"])
                decision_id = str(payload.get("decision_id") or "")
                if decision_id:
                    self.learning.record_fill(decision_id, execution)
            new_count += 1
            self.audit.emit(
                "EXECUTION",
                "INFO",
                execution_id=execution_id,
                broker_order_id=order_id,
            )
        positions = self.ibkr.positions()
        self.audit.emit(
            "PORTFOLIO_RECONCILIATION",
            "INFO",
            positions=len(positions),
            new_executions=new_count,
        )

    def _fx_rates(self, instruments: list[Any]) -> dict[str, Decimal]:
        rates: dict[str, Decimal] = {}
        now = time.time()
        currencies = {
            str(instrument.currency).upper()
            for instrument in instruments
            if instrument.currency
        }
        for currency in currencies:
            base = self.config.base_currency.upper()
            if currency == base:
                continue
            cached = self._fx_cache.get(currency)
            if cached and now - cached[0] < self.config.market_data_cache_seconds:
                rates[f"{base}{currency}"] = cached[1]
                continue
            try:
                raw = self.ibkr.market_snapshot(
                    {
                        "symbol": base,
                        "security_type": "CASH",
                        "exchange": "IDEALPRO",
                        "currency": currency,
                    },
                    "FX",
                )
                bid = Decimal(str(raw.get("1", "0")))
                ask = Decimal(str(raw.get("2", "0")))
                last = Decimal(str(raw.get("4", "0")))
                if last <= 0 and bid > 0 and ask > 0:
                    last = (bid + ask) / Decimal("2")
                if last > 0:
                    self._fx_cache[currency] = (now, last)
                    rates[f"{base}{currency}"] = last
            except Exception as exc:
                self.audit.emit(
                    "FX_RATE_UNAVAILABLE",
                    "WARNING",
                    currency=currency,
                    base_currency=base,
                    error=type(exc).__name__,
                )
        return rates

    def _publish(self, learning: dict[str, Any] | None = None) -> None:
        values = {
            "status": self.stage.value,
            "connection": (
                "CONNECTED"
                if self.ibkr.app is not None
                and self.ibkr.app.isConnected()
                else "DISCONNECTED"
            ),
            "equity": getattr(self.portfolio, "equity", Decimal("0")),
            "cash": getattr(self.portfolio, "cash", Decimal("0")),
            "buying_power": getattr(
                self.portfolio, "buying_power", Decimal("0")
            ),
            "margin_used": getattr(
                self.portfolio, "margin_used", Decimal("0")
            ),
            "daily_pnl": getattr(
                self.portfolio, "daily_pnl", Decimal("0")
            ),
            "gross_exposure": getattr(
                self.portfolio, "gross_exposure", Decimal("0")
            ),
            "net_exposure": getattr(
                self.portfolio, "net_exposure", Decimal("0")
            ),
            "positions": len(
                getattr(self.portfolio, "positions", {})
            ),
            "cycle": self.cycle_id,
            **self.stats,
            "last_order": "",
            "risk": (
                "RECOVERY_REQUIRED"
                if self.recovery.required
                else "OK"
            ),
            "regime": "MULTI",
            "news": self.news.status,
            "gemini": self.gemini.status,
            "learning": (learning or {}).get(
                "status", self.learning.status
            ),
        }
        result = self.sensors.publish(values)
        self.audit.emit(
            "HA_SENSOR_PUBLISH_RESULT",
            "INFO",
            **result,
        )
