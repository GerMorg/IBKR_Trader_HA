from __future__ import annotations

from decimal import Decimal
import json
import time
from typing import Any


class LearningEngine:
    def __init__(self, db: Any, config: Any, audit: Any) -> None:
        self.db = db
        self.config = config
        self.audit = audit
        self.status = "INITIALIZING"
        self.model_version = "baseline-0.1"

    def record_decision(self, decision: Any, cycle_id: str) -> None:
        self.db.learning_sample(
            decision.decision_id,
            decision.decision_id,
            {
                "cycle_id": cycle_id,
                "con_id": decision.instrument.contract.con_id,
                "asset_class": decision.instrument.asset_class.value,
                "confidence": str(decision.signal.confidence),
                "net_edge_bps": str(decision.signal.net_edge_bps),
                "features": {k: str(v) for k, v in decision.signal.feature_snapshot.items()},
                "action": decision.action.value,
                "target_position": str(decision.target_position),
            },
        )

    def record_order(self, decision_id: str, result: dict[str, Any]) -> None:
        row = self.db.one(
            "SELECT sample_id,payload_json FROM learning_samples WHERE decision_id=? ORDER BY created_at DESC LIMIT 1",
            (decision_id,),
        )
        if not row:
            return
        payload = json.loads(row["payload_json"])
        payload["execution"] = result
        self.db.execute(
            "UPDATE learning_samples SET payload_json=? WHERE sample_id=?",
            (json.dumps(payload, default=str, sort_keys=True), row["sample_id"]),
        )

    def record_fill(self, decision_id: str, fill: dict[str, Any]) -> None:
        row = self.db.one(
            "SELECT sample_id,payload_json FROM learning_samples WHERE decision_id=? ORDER BY created_at DESC LIMIT 1",
            (decision_id,),
        )
        if not row:
            return
        payload = json.loads(row["payload_json"])
        payload.setdefault("fills", []).append(fill)
        self.db.execute(
            "UPDATE learning_samples SET payload_json=? WHERE sample_id=?",
            (json.dumps(payload, default=str, sort_keys=True), row["sample_id"]),
        )

    @staticmethod
    def brier(pairs: list[tuple[float, bool]]) -> float:
        if not pairs:
            return 1.0
        return sum((p - float(y)) ** 2 for p, y in pairs) / len(pairs)

    def recalibrate(self) -> dict[str, Any]:
        if not self.config.learning_enabled:
            self.status = "DISABLED"
            return {"status": self.status}
        rows = self.db.query(
            "SELECT payload_json FROM learning_samples WHERE outcome_status='SETTLED' ORDER BY settled_at",
        )
        if len(rows) < self.config.learning_min_samples:
            self.status = "INSUFFICIENT_DATA"
            return {"status": self.status, "samples": len(rows)}
        pairs: list[tuple[float, bool]] = []
        for row in rows:
            data = json.loads(row["payload_json"])
            if "confidence" in data and "success" in data:
                pairs.append((float(data["confidence"]), bool(data["success"])))
        if len(pairs) < self.config.learning_min_samples:
            self.status = "INSUFFICIENT_DATA"
            return {"status": self.status, "samples": len(pairs)}
        cut = max(1, int(len(pairs) * (1 - self.config.learning_validation_fraction)))
        train, validation = pairs[:cut], pairs[cut:]
        if not validation:
            self.status = "INSUFFICIENT_DATA"
            return {"status": self.status}
        base = self.brier(validation)
        best_scale = 1.0
        best = base
        for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
            score = self.brier([(max(0.0, min(1.0, p * scale)), y) for p, y in validation])
            if score < best:
                best = score
                best_scale = scale
        improvement = base - best
        candidate = f"confidence-scale-{int(time.time())}"
        if improvement >= self.config.learning_min_improvement and self.config.learning_auto_promotion:
            params = {"confidence_scale": best_scale, "train_samples": len(train), "validation_samples": len(validation)}
            self.db.execute(
                "INSERT OR REPLACE INTO model_versions(version,parent_version,status,parameters_json,metrics_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    candidate, self.model_version, "ACTIVE", json.dumps(params),
                    json.dumps({"base_brier": base, "validation_brier": best, "improvement": improvement}),
                    time.time(),
                ),
            )
            self.model_version = candidate
            self.status = "PROMOTED"
        else:
            self.status = "STABLE"
        return {
            "status": self.status,
            "samples": len(pairs),
            "base_brier": base,
            "validation_brier": best,
            "improvement": improvement,
            "model_version": self.model_version,
        }

    def settle_execution(self, decision_id: str, success: bool) -> None:
        row = self.db.one(
            "SELECT sample_id,payload_json FROM learning_samples WHERE decision_id=? ORDER BY created_at DESC LIMIT 1",
            (decision_id,),
        )
        if not row:
            return
        payload = json.loads(row["payload_json"])
        payload["success"] = bool(success)
        self.db.execute(
            "UPDATE learning_samples SET outcome_status='SETTLED',payload_json=?,settled_at=? WHERE sample_id=?",
            (json.dumps(payload, default=str, sort_keys=True), time.time(), row["sample_id"]),
        )
