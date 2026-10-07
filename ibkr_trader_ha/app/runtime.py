from __future__ import annotations

from decimal import Decimal
import time
from typing import Any

from app.config import Config
from app.discovery import DiscoveryEngine
from app.domain.models import digest_config
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
        self.portfolio = None
        self.stats: dict[str, Any] = {}

    def startup(self) -> bool:
        self.stage = RuntimeStage.CONFIG_LOADED
        self.audit.emit("STARTUP_CONFIG_LOADED", config_hash=digest_config(self.config.__dict__))
        try:
            if self.db.recovery_state() and self.db.recovery_state().get("state") == "RECOVERY_REQUIRED":
                self.recovery.require(self.db.recovery_state().get("detail", "persisted recovery"))
            self.ibkr.connect()
            self.stage = RuntimeStage.IBKR_CONNECTED
            self.audit.emit("IBKR_CONNECTED", host=self.config.ibkr_host, port=self.config.ibkr_port)
            account = self.ibkr.account_summary()
            raw_positions = self.ibkr.positions()
            self.audit.emit("PORTFOLIO_RECONCILIATION", raw_positions=len(raw_positions))
            discovered, discovery_stats = self.discovery.discover()
            self.instruments = {item.contract.con_id: item for item in discovered}

            for row in raw_positions:
                con_id = int(row.get("con_id", 0) or 0)
                if con_id and con_id not in self.instruments:
                    try:
                        details = self.ibkr.contract_details({"con_id": con_id})
                        if details:
                            item = self.discovery.map_contract(details[0])
                            self.instruments[con_id] = item
                    except Exception as exc:
                        self.audit.emit("CONTRACT_DISCOVERY_FAILED", "WARNING", con_id=con_id, error=type(exc).__name__)

            snapshots: dict[int, Any] = {}
            for con_id, instrument in list(self.instruments.items()):
                if any(int(row.get("con_id", 0)) == con_id for row in raw_positions):
                    snap = self.market.snapshot(instrument)
                    if snap:
                        snapshots[con_id] = snap

            fx_rates = self._fx_rates(self.instruments, snapshots)
            self.portfolio = self.portfolio_engine.build(account, raw_positions, self.instruments, snapshots, fx_rates)
            self.db.save_portfolio(self.portfolio)

            open_orders = self.ibkr.open_orders()
            self._reconcile_open_orders(open_orders)
            self.stage = RuntimeStage.ACCOUNT_RECONCILED
            self.recovery.clear()
            self.stage = RuntimeStage.READY
            self._publish()
            self.audit.emit("STARTUP_READY", instruments=len(self.instruments), **discovery_stats)
            return True
        except Exception as exc:
            self.stage = RuntimeStage.SAFE_MODE
            self.recovery.require(f"STARTUP:{type(exc).__name__}:{str(exc)[:300]}")
            self._publish()
            return False

    def run_cycle(self) -> dict[str, Any]:
        if self.stage != RuntimeStage.READY and not self.startup():
            return {"status": "SAFE_MODE", "cycle_id": self.cycle_id}
        self.cycle_id = f"cycle_{time.time_ns()}"
        self.stage = RuntimeStage.RUNNING
        blockers: list[str] = []
        self.stats = {"discovered": 0, "candidates": 0, "analyzed": 0, "approved": 0, "blocked": 0, "traded": 0}
        self.db.start_cycle(self.cycle_id, digest_config(self.config.__dict__))
        self.audit.emit("CYCLE_START", cycle_id=self.cycle_id)

        try:
            account = self.ibkr.account_summary()
            raw_positions = self.ibkr.positions()
            open_orders = self.ibkr.open_orders()
            self._reconcile_open_orders(open_orders)

            discovered, discovery_stats = self.discovery.discover()
            for item in discovered:
                self.instruments[item.contract.con_id] = item
            self.stats["discovered"] = discovery_stats["discovered"]

            snapshots: dict[int, Any] = {}
            ranked = discovered[: max(self.config.max_deep_analysis_candidates * 2, 50)]
            held_ids = set(int(row.get("con_id", 0)) for row in raw_positions)
            for con_id in held_ids:
                if con_id in self.instruments and con_id not in {x.contract.con_id for x in ranked}:
                    ranked.append(self.instruments[con_id])
            for instrument in ranked:
                snap = self.market.snapshot(instrument)
                if snap:
                    snapshots[instrument.contract.con_id] = snap
                    self.db.save_market(snap)

            self.stats["candidates"] = len(snapshots)
            histories: dict[int, list[dict[str, Any]]] = {}
            for instrument in ranked[: self.config.max_deep_analysis_candidates]:
                histories[instrument.contract.con_id] = self.market.history(instrument)

            fx_rates = self._fx_rates(self.instruments, snapshots)
            self.portfolio = self.portfolio_engine.build(account, raw_positions, self.instruments, snapshots, fx_rates)
            self.db.save_portfolio(self.portfolio)

            news_items = self.news.collect() if self.config.news_enabled else []
            decisions: list[Any] = []
            model_scale = Decimal("1")
            for instrument in ranked[: self.config.max_deep_analysis_candidates]:
                snap = snapshots.get(instrument.contract.con_id)
                if snap is None:
                    blockers.append(f"{instrument.symbol}:MARKET_DATA_UNAVAILABLE")
                    continue
                feats = self.features.calculate(snap, histories.get(instrument.contract.con_id, []))
                regime = self.regimes.detect(feats)
                news_impact = self.news.effect_for(instrument, news_items) if news_items else Decimal("0")
                ai = {"effect_bps": Decimal("0"), "status": "DISABLED"}
                if self.config.gemini_enabled and len(decisions) < self.config.max_gemini_candidates:
                    ai = self.gemini.analyze(instrument, feats, news_impact, regime)
                pair = self.strategies.evaluate(
                    instrument, snap, feats, regime, news_impact, Decimal(str(ai.get("effect_bps", 0)))
                )
                if not pair:
                    blockers.append(f"{instrument.symbol}:ANALYSIS_ONLY")
                    continue
                decision = self.decisions.select(instrument, pair[0], pair[1], self.portfolio, model_scale)
                self.stats["analyzed"] += 1
                if decision is None:
                    continue
                self.db.save_decision(self.cycle_id, decision)
                self.learning.record_decision(decision, self.cycle_id)
                decision = self._size_decision(decision, snap, feats)
                risk_result = self.risk.evaluate(
                    decision, self.portfolio, snap, None, self._orders_today()
                )
                self.db.risk_event(self.cycle_id, instrument.contract.con_id, risk_result)
                self.audit.emit(
                    "RISK_EVALUATION",
                    "INFO" if risk_result.allowed else "WARNING",
                    con_id=instrument.contract.con_id,
                    reason=risk_result.reason,
                    checks=risk_result.checks,
                )
                if not risk_result.allowed:
                    self.stats["blocked"] += 1
                    blockers.append(f"{instrument.symbol}:{risk_result.reason}")
                    continue
                self.stats["approved"] += 1
                decisions.append((decision, snap))

            for decision, snap in decisions:
                result = self.execution.execute(
                    decision, snap, None, self._orders_today()
                )
                self.learning.record_order(decision.decision_id, result)
                state = str(result.get("state", ""))
                if state in {OrderState.ACKNOWLEDGED.value, OrderState.LIVE.value, OrderState.PARTIALLY_FILLED.value, OrderState.FILLED.value}:
                    self.stats["traded"] += 1
                elif state == "BLOCKED":
                    self.stats["blocked"] += 1
                    blockers.append(f"{decision.instrument.symbol}:{result.get('reason', 'ORDER_BLOCKED')}")

            self._reconcile_after_cycle()
            learning = self.learning.recalibrate()
            self.db.finish_cycle(self.cycle_id, "COMPLETED", ";".join(blockers[:5]))
            self.stage = RuntimeStage.READY
            self._publish(learning=learning)
            self.audit.emit("CYCLE_COMPLETE", cycle_id=self.cycle_id, **self.stats, blockers=blockers[:10])
            return {"status": "COMPLETED", "cycle_id": self.cycle_id, **self.stats, "blockers": blockers}
        except Exception as exc:
            self.db.finish_cycle(self.cycle_id, "FAILED", type(exc).__name__)
            self.recovery.require(f"CYCLE:{type(exc).__name__}:{str(exc)[:300]}")
            self.stage = RuntimeStage.RECOVERY_REQUIRED
            self._publish()
            self.audit.emit("CYCLE_FAILED", "ERROR", cycle_id=self.cycle_id, error=type(exc).__name__)
            return {"status": "FAILED", "cycle_id": self.cycle_id, "error": type(exc).__name__}

    def _size_decision(self, decision: Any, snapshot: Any, features: dict[str, Decimal]) -> Any:
        from app.domain.models import Decision
        if decision.action in {DecisionAction.EXIT, DecisionAction.REBALANCE}:
            return self.decisions.with_position(decision, Decimal("0"), abs(decision.current_position), Decimal("1"), True)
        qty, notional = self.sizing.size(
            decision.instrument,
            snapshot.ask if decision.action == DecisionAction.LONG else snapshot.bid,
            features.get("volatility", Decimal("5")),
            self.portfolio.equity,
        )
        leverage = self.leverage.choose(
            decision.instrument,
            decision.signal.confidence,
            features.get("volatility", Decimal("5")),
            Decimal(str(self.config.risk_max_leverage)),
        )
        price = snapshot.ask if decision.action == DecisionAction.LONG else snapshot.bid
        target_notional = notional
        target = decision.current_position + target_notional if decision.action == DecisionAction.LONG else decision.current_position - target_notional
        return self.decisions.with_position(decision, target, notional, leverage, False)

    def _orders_today(self) -> int:
        now = time.time()
        start = now - (now % 86400)
        row = self.db.one("SELECT COUNT(*) AS n FROM orders WHERE submitted_at>=?", (start,))
        return int(row["n"]) if row else 0

    def _reconcile_open_orders(self, open_orders: list[dict[str, Any]]) -> None:
        broker_ids = {int(row.get("order_id", 0)) for row in open_orders}
        local = self.db.query(
            "SELECT broker_order_id,state FROM orders WHERE state IN ('SUBMITTING','ACKNOWLEDGED','LIVE','PARTIALLY_FILLED','UNKNOWN_RECONCILING')"
        )
        for row in local:
            oid = int(row["broker_order_id"])
            if oid not in broker_ids:
                status = self.ibkr.order_status(oid)
                if not status:
                    self.recovery.require(f"ORDER_STATE_UNKNOWN:{oid}")

    def _reconcile_after_cycle(self) -> None:
        executions = self.ibkr.executions()
        for execution in executions:
            self.tax.record_fill(execution)
        self.audit.emit("EXECUTION", "INFO", count=len(executions))
        positions = self.ibkr.positions()
        self.audit.emit("PORTFOLIO_RECONCILIATION", "INFO", positions=len(positions))

    @staticmethod
    def _fx_rates(instruments: dict[int, Any], snapshots: dict[int, Any]) -> dict[str, Decimal]:
        rates: dict[str, Decimal] = {}
        for con_id, instrument in instruments.items():
            snap = snapshots.get(con_id)
            if not snap or instrument.contract.security_type != "CASH":
                continue
            symbol = instrument.symbol.replace("/", ".").replace(" ", ".").upper()
            rates[symbol.replace(".", "")] = snap.last
        return rates

    def _publish(self, learning: dict[str, Any] | None = None) -> None:
        values = {
            "status": self.stage.value,
            "connection": "CONNECTED" if self.ibkr.app is not None and self.ibkr.app.isConnected() else "DISCONNECTED",
            "equity": getattr(self.portfolio, "equity", Decimal("0")),
            "cash": getattr(self.portfolio, "cash", Decimal("0")),
            "buying_power": getattr(self.portfolio, "buying_power", Decimal("0")),
            "margin_used": getattr(self.portfolio, "margin_used", Decimal("0")),
            "daily_pnl": getattr(self.portfolio, "daily_pnl", Decimal("0")),
            "gross_exposure": getattr(self.portfolio, "gross_exposure", Decimal("0")),
            "net_exposure": getattr(self.portfolio, "net_exposure", Decimal("0")),
            "positions": len(getattr(self.portfolio, "positions", {})),
            "cycle": self.cycle_id,
            **self.stats,
            "last_order": "",
            "risk": "RECOVERY_REQUIRED" if self.recovery.required else "OK",
            "regime": "MULTI",
            "news": self.news.status,
            "gemini": self.gemini.status,
            "learning": (learning or {}).get("status", self.learning.status),
        }
        result = self.sensors.publish(values)
        self.audit.emit("HA_SENSOR_PUBLISH_RESULT", "INFO", **result)
