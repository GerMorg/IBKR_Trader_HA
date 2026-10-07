from decimal import Decimal
import time

from app.news import NewsEngine


def test_news_classification_and_mapping() -> None:
    engine = NewsEngine(__import__("app.persistence", fromlist=["Database"]).Database(":memory:"))
    item = engine._classify(type("R", (), {
        "source": "SEC", "url": "u", "title": "Apple profit growth",
        "summary": "Technology expansion", "published_at": time.time()
    })())
    assert item.sentiment > 0
    assert "AAPL" in item.affected_assets
    assert "TECHNOLOGY" in item.affected_sectors


def test_gemini_without_key_is_safe(audit) -> None:
    from app.gemini import GeminiAnalyzer
    result = GeminiAnalyzer("", "gemini-2.5-flash", True, 5, audit).analyze(
        type("I", (), {"symbol": "TEST", "asset_class": type("A", (), {"value": "EQUITY"})()})(),
        {"trend": Decimal("1")}, Decimal("0"), "trend",
    )
    assert result["status"] == "DISABLED"
