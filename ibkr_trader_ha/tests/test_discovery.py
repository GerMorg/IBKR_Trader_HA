from decimal import Decimal

from app.discovery import DiscoveryEngine
from app.domain.states import AssetClass


def row(sec_type: str, con_id: int = 1) -> dict[str, str]:
    return {
        "con_id": str(con_id), "symbol": "TEST", "local_symbol": "TEST",
        "sec_type": sec_type, "exchange": "SMART", "primary_exchange": "NYSE",
        "currency": "USD", "trading_class": "TEST", "multiplier": "1",
        "min_tick": "0.01", "size_increment": "1", "min_size": "1",
        "order_types": "MKT,LMT,STP", "long_name": "Test security",
        "liquid_hours": "20261007:0000-2359", "time_zone_id": "UTC",
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


class FakeIBKR:
    def option_chain(self, underlying_con_id, symbol, underlying_sec_type):
        assert underlying_sec_type == "STK"
        return [{
            "exchange": "SMART",
            "trading_class": "TEST",
            "multiplier": "100",
            "expirations": ["29991231"],
            "strikes": [100.0, 105.0],
        }]

    def contract_details(self, query):
        return [row(
            "OPT", 9000 + int(float(query["strike"])) +
            (1 if query["right"] == "C" else 2)
        )]


class Cfg:
    asset_options_enabled = True
    max_option_underlyings = 1
    max_option_contracts = 4


def test_option_discovery_uses_chain_and_contract_details(equity) -> None:
    engine = DiscoveryEngine(FakeIBKR(), Cfg())
    options = engine.discover_options([(equity, Decimal("101"))])
    assert len(options) == 4
    assert all(item.asset_class == AssetClass.OPTION for item in options)
