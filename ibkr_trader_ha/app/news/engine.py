from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from defusedxml import ElementTree
from email.utils import parsedate_to_datetime
from decimal import Decimal
import hashlib
import re
import time
from typing import Any
from urllib.request import Request, urlopen

from app.domain.models import NewsFeature


@dataclass(frozen=True)
class RawNews:
    source: str
    url: str
    title: str
    summary: str
    published_at: float


class NewsEngine:
    SOURCES = (
        ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
        ("European Central Bank", "https://www.ecb.europa.eu/rss/press.html"),
        ("SEC", "https://www.sec.gov/news/pressreleases.rss"),
    )
    POSITIVE = {"growth", "surge", "rally", "approval", "easing", "cut", "record", "profit", "upgrade", "expansion"}
    NEGATIVE = {"fraud", "hack", "ban", "lawsuit", "crisis", "collapse", "sanction", "war", "recession", "loss", "downgrade", "default"}
    ALIASES = {
        "AAPL": {"apple"}, "MSFT": {"microsoft"}, "NVDA": {"nvidia"}, "AMZN": {"amazon"},
        "GOOGL": {"google", "alphabet"}, "META": {"meta", "facebook"}, "TSLA": {"tesla"},
        "BTC": {"bitcoin", "btc"}, "ETH": {"ethereum", "eth"}, "EUR": {"euro", "ecb"},
        "USD": {"dollar", "federal reserve", "fed"}, "GOLD": {"gold"},
    }
    SECTOR_WORDS = {
        "TECHNOLOGY": {"software", "semiconductor", "chip", "technology"},
        "FINANCIAL": {"bank", "banks", "credit", "financial"},
        "ENERGY": {"oil", "gas", "energy", "opec"},
        "HEALTHCARE": {"drug", "pharma", "healthcare", "medical"},
        "INDUSTRIAL": {"manufacturing", "industrial", "factory"},
    }

    def __init__(self, db: Any, refresh_minutes: int = 10, timeout_seconds: int = 10) -> None:
        self.db = db
        self.refresh_seconds = max(60, int(refresh_minutes) * 60)
        self.timeout_seconds = max(3, min(30, int(timeout_seconds)))
        self._cache: list[NewsFeature] = []
        self._last_fetch = 0.0
        self.status = "UNKNOWN"

    def collect(self) -> list[NewsFeature]:
        if self._cache and time.monotonic() - self._last_fetch < self.refresh_seconds:
            self.status = "CACHED"
            return list(self._cache)
        rows: list[RawNews] = []
        with ThreadPoolExecutor(max_workers=len(self.SOURCES)) as pool:
            futures = [pool.submit(self._fetch, source, url) for source, url in self.SOURCES]
            for future in as_completed(futures):
                try:
                    rows.extend(future.result())
                except Exception:
                    self.status = "DEGRADED"
        features = [self._classify(row) for row in rows]
        for feature in features:
            self.db.save_news(feature)
        if features:
            self._cache = sorted(features, key=lambda x: x.published_at, reverse=True)
            self._last_fetch = time.monotonic()
            self.status = "OK"
        elif self._cache:
            self.status = "STALE"
        else:
            self.status = "UNAVAILABLE"
        return list(self._cache)

    def effect_for(self, instrument: Any, items: list[NewsFeature]) -> Decimal:
        symbol = instrument.symbol.upper()
        sector = instrument.sector.upper()
        total = Decimal("0")
        for item in items:
            matched = symbol in item.affected_assets or bool(set(item.affected_sectors) & {sector})
            if not item.affected_assets and not item.affected_sectors:
                matched = True
            if matched:
                total += item.active_impact_bps
        return max(Decimal("-120"), min(Decimal("120"), total))

    def _fetch(self, source: str, url: str) -> list[RawNews]:
        with urlopen(Request(url, headers={"User-Agent": "IBKR-Trader-HA/0.1"}), timeout=self.timeout_seconds) as response:  # nosec B310
            root = ElementTree.fromstring(response.read())
        output: list[RawNews] = []
        for item in root.findall(".//item")[:40]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or url).strip()
            summary = re.sub(r"<[^>]+>", " ", (item.findtext("description") or "").strip())
            raw_date = (item.findtext("pubDate") or "").strip()
            try:
                published = parsedate_to_datetime(raw_date).timestamp()
            except Exception:
                published = time.time()
            if title:
                output.append(RawNews(source, link, title, summary, published))
        return output

    def _classify(self, item: RawNews) -> NewsFeature:
        text = f"{item.title} {item.summary}"
        low = text.lower()
        pos = sum(bool(re.search(r"\b" + re.escape(word) + r"\b", low)) for word in self.POSITIVE)
        neg = sum(bool(re.search(r"\b" + re.escape(word) + r"\b", low)) for word in self.NEGATIVE)
        score = Decimal(pos - neg)
        sentiment = max(Decimal("-1"), min(Decimal("1"), score / Decimal("4")))
        impact = max(Decimal("-60"), min(Decimal("60"), score * Decimal("12")))
        assets = tuple(symbol for symbol, aliases in self.ALIASES.items() if any(alias in low for alias in aliases))
        sectors = tuple(
            sector for sector, words in self.SECTOR_WORDS.items()
            if any(word in low for word in words)
        )
        digest = hashlib.sha256(f"{item.source}|{item.title}|{item.url}".encode()).hexdigest()
        return NewsFeature(
            news_id=digest[:32],
            source=item.source,
            published_at=item.published_at,
            title=item.title,
            affected_assets=assets,
            affected_sectors=sectors,
            sentiment=sentiment,
            impact_bps=impact,
            confidence=Decimal("0.75"),
            decay=Decimal("1"),
        )
