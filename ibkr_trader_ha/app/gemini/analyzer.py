from __future__ import annotations

from decimal import Decimal
import json
from typing import Any

from pydantic import BaseModel, Field


class GeminiResult(BaseModel):
    sentiment_adjustment_bps: float = Field(default=0, ge=-50, le=50)
    regime_bias: float = Field(default=0, ge=-1, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    rationale: str = ""


class GeminiAnalyzer:
    def __init__(self, api_key: str, model: str, enabled: bool, timeout_seconds: int, audit: Any) -> None:
        self.api_key = api_key
        self.model = model
        self.enabled = enabled
        self.timeout_seconds = int(timeout_seconds)
        self.audit = audit
        self.status = "DISABLED"
        self.last_model = ""

    def analyze(self, instrument: Any, features: dict[str, Decimal], news_impact_bps: Decimal, regime: str) -> dict[str, Any]:
        if not self.enabled or not self.api_key:
            self.status = "DISABLED"
            return {"status": "DISABLED", "effect_bps": Decimal("0"), "confidence": Decimal("0")}
        try:
            from google import genai
        except ImportError:
            self.status = "UNAVAILABLE"
            return {"status": "UNAVAILABLE", "effect_bps": Decimal("0"), "confidence": Decimal("0")}

        prompt = (
            "You are a research analyst. Never issue an order, sizing, leverage or risk override. "
            "Return JSON only. Interpret market regime and news context for this instrument. "
            + json.dumps({
                "symbol": instrument.symbol,
                "asset_class": instrument.asset_class.value,
                "features": {k: str(v) for k, v in features.items()},
                "news_impact_bps": str(news_impact_bps),
                "regime": regime,
            }, sort_keys=True)
        )
        try:
            client = genai.Client(api_key=self.api_key)
            response = client.interactions.create(
                model=self.model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": GeminiResult.model_json_schema(),
                },
                store=False,
            )
            parsed = GeminiResult.model_validate_json(response.output_text)
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
            self.audit.emit("GEMINI_UNAVAILABLE", "WARNING", error=type(exc).__name__)
            return {"status": "DEGRADED", "effect_bps": Decimal("0"), "confidence": Decimal("0"), "reason": type(exc).__name__}
