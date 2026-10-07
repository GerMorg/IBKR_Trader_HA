from __future__ import annotations

from decimal import Decimal
import json
from typing import Any, Callable

from pydantic import BaseModel, Field


class GeminiResult(BaseModel):
    sentiment_adjustment_bps: float = Field(default=0, ge=-50, le=50)
    regime_bias: float = Field(default=0, ge=-1, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""


class GeminiAnalyzer:
    def __init__(
        self,
        api_key: str,
        model: str,
        enabled: bool,
        timeout_seconds: int,
        audit: Any,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.enabled = enabled
        self.timeout_seconds = int(timeout_seconds)
        self.audit = audit
        self.client_factory = client_factory
        self.status = "DISABLED"
        self.last_model = ""

    def analyze(
        self,
        instrument: Any,
        features: dict[str, Decimal],
        news_impact_bps: Decimal,
        regime: str,
    ) -> dict[str, Any]:
        if not self.enabled or not self.api_key:
            self.status = "DISABLED"
            return {
                "status": "DISABLED",
                "effect_bps": Decimal("0"),
                "confidence": Decimal("0"),
            }

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            self.status = "UNAVAILABLE"
            return {
                "status": "UNAVAILABLE",
                "effect_bps": Decimal("0"),
                "confidence": Decimal("0"),
            }

        prompt = (
            "You are a research analyst. Never issue an order, sizing, leverage "
            "or risk override. Return JSON only. Interpret market regime, "
            "instrument context and news for this instrument.\n"
            + json.dumps(
                {
                    "symbol": instrument.symbol,
                    "asset_class": instrument.asset_class.value,
                    "features": {key: str(value) for key, value in features.items()},
                    "news_impact_bps": str(news_impact_bps),
                    "regime": regime,
                },
                sort_keys=True,
            )
        )

        try:
            client = (
                self.client_factory(self.api_key)
                if self.client_factory
                else genai.Client(api_key=self.api_key)
            )
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiResult,
                ),
            )
            text = getattr(response, "text", "")
            parsed = GeminiResult.model_validate_json(text)
            self.last_model = self.model
            self.status = "OK"
            result = parsed.model_dump()
            return {
                "status": "OK",
                "effect_bps": Decimal(str(result["sentiment_adjustment_bps"])),
                "confidence": Decimal(str(result["confidence"])),
                "regime_bias": Decimal(str(result["regime_bias"])),
                "rationale": str(result["rationale"]),
                "model": self.model,
            }
        except Exception as exc:
            self.status = "DEGRADED"
            self.audit.emit(
                "GEMINI_UNAVAILABLE",
                "WARNING",
                error=type(exc).__name__,
            )
            return {
                "status": "DEGRADED",
                "effect_bps": Decimal("0"),
                "confidence": Decimal("0"),
                "reason": type(exc).__name__,
            }
