from __future__ import annotations

from decimal import Decimal
import time

import pytest

from app.config import Config
from app.domain.models import CapabilityProfile, Contract, Instrument, MarketSnapshot
from app.domain.states import AssetClass


@pytest.fixture()
def config() -> Config:
    return Config.from_mapping({
        "trading_mode": "paper",
        "trading_enabled": True,
        "kill_switch": False,
        "gemini_enabled": False,
        "news_enabled": False,
        "database_path": ":memory:",
    })


@pytest.fixture()
def equity() -> Instrument:
    contract = Contract(
        con_id=1001,
        symbol="TEST",
        local_symbol="TEST",
        security_type="STK",
        exchange="SMART",
        primary_exchange="NYSE",
        currency="USD",
        min_tick=Decimal("0.01"),
        size_increment=Decimal("1"),
        min_size=Decimal("1"),
        multiplier=Decimal("1"),
    )
    capability = CapabilityProfile(
        can_long=True, can_short=True, can_margin=True,
        can_market_order=True, can_limit_order=True, can_stop=True,
        can_trailing=True, can_bracket=True, can_fractional=False,
        supports_combo=False, market_data_available=True,
        historical_data_available=True, account_eligible=True,
        tradable_now=True, supported_by_strategy=True, supported_by_risk=True,
    )
    return Instrument(contract, AssetClass.EQUITY, capability, "TECHNOLOGY", "Software", "Test Inc")


@pytest.fixture()
def snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        con_id=1001, timestamp=time.time(), last=Decimal("100"),
        bid=Decimal("99.95"), ask=Decimal("100.05"),
        volume=Decimal("100000"), average_daily_notional=Decimal("10000000"),
    )
