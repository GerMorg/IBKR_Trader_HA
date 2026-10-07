from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    ibkr_host: str
    ibkr_port: int
    ibkr_client_id: int
    ibkr_account: str
    ibkr_connect_timeout_seconds: int
    ibkr_request_timeout_seconds: int
    ibkr_reconnect_max_seconds: int
    base_currency: str
    trading_mode: str
    trading_enabled: bool
    kill_switch: bool
    require_what_if: bool

    asset_equities_enabled: bool
    asset_etfs_enabled: bool
    asset_fx_enabled: bool
    asset_futures_enabled: bool
    asset_options_enabled: bool
    asset_bonds_enabled: bool
    asset_funds_enabled: bool
    asset_structured_enabled: bool

    scan_interval_seconds: int
    scan_max_results_per_profile: int
    scan_profiles_per_cycle: int
    market_data_cache_seconds: int
    historical_cache_seconds: int
    max_deep_analysis_candidates: int
    max_option_underlyings: int
    max_option_contracts: int
    max_gemini_candidates: int
    max_orderbook_age_seconds: int
    max_market_data_age_seconds: int
    min_average_daily_notional_eur: float
    max_spread_bps: float

    strategy_min_edge_bps: float
    strategy_min_confidence: float
    risk_per_trade_pct: float
    risk_max_position_pct: float
    risk_max_order_pct: float
    risk_max_gross_pct: float
    risk_max_net_pct: float
    risk_max_margin_pct: float
    risk_max_leverage: float
    risk_max_open_positions: int
    risk_daily_loss_pct: float
    risk_max_drawdown_pct: float
    risk_cash_reserve_pct: float
    risk_max_correlation_exposure_pct: float
    risk_max_sector_exposure_pct: float
    risk_max_currency_exposure_pct: float
    risk_max_orders_per_day: int
    execution_max_slippage_bps: float
    execution_timeout_seconds: int
    execution_max_reprices: int

    learning_enabled: bool
    learning_min_samples: int
    learning_validation_fraction: float
    learning_min_improvement: float
    learning_recalibration_hours: int
    learning_auto_promotion: bool

    news_enabled: bool
    news_refresh_minutes: int
    news_source_timeout_seconds: int
    gemini_enabled: bool
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_seconds: int

    database_path: str
    tax_reporting_enabled: bool
    tax_report_directory: str
    sensors_enabled: bool
    log_file_enabled: bool

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "Config":
        def b(name: str, default: bool) -> bool:
            value = raw.get(name, default)
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)

        def i(name: str, default: int, low: int = 0) -> int:
            try:
                return max(low, int(raw.get(name, default)))
            except (TypeError, ValueError):
                return default

        def f(name: str, default: float, low: float = 0.0, high: float | None = None) -> float:
            try:
                value = float(raw.get(name, default))
            except (TypeError, ValueError):
                value = default
            value = max(low, value)
            return min(high, value) if high is not None else value

        cfg = cls(
            ibkr_host=str(raw.get("ibkr_host", "127.0.0.1")).strip(),
            ibkr_port=i("ibkr_port", 4002, 1),
            ibkr_client_id=i("ibkr_client_id", 170, 0),
            ibkr_account=str(raw.get("ibkr_account", "")).strip(),
            ibkr_connect_timeout_seconds=i("ibkr_connect_timeout_seconds", 20, 5),
            ibkr_request_timeout_seconds=i("ibkr_request_timeout_seconds", 15, 3),
            ibkr_reconnect_max_seconds=i("ibkr_reconnect_max_seconds", 60, 5),
            base_currency=str(raw.get("base_currency", "EUR")).strip().upper() or "EUR",
            trading_mode=str(raw.get("trading_mode", "paper")).strip().lower(),
            trading_enabled=b("trading_enabled", False),
            kill_switch=b("kill_switch", True),
            require_what_if=b("require_what_if", True),
            asset_equities_enabled=b("asset_equities_enabled", True),
            asset_etfs_enabled=b("asset_etfs_enabled", True),
            asset_fx_enabled=b("asset_fx_enabled", True),
            asset_futures_enabled=b("asset_futures_enabled", True),
            asset_options_enabled=b("asset_options_enabled", True),
            asset_bonds_enabled=b("asset_bonds_enabled", True),
            asset_funds_enabled=b("asset_funds_enabled", False),
            asset_structured_enabled=b("asset_structured_enabled", False),
            scan_interval_seconds=i("scan_interval_seconds", 300, 30),
            scan_max_results_per_profile=i("scan_max_results_per_profile", 50, 1),
            scan_profiles_per_cycle=i("scan_profiles_per_cycle", 6, 1),
            market_data_cache_seconds=i("market_data_cache_seconds", 20, 1),
            historical_cache_seconds=i("historical_cache_seconds", 900, 30),
            max_deep_analysis_candidates=i("max_deep_analysis_candidates", 30, 1),
            max_option_underlyings=i("max_option_underlyings", 5, 1),
            max_option_contracts=i("max_option_contracts", 30, 1),
            max_gemini_candidates=i("max_gemini_candidates", 12, 1),
            max_orderbook_age_seconds=i("max_orderbook_age_seconds", 15, 1),
            max_market_data_age_seconds=i("max_market_data_age_seconds", 30, 1),
            min_average_daily_notional_eur=f("min_average_daily_notional_eur", 100000, 0),
            max_spread_bps=f("max_spread_bps", 60, 0),
            strategy_min_edge_bps=f("strategy_min_edge_bps", 25, 0),
            strategy_min_confidence=f("strategy_min_confidence", 0.60, 0, 1),
            risk_per_trade_pct=f("risk_per_trade_pct", 0.50, 0.05, 5),
            risk_max_position_pct=f("risk_max_position_pct", 8, 0.1, 100),
            risk_max_order_pct=f("risk_max_order_pct", 3, 0.1, 100),
            risk_max_gross_pct=f("risk_max_gross_pct", 60, 0.1, 100),
            risk_max_net_pct=f("risk_max_net_pct", 40, 0.1, 100),
            risk_max_margin_pct=f("risk_max_margin_pct", 30, 0.1, 100),
            risk_max_leverage=f("risk_max_leverage", 5, 1, 10),
            risk_max_open_positions=i("risk_max_open_positions", 8, 1),
            risk_daily_loss_pct=f("risk_daily_loss_pct", 2, 0.1, 100),
            risk_max_drawdown_pct=f("risk_max_drawdown_pct", 6, 0.1, 100),
            risk_cash_reserve_pct=f("risk_cash_reserve_pct", 20, 0, 100),
            risk_max_correlation_exposure_pct=f("risk_max_correlation_exposure_pct", 30, 0.1, 100),
            risk_max_sector_exposure_pct=f("risk_max_sector_exposure_pct", 30, 0.1, 100),
            risk_max_currency_exposure_pct=f("risk_max_currency_exposure_pct", 50, 0.1, 100),
            risk_max_orders_per_day=i("risk_max_orders_per_day", 12, 1),
            execution_max_slippage_bps=f("execution_max_slippage_bps", 30, 0, 2000),
            execution_timeout_seconds=i("execution_timeout_seconds", 45, 5),
            execution_max_reprices=i("execution_max_reprices", 2, 0),
            learning_enabled=b("learning_enabled", True),
            learning_min_samples=i("learning_min_samples", 100, 20),
            learning_validation_fraction=f("learning_validation_fraction", 0.30, 0.1, 0.5),
            learning_min_improvement=f("learning_min_improvement", 0.01, 0.0001, 1),
            learning_recalibration_hours=i("learning_recalibration_hours", 24, 1),
            learning_auto_promotion=b("learning_auto_promotion", True),
            news_enabled=b("news_enabled", True),
            news_refresh_minutes=i("news_refresh_minutes", 10, 1),
            news_source_timeout_seconds=i("news_source_timeout_seconds", 10, 3),
            gemini_enabled=b("gemini_enabled", True),
            gemini_api_key=str(raw.get("gemini_api_key", "")).strip(),
            gemini_model=str(raw.get("gemini_model", "gemini-2.5-flash")).strip(),
            gemini_timeout_seconds=i("gemini_timeout_seconds", 30, 5),
            database_path=str(raw.get("database_path", "/data/ibkr_trader.db")),
            tax_reporting_enabled=b("tax_reporting_enabled", True),
            tax_report_directory=str(raw.get("tax_report_directory", "/config/reports/tax")),
            sensors_enabled=b("sensors_enabled", True),
            log_file_enabled=b("log_file_enabled", True),
        )
        cls.validate(cfg)
        return cfg

    @classmethod
    def load(cls, path: str = "/data/options.json") -> "Config":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        return cls.from_mapping(raw)

    @staticmethod
    def validate(cfg: "Config") -> None:
        if cfg.trading_mode not in {"paper", "live"}:
            raise ValueError("trading_mode must be paper or live")
        if len(cfg.base_currency) != 3 or not cfg.base_currency.isalpha():
            raise ValueError("base_currency must be a 3-letter currency code")
        if cfg.trading_mode == "live" and cfg.trading_enabled and not cfg.ibkr_account:
            raise ValueError("ibkr_account is required for enabled live trading")
        if not cfg.ibkr_host:
            raise ValueError("ibkr_host must not be empty")
        if cfg.risk_max_net_pct > cfg.risk_max_gross_pct:
            raise ValueError("net exposure limit cannot exceed gross exposure limit")
        if cfg.risk_max_position_pct > cfg.risk_max_gross_pct:
            raise ValueError("position limit cannot exceed gross exposure limit")
        if cfg.risk_max_order_pct > cfg.risk_max_position_pct:
            raise ValueError("order limit cannot exceed position limit")
        if cfg.learning_validation_fraction <= 0 or cfg.learning_validation_fraction >= 1:
            raise ValueError("learning_validation_fraction must be between 0 and 1")
