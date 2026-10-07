from app.persistence import Database
from app.recovery import RecoveryManager
from app.monitoring import AuditLogger


def test_recovery_persists_until_cleared() -> None:
    db = Database(":memory:")
    recovery = RecoveryManager(db, AuditLogger(False))
    recovery.require("ORDER_STATE_UNKNOWN:42")
    assert recovery.check() is False
    persisted = db.recovery_state()
    assert persisted is not None
    assert persisted["state"] == "RECOVERY_REQUIRED"
    recovery.clear()
    assert recovery.check() is True
    assert db.recovery_state()["state"] == "CLEAR"


def test_recovery_heartbeat_timeout(monkeypatch) -> None:
    db = Database(":memory:")
    recovery = RecoveryManager(db, AuditLogger(False))
    import app.recovery.manager as module
    monkeypatch.setattr(module.time, "time", lambda: 1000.0)
    assert recovery.heartbeat_timeout(900, 50) is True
    assert recovery.heartbeat_timeout(970, 50) is False
