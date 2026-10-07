from pathlib import Path

from app.persistence import Database
from app.tax import AustrianTaxLedger


def test_austrian_technical_ledger_exports_json_and_csv(tmp_path: Path) -> None:
    db = Database(":memory:")
    ledger = AustrianTaxLedger(db, str(tmp_path))
    fill = {
        "execution_id": "exec-1",
        "timestamp": "2026-01-10T10:00:00+00:00",
        "asset_class": "EQUITY",
        "symbol": "TEST",
        "quantity": "2",
        "price": "100",
        "currency": "USD",
        "fees": "1",
        "realized_pnl": "20",
    }
    assert ledger.record_fill(fill) is True
    assert ledger.record_fill(fill) is False
    result = ledger.report(2026)
    assert result["events"] == 1
    assert Path(result["json"]).exists()
    assert Path(result["csv"]).exists()
