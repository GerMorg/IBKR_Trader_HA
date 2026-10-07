from datetime import datetime
from zoneinfo import ZoneInfo

from app.market import is_liquid_now


def test_liquid_hours_inside_session() -> None:
    now = datetime(2026, 10, 7, 15, 0, tzinfo=ZoneInfo("Europe/Vienna"))
    assert is_liquid_now("20261007:0900-1700", "Europe/Vienna", now) is True


def test_liquid_hours_outside_session() -> None:
    now = datetime(2026, 10, 7, 18, 0, tzinfo=ZoneInfo("Europe/Vienna"))
    assert is_liquid_now("20261007:0900-1700", "Europe/Vienna", now) is False


def test_closed_day_is_not_tradable() -> None:
    now = datetime(2026, 10, 7, 12, 0, tzinfo=ZoneInfo("Europe/Vienna"))
    assert is_liquid_now("20261007:CLOSED", "Europe/Vienna", now) is False


def test_overnight_session() -> None:
    now = datetime(2026, 10, 8, 1, 0, tzinfo=ZoneInfo("Europe/Vienna"))
    assert is_liquid_now("20261007:2200-0200;20261008:CLOSED", "Europe/Vienna", now) is True
