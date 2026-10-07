from decimal import Decimal

from app.discovery import DiscoveryEngine
from app.domain.states import AssetClass


def row(sec_type: str, con_id: int = 1) -> dict[str, str]:
    return {
        "con_id": str(con_id), "symbol": "TEST", "local_symbol": "TEST",
        "sec_type": sec_type, "exchange": "SMART", "primary_exchange": "NYSE",
        "currency": "USD", "trading_class": "TEST", "multiplier": "1",
        "min_tick": "0.01", "size_increment": "1", "min_size": "1",
        "order_types": "MKT,LMT,STP",
        "long_name": "Test security",
    }


def test_maps_supported_security_types() -> None:
    assert DiscoveryEngine.map_contract(row("STK")).asset_class == AssetClass.EQUITY
    assert DiscoveryEngine.map_contract(row("CASH", 2)).asset_class == AssetClass.FX
    assert DiscoveryEngine.map_contract(row("FUT", 3)).asset_class == AssetClass.FUTURES
    assert DiscoveryEngine.map_contract(row("OPT", 4)).asset_class == AssetClass.OPTION


def test_unknown_is_analysis_only() -> None:
    item = DiscoveryEngine.map_contract(row("UNKNOWN", 99))
    assert item.asset_class == AssetClass.UNKNOWN
    assert item.capability.supported_by_strategy is False
    assert item.tradeable is False
