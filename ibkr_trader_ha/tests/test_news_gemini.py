from decimal import Decimal
import time

from app.gemini import GeminiAnalyzer
from app.monitoring import AuditLogger
from app.news import NewsEngine
from app.persistence import Database


def test_news_classification_and_mapping() -> None:
    engine = NewsEngine(Database(":memory:"))
    item = engine._classify(
        type(
            "R",
            (),
            {
                "source": "SEC",
                "url": "u",
                "title": "Apple profit growth",
                "summary": "Technology expansion",
                "published_at": time.time(),
            },
        )()
    )
    assert item.sentiment > 0
    assert "AAPL" in item.affected_assets
    assert "TECHNOLOGY" in item.affected_sectors


def test_gemini_without_key_is_safe() -> None:
    result = GeminiAnalyzer(
        "", "gemini-2.5-flash", True, 5, AuditLogger(False)
    ).analyze(
        type(
            "I",
            (),
            {
                "symbol": "TEST",
                "asset_class": type("A", (), {"value": "EQUITY"})(),
            },
        )(),
        {"trend": Decimal("1")},
        Decimal("0"),
        "trend",
    )
    assert result["status"] == "DISABLED"


def test_gemini_structured_output_is_validated() -> None:
    class Response:
        text = '{"sentiment_adjustment_bps": 12, "regime_bias": 0.2, "confidence": 0.8, "rationale": "positive"}'

    class Models:
        def generate_content(self, **kwargs):
            assert kwargs["config"].response_mime_type == "application/json"
            return Response()

    class Client:
        models = Models()

    analyzer = GeminiAnalyzer(
        "secret",
        "gemini-2.5-flash",
        True,
        5,
        AuditLogger(False),
        client_factory=lambda _: Client(),
    )
    result = analyzer.analyze(
        type(
            "I",
            (),
            {
                "symbol": "TEST",
                "asset_class": type("A", (), {"value": "EQUITY"})(),
            },
        )(),
        {"trend": Decimal("1")},
        Decimal("4"),
        "trend",
    )
    assert result["status"] == "OK"
    assert result["effect_bps"] == Decimal("12")
    assert result["confidence"] == Decimal("0.8")
