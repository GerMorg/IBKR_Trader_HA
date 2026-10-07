from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import time
import uuid

from .states import AssetClass, DecisionAction, OrderState


D = Decimal


@dataclass(frozen=True)
class CapabilityProfile:
    can_long: bool
    can_short: bool
    can_margin: bool
    can_market_order: bool
    can_limit_order: bool
    can_stop: bool
    can_trailing: bool
    can_bracket: bool
    can_fractional: bool
    supports_combo: bool
    market_data_available: bool
    historical_data_available: bool
    account_eligible: bool
    tradable_now: bool
    supported_by_strategy: bool
    supported_by_risk: bool
    shortability_score: Decimal = D("0")
    short_requires_locate: bool = False
    ineligibility_reason: str = ""


@dataclass(frozen=True)
class Contract:
    con_id: int
    symbol: str
    local_symbol: str
    security_type: str
    exchange: str
    primary_exchange: str
    currency: str
    trading_class: str = ""
    multiplier: Decimal = D("1")
    min_tick: Decimal = D("0.01")
    size_increment: Decimal = D("1")
    min_size: Decimal = D("0")
    trading_hours: str = ""
    liquid_hours: str = ""
    expiry: str = ""
    contract_month: str = ""
    strike: Decimal | None = None
    right: str = ""
    underlying: str = ""
    underlying_con_id: int | None = None
    market_rule_ids: tuple[int, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Instrument:
    contract: Contract
    asset_class: AssetClass
    capability: CapabilityProfile
    sector: str = ""
    industry: str = ""
    description: str = ""

    @property
    def key(self) -> str:
        return f"{self.contract.con_id}:{self.contract.local_symbol}"

    @property
    def symbol(self) -> str:
        return self.contract.symbol

    @property
    def currency(self) -> str:
        return self.contract.currency

    @property
    def tradeable(self) -> bool:
        return (
            self.capability.account_eligible
            and self.capability.tradable_now
            and self.capability.supported_by_strategy
            and self.capability.market_data_available
        )


@dataclass(frozen=True)
class MarketSnapshot:
    con_id: int
    timestamp: float
    last: Decimal
    bid: Decimal
    ask: Decimal
    volume: Decimal = D("0")
    average_daily_notional: Decimal = D("0")
    closes: tuple[Decimal, ...] = ()
    high: Decimal = D("0")
    low: Decimal = D("0")
    open_interest: Decimal | None = None
    implied_volatility: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    shortable_shares: Decimal | None = None
    etf_nav: Decimal | None = None
    source: str = "IBKR"

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.timestamp)

    @property
    def spread_bps(self) -> Decimal:
        if self.bid <= 0 or self.ask <= 0:
            return D("999999")
        mid = (self.bid + self.ask) / D("2")
        return (self.ask - self.bid) / mid * D("10000")


@dataclass(frozen=True)
class NewsFeature:
    news_id: str
    source: str
    published_at: float
    title: str
    affected_assets: tuple[str, ...]
    affected_sectors: tuple[str, ...]
    sentiment: Decimal
    impact_bps: Decimal
    confidence: Decimal
    decay: Decimal
    gemini_interpretation: str = ""

    @property
    def active_impact_bps(self) -> Decimal:
        age_hours = max(0.0, (time.time() - self.published_at) / 3600.0)
        age_decay = max(D("0"), D("1") - D(str(age_hours)) / D("48"))
        return self.impact_bps * self.confidence * self.decay * age_decay


@dataclass(frozen=True)
class Signal:
    con_id: int
    action: DecisionAction
    confidence: Decimal
    expected_return: Decimal
    expected_risk: Decimal
    gross_edge_bps: Decimal
    expected_cost_bps: Decimal
    holding_period_hours: int
    target_position: Decimal
    rationale: str
    feature_snapshot: dict[str, Decimal]
    data_quality: Decimal
    invalidation_conditions: tuple[str, ...] = ()

    @property
    def net_edge_bps(self) -> Decimal:
        return self.gross_edge_bps - self.expected_cost_bps


@dataclass(frozen=True)
class Decision:
    decision_id: str
    instrument: Instrument
    signal: Signal
    action: DecisionAction
    target_position: Decimal
    current_position: Decimal
    quantity_notional: Decimal
    leverage: Decimal
    reduce_only: bool
    strategy_version: str
    model_version: str
    rationale: dict[str, object]
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    idempotency_key: str
    decision_id: str
    con_id: int
    action: DecisionAction
    side: str
    order_type: str
    quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    leverage: Decimal
    reduce_only: bool
    max_slippage_bps: Decimal
    state: OrderState = OrderState.INTENT_CREATED
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Fill:
    broker_order_id: int
    execution_id: str
    con_id: int
    side: str
    quantity: Decimal
    price: Decimal
    commission: Decimal
    commission_currency: str
    timestamp: float


@dataclass(frozen=True)
class ExecutionReport:
    broker_order_id: int
    con_id: int
    status: OrderState
    filled_quantity: Decimal
    remaining_quantity: Decimal
    average_fill_price: Decimal
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class PortfolioState:
    account_id: str = ""
    currency: str = "EUR"
    equity: Decimal = D("0")
    cash: Decimal = D("0")
    available_funds: Decimal = D("0")
    buying_power: Decimal = D("0")
    gross_exposure: Decimal = D("0")
    net_exposure: Decimal = D("0")
    margin_used: Decimal = D("0")
    maintenance_margin: Decimal = D("0")
    unrealized_pnl: Decimal = D("0")
    realized_pnl: Decimal = D("0")
    daily_pnl: Decimal = D("0")
    positions: dict[int, Decimal] = field(default_factory=dict)
    position_quantities: dict[int, Decimal] = field(default_factory=dict)
    valuation_complete: bool = True
    position_currency: dict[int, str] = field(default_factory=dict)
    position_asset_class: dict[int, AssetClass] = field(default_factory=dict)
    position_sector: dict[int, str] = field(default_factory=dict)
    source_timestamp: float = field(default_factory=time.time)
    peak_equity: Decimal = D("0")

    @property
    def drawdown_pct(self) -> Decimal:
        peak = self.peak_equity if self.peak_equity > 0 else self.equity
        if peak <= 0:
            return D("0")
        return max(D("0"), (peak - self.equity) / peak * D("100"))


@dataclass(frozen=True)
class RiskResult:
    allowed: bool
    reason: str
    checks: dict[str, bool]
    effective_leverage: Decimal
    max_quantity: Decimal = D("0")
    margin_required: Decimal = D("0")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def idempotency_key(con_id: int, action: DecisionAction, target_position: Decimal) -> str:
    raw = f"{con_id}|{action.value}|{target_position.quantize(D('0.00000001'))}"
    return sha256(raw.encode("utf-8")).hexdigest()[:40]


def digest_config(value: object) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def utc_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).isoformat()
