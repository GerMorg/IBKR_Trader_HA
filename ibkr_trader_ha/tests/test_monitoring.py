from app.monitoring.audit import _scrub


def test_audit_scrubs_secrets() -> None:
    value = _scrub({"api_key": "abc", "nested": {"token": "xyz"}, "name": "ok"})
    assert value["api_key"] == "***REDACTED***"
    assert value["nested"]["token"] == "***REDACTED***"
    assert value["name"] == "ok"
