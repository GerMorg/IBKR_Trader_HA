from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from typing import Any


SECRET_WORDS = ("key", "secret", "token", "password", "authorization", "api_key", "api_secret")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): (
                "***REDACTED***"
                if any(word in str(k).lower() for word in SECRET_WORDS)
                else _scrub(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, tuple):
        return [_scrub(v) for v in value]
    text = str(value)
    for marker in ("Bearer ", "Basic "):
        if text.startswith(marker):
            return marker + "***REDACTED***"
    return value


class AuditLogger:
    def __init__(self, enabled: bool, path: str = "/data/logs/ibkr_trader.jsonl") -> None:
        self.enabled = enabled
        self.path = Path(path)
        self._lock = threading.RLock()

    def emit(self, code: str, level: str = "INFO", **payload: Any) -> None:
        record = {
            "ts": time.time(),
            "code": code,
            "level": level,
            "payload": _scrub(payload),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        print(line, flush=True)
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            return
