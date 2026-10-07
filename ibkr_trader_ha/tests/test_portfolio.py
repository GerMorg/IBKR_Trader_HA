from decimal import Decimal

from app.portfolio import PortfolioEngine


def test_portfolio_keeps_position_quantity_and_exposure_separate(equity, snapshot) -> None:
    portfolio = PortfolioEngine("EUR").build(
        {"AccountId": "U123", "NetLiquidation": "10000", "TotalCashValue": "9000", "AvailableFunds": "8000"},
        [{"con_id": 1001, "quantity": "10", "average_cost": "95"}],
        {1001: equity},
        {1001: snapshot},
        {"USDEUR": Decimal("0.9")},
    )
    assert portfolio.position_quantities[1001] == Decimal("10")
    assert portfolio.positions[1001] == Decimal("900")
    assert portfolio.gross_exposure == Decimal("900")
    assert portfolio.valuation_complete is True


def test_portfolio_flags_missing_market_data(equity) -> None:
    portfolio = PortfolioEngine("EUR").build(
        {"AccountId": "U123", "NetLiquidation": "10000", "TotalCashValue": "9000", "AvailableFunds": "8000"},
        [{"con_id": 1001, "quantity": "10", "average_cost": "95"}],
        {1001: equity},
        {},
        {"USDEUR": Decimal("0.9")},
    )
    assert portfolio.positions[1001] == Decimal("855")
    assert portfolio.valuation_complete is False
