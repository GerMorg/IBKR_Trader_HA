from __future__ import annotations

import time
from typing import Any


class RecoveryManager:
    def __init__(self, db: Any, audit: Any) -> None:
        self.db = db
        self.audit = audit
        self.required = False
        self.reason = ""

    def require(self, reason: str) -> None:
        self.required = True
        self.reason = reason
        self.db.set_recovery("RECOVERY_REQUIRED", reason)
        self.audit.emit("RECOVERY_REQUIRED", "ERROR", reason=reason)

    def clear(self) -> None:
        self.required = False
        self.reason = ""
        self.db.set_recovery("CLEAR", "")
        self.audit.emit("RECOVERY_CLEARED", "INFO")

    def check(self) -> bool:
        return not self.required

    def mark_reconnect(self, detail: str) -> None:
        self.db.set_recovery("RECONNECTING", detail)
        self.audit.emit("IBKR_RECONNECT", "WARNING", detail=detail)

    def heartbeat_timeout(self, last_seen: float, timeout: float) -> bool:
        return time.time() - last_seen > timeout
