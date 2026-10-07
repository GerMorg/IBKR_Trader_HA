from __future__ import annotations

import csv
import json
from pathlib import Path
import time
from typing import Any


class AustrianTaxLedger:
    """Technical transaction ledger; not tax advice."""

    def __init__(self, db: Any, directory: str) -> None:
        self.db = db
        self.directory = Path(directory)

    def record_fill(self, fill: dict[str, Any]) -> None:
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS tax_events
               (id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at REAL NOT NULL, payload_json TEXT NOT NULL)"""
        )
        self.db.execute(
            "INSERT INTO tax_events(captured_at,payload_json) VALUES(?,?)",
            (time.time(), json.dumps(fill, default=str, sort_keys=True)),
        )

    def report(self, year: int) -> dict[str, Any]:
        start = time.mktime((year, 1, 1, 0, 0, 0, 0, 0, -1))
        end = time.mktime((year + 1, 1, 1, 0, 0, 0, 0, 0, -1))
        rows = self.db.query(
            "SELECT captured_at,payload_json FROM tax_events WHERE captured_at>=? AND captured_at<? ORDER BY captured_at",
            (start, end),
        )
        events = [json.loads(row["payload_json"]) for row in rows]
        self.directory.mkdir(parents=True, exist_ok=True)
        json_path = self.directory / f"ibkr_tax_{year}.json"
        csv_path = self.directory / f"ibkr_tax_{year}.csv"
        json_path.write_text(json.dumps({"year": year, "events": events}, default=str, indent=2), encoding="utf-8")
        keys = sorted({key for item in events for key in item})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys or ["timestamp"])
            writer.writeheader()
            writer.writerows(events)
        return {"year": year, "events": len(events), "json": str(json_path), "csv": str(csv_path), "status": "READY_FOR_REVIEW"}
