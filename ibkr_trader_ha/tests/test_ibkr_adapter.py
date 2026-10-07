from __future__ import annotations

from decimal import Decimal

from app.ibkr.client import IBKRClient


class FakeContract:
    def __init__(self) -> None:
        self.conId = 0
        self.symbol = ""
        self.localSymbol = ""
        self.secType = ""
        self.exchange = ""
        self.primaryExchange = ""
        self.currency = ""
        self.tradingClass = ""
        self.lastTradeDateOrContractMonth = ""
        self.strike = 0.0
        self.right = ""
        self.multiplier = ""


class FakeOrder:
    def __init__(self) -> None:
        self.action = ""
        self.orderType = ""
        self.totalQuantity = 0.0
        self.tif = ""
        self.orderRef = ""
        self.transmit = False
        self.whatIf = False
        self.lmtPrice = 0.0
        self.auxPrice = 0.0


def test_contract_mapping_does_not_leak_native_types() -> None:
    client = IBKRClient("127.0.0.1", 4002, 1)
    client.NativeContract = FakeContract
    contract = client._make_contract({
        "con_id": 123,
        "symbol": "AAPL",
        "local_symbol": "AAPL",
        "security_type": "STK",
        "exchange": "SMART",
        "primary_exchange": "NASDAQ",
        "currency": "USD",
        "trading_class": "NMS",
    })
    assert contract.conId == 123
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"


def test_order_translation_preserves_decimal_quantity_and_prices() -> None:
    client = IBKRClient("127.0.0.1", 4002, 1)
    client.NativeOrder = FakeOrder
    order = client._make_order({
        "side": "buy",
        "order_type": "LMT",
        "quantity": Decimal("1.25"),
        "limit_price": Decimal("100.15"),
    }, what_if=True)
    assert order.action == "BUY"
    assert order.orderType == "LMT"
    assert order.totalQuantity == 1.25
    assert order.lmtPrice == 100.15
    assert order.whatIf is True
    assert order.transmit is False
