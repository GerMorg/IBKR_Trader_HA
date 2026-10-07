from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterator


class Database:
    def __init__(self, path: str = ":memory:", schema_path: str | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        if path != ":memory:":
            self.connection.execute("PRAGMA journal_mode=WAL")
        schema_file = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
        with self.transaction() as conn:
            conn.executescript(schema_file.read_text(encoding="utf-8"))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.transaction() as conn:
            return conn.execute(sql, params)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self.connection.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def event(self, code: str, level: str, payload: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO app_events(ts,code,level,payload_json) VALUES(?,?,?,?)",
            (time.time(), code, level, json.dumps(payload, default=str, sort_keys=True)),
        )

    def start_cycle(self, cycle_id: str, config_hash: str) -> None:
        self.execute(
            "INSERT INTO cycles(cycle_id,started_at,status,config_hash) VALUES(?,?,?,?)",
            (cycle_id, time.time(), "RUNNING", config_hash),
        )

    def finish_cycle(self, cycle_id: str, status: str, blocker: str = "") -> None:
        self.execute(
            "UPDATE cycles SET finished_at=?,status=?,blocker=? WHERE cycle_id=?",
            (time.time(), status, blocker, cycle_id),
        )

    def save_instruments(self, instruments: list[Any]) -> None:
        rows = []
        for item in instruments:
            rows.append(
                (
                    item.contract.con_id,
                    item.symbol,
                    item.contract.local_symbol,
                    item.asset_class.value,
                    json.dumps(asdict(item.contract), default=str, sort_keys=True),
                    json.dumps(asdict(item.capability), default=str, sort_keys=True),
                    item.sector,
                    item.industry,
                    time.time(),
                )
            )
        with self.transaction() as conn:
            conn.executemany(
                """INSERT INTO instruments
                   (con_id,symbol,local_symbol,asset_class,contract_json,capability_json,sector,industry,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(con_id) DO UPDATE SET
                     symbol=excluded.symbol, local_symbol=excluded.local_symbol,
                     asset_class=excluded.asset_class, contract_json=excluded.contract_json,
                     capability_json=excluded.capability_json, sector=excluded.sector,
                     industry=excluded.industry, updated_at=excluded.updated_at""",
                rows,
            )

    def save_market(self, snapshot: Any) -> None:
        self.execute(
            "INSERT OR IGNORE INTO market_snapshots(con_id,captured_at,payload_json) VALUES(?,?,?)",
            (snapshot.con_id, snapshot.timestamp, json.dumps(asdict(snapshot), default=str, sort_keys=True)),
        )

    def save_news(self, item: Any) -> None:
        self.execute(
            "INSERT OR REPLACE INTO news_items(news_id,published_at,payload_json) VALUES(?,?,?)",
            (item.news_id, item.published_at, json.dumps(asdict(item), default=str, sort_keys=True)),
        )

    def save_decision(self, cycle_id: str, decision: Any) -> None:
        self.execute(
            """INSERT INTO decisions
               (decision_id,cycle_id,con_id,action,target_position,confidence,net_edge_bps,payload_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                decision.decision_id,
                cycle_id,
                decision.instrument.contract.con_id,
                decision.action.value,
                str(decision.target_position),
                str(decision.signal.confidence),
                str(decision.signal.net_edge_bps),
                json.dumps(asdict(decision), default=str, sort_keys=True),
                decision.created_at,
            ),
        )

    def save_intent(self, intent: Any) -> bool:
        try:
            self.execute(
                """INSERT INTO order_intents
                   (intent_id,idempotency_key,decision_id,con_id,state,payload_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    intent.intent_id,
                    intent.idempotency_key,
                    intent.decision_id,
                    intent.con_id,
                    intent.state.value,
                    json.dumps(asdict(intent), default=str, sort_keys=True),
                    intent.created_at,
                    time.time(),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def intent_exists(self, key: str) -> bool:
        return self.one(
            "SELECT intent_id FROM order_intents WHERE idempotency_key=?",
            (key,),
        ) is not None

    def update_intent_state(self, intent_id: str, state: str) -> None:
        self.execute(
            "UPDATE order_intents SET state=?,updated_at=? WHERE intent_id=?",
            (state, time.time(), intent_id),
        )

    def save_order(self, broker_order_id: int, intent: Any, payload: dict[str, Any], state: str) -> None:
        self.execute(
            """INSERT INTO orders
               (broker_order_id,intent_id,con_id,state,payload_json,submitted_at,updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(broker_order_id) DO UPDATE SET
                 state=excluded.state,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
            (
                broker_order_id,
                intent.intent_id,
                intent.con_id,
                state,
                json.dumps(payload, default=str, sort_keys=True),
                time.time(),
                time.time(),
            ),
        )

    def save_execution(self, fill: Any) -> None:
        self.execute(
            """INSERT OR REPLACE INTO executions
               (execution_id,broker_order_id,con_id,payload_json,captured_at)
               VALUES(?,?,?,?,?)""",
            (
                fill.execution_id,
                fill.broker_order_id,
                fill.con_id,
                json.dumps(asdict(fill), default=str, sort_keys=True),
                fill.timestamp,
            ),
        )

    def save_portfolio(self, state: Any) -> None:
        self.execute(
            "INSERT INTO portfolio_snapshots(captured_at,payload_json) VALUES(?,?)",
            (state.source_timestamp, json.dumps(asdict(state), default=str, sort_keys=True)),
        )

    def risk_event(self, cycle_id: str, con_id: int | None, result: Any) -> None:
        self.execute(
            "INSERT INTO risk_events(cycle_id,con_id,reason,checks_json,created_at) VALUES(?,?,?,?,?)",
            (
                cycle_id,
                con_id,
                result.reason,
                json.dumps(result.checks, sort_keys=True),
                time.time(),
            ),
        )

    def learning_sample(
        self,
        sample_id: str,
        decision_id: str,
        payload: dict[str, Any],
        status: str = "OPEN",
    ) -> None:
        self.execute(
            """INSERT OR REPLACE INTO learning_samples
               (sample_id,decision_id,outcome_status,payload_json,created_at,settled_at)
               VALUES(?,?,?,?,?,?)""",
            (
                sample_id,
                decision_id,
                status,
                json.dumps(payload, default=str, sort_keys=True),
                time.time(),
                None,
            ),
        )

    def set_recovery(self, state: str, detail: str) -> None:
        self.execute(
            """INSERT INTO recovery_markers(key,state,detail,updated_at)
               VALUES('global',?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 state=excluded.state,detail=excluded.detail,updated_at=excluded.updated_at""",
            (state, detail, time.time()),
        )

    def recovery_state(self) -> dict[str, Any] | None:
        return self.one("SELECT state,detail,updated_at FROM recovery_markers WHERE key='global'")

    def close(self) -> None:
        with self._lock:
            self.connection.close()
