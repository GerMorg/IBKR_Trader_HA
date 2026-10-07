from __future__ import annotations

import pytest

from app.config import Config


def test_defaults_are_safe() -> None:
    cfg = Config.from_mapping({})
    assert cfg.kill_switch is True
    assert cfg.trading_enabled is False
    assert cfg.require_what_if is True
    assert cfg.trading_mode == "paper"


def test_invalid_exposure_relationship_is_rejected() -> None:
    with pytest.raises(ValueError, match="gross"):
        Config.from_mapping({"risk_max_net_pct": 80, "risk_max_gross_pct": 60})


def test_string_booleans_are_parsed() -> None:
    cfg = Config.from_mapping({"trading_enabled": "true", "kill_switch": "off"})
    assert cfg.trading_enabled is True
    assert cfg.kill_switch is False
