from decimal import Decimal

import pytest

from app.portfolio import CurrencyConverter


def test_direct_fx_conversion() -> None:
    assert CurrencyConverter().to_base(Decimal("100"), "USD", "EUR", {"USDEUR": Decimal("0.92")}) == Decimal("92.00")


def test_inverse_fx_conversion() -> None:
    assert CurrencyConverter().to_base(Decimal("92"), "USD", "EUR", {"EURUSD": Decimal("1.25")}) == Decimal("73.6")


def test_missing_fx_rate_is_blocking() -> None:
    with pytest.raises(ValueError, match="FX_RATE_UNAVAILABLE"):
        CurrencyConverter().to_base(Decimal("10"), "GBP", "EUR", {})
