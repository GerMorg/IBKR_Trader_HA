from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


class SensorPublisher:
    def __init__(self, enabled: bool, supervisor_token: str | None = None) -> None:
        self.enabled = enabled
        self.supervisor_token = supervisor_token or os.getenv("SUPERVISOR_TOKEN", "")
        self.last_state: dict[str, Any] = {}

    def publish(self, values: dict[str, Any]) -> dict[str, Any]:
        self.last_state = dict(values)
        if not self.enabled or not self.supervisor_token:
            return {"published": False, "reason": "HA_API_UNAVAILABLE"}
        results = {}
        for name, state in self._sensor_map(values).items():
            results[name] = self._publish_one(name, state)
        return {"published": True, "results": results}

    def _publish_one(self, name: str, state: Any) -> bool:
        payload = json.dumps({"state": str(state)}).encode("utf-8")
        request = urllib.request.Request(
            f"http://supervisor/core/api/states/sensor.ibkr_trader_{name}",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.supervisor_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
                return 200 <= response.status < 300
        except Exception:
            return False

    @staticmethod
    def _sensor_map(values: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": values.get("status", "UNKNOWN"),
            "connection": values.get("connection", "UNKNOWN"),
            "equity": values.get("equity", "0"),
            "cash": values.get("cash", "0"),
            "buying_power": values.get("buying_power", "0"),
            "margin_used": values.get("margin_used", "0"),
            "daily_pnl": values.get("daily_pnl", "0"),
            "gross_exposure": values.get("gross_exposure", "0"),
            "net_exposure": values.get("net_exposure", "0"),
            "positions": values.get("positions", "0"),
            "cycle": values.get("cycle", ""),
            "discovered": values.get("discovered", "0"),
            "candidates": values.get("candidates", "0"),
            "analyzed": values.get("analyzed", "0"),
            "approved": values.get("approved", "0"),
            "blocked": values.get("blocked", "0"),
            "last_order": values.get("last_order", ""),
            "risk": values.get("risk", "UNKNOWN"),
            "regime": values.get("regime", "UNKNOWN"),
            "news": values.get("news", "UNKNOWN"),
            "gemini": values.get("gemini", "UNKNOWN"),
            "learning": values.get("learning", "UNKNOWN"),
        }
