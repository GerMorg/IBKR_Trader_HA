from decimal import Decimal

from app.market import FeatureEngine, RegimeEngine


def test_features_calculate() -> None:
    features = FeatureEngine().calculate(
        __import__("app.domain.models", fromlist=["MarketSnapshot"]).MarketSnapshot(
            con_id=1, timestamp=__import__("time").time(),
            last=Decimal("120"), bid=Decimal("119.9"), ask=Decimal("120.1"),
            closes=(Decimal("100"), Decimal("105"), Decimal("110"), Decimal("115"), Decimal("120")),
        ),
        [{"close": str(x)} for x in [100, 105, 110, 115, 120]],
    )
    assert features["trend"] > 0
    assert features["momentum"] > 0


def test_regime_is_high_vol_when_volatility_is_high() -> None:
    regime = RegimeEngine().detect({"trend": Decimal("0"), "momentum": Decimal("0"), "volatility": Decimal("12")})
    assert regime == "crisis/event"
