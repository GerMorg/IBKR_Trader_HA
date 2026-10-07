from __future__ import annotations

import time

from app.config import Config
from app.discovery import DiscoveryEngine
from app.execution import ExecutionEngine
from app.gemini import GeminiAnalyzer
from app.ibkr import IBKRClient
from app.learning import LearningEngine
from app.market import MarketDataEngine
from app.monitoring import AuditLogger
from app.news import NewsEngine
from app.persistence import Database
from app.portfolio import PortfolioEngine
from app.recovery import RecoveryManager
from app.risk import LeverageEngine, PositionSizer, RiskEngine
from app.runtime import Runtime
from app.sensors import SensorPublisher
from app.strategy import StrategyDispatcher
from app.tax import AustrianTaxLedger
from app.trading import DecisionEngine


def build_runtime(config: Config | None = None) -> Runtime:
    cfg = config or Config.load()
    db = Database(cfg.database_path)
    audit = AuditLogger(cfg.log_file_enabled)
    ibkr = IBKRClient(
        cfg.ibkr_host,
        cfg.ibkr_port,
        cfg.ibkr_client_id,
        cfg.ibkr_account,
        cfg.base_currency,
        cfg.ibkr_connect_timeout_seconds,
        cfg.ibkr_request_timeout_seconds,
    )
    recovery = RecoveryManager(db, audit)
    discovery = DiscoveryEngine(ibkr, cfg)
    market = MarketDataEngine(ibkr, cfg)
    portfolio = PortfolioEngine(cfg.base_currency)
    strategies = StrategyDispatcher()
    decisions = DecisionEngine()
    risk = RiskEngine(cfg)
    sizing = PositionSizer(cfg.risk_per_trade_pct, cfg.risk_max_position_pct, cfg.risk_max_order_pct)
    leverage = LeverageEngine()
    execution = ExecutionEngine(ibkr, db, risk, cfg, audit)
    news = NewsEngine(db, cfg.news_refresh_minutes, cfg.news_source_timeout_seconds)
    gemini = GeminiAnalyzer(cfg.gemini_api_key, cfg.gemini_model, cfg.gemini_enabled, cfg.gemini_timeout_seconds, audit)
    learning = LearningEngine(db, cfg, audit)
    sensors = SensorPublisher(cfg.sensors_enabled)
    tax = AustrianTaxLedger(db, cfg.tax_report_directory)
    return Runtime(
        cfg, db, audit, ibkr, discovery, market, portfolio, strategies,
        decisions, risk, sizing, leverage, execution, news, gemini,
        learning, sensors, recovery, tax,
    )


def main() -> None:
    runtime = build_runtime()
    if not runtime.startup():
        while True:
            time.sleep(60)
    next_cycle = time.monotonic()
    while True:
        runtime.run_cycle()
        next_cycle += runtime.config.scan_interval_seconds
        delay = next_cycle - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            next_cycle = time.monotonic()


if __name__ == "__main__":
    main()
