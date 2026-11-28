"""Tamper-evident SQLite WAL hash-chained audit ledger with MVCC read-bypass."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from filelock import FileLock

from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor
from smartrx_safety_agents.models.audit import AuditEventRecord
from smartrx_safety_agents.models.clinical import ActionType, RiskGrade

_GENESIS_HASH = "0" * 64
_SCHEMA_VERSION = 1


def _compute_row_hash(
    *,
    prev_row_hash: str,
    plan_id: str,
    idempotency_key: str,
    patient_token: str,
    agent_name: str,
    model_version: str,
    action_type: str,
    risk_grade: str,
    quarantined: int,
    hitl_override_reason: str | None,
    payload_json: str,
    created_at: str,
) -> str:
    canonical = "|".join(
        (
            prev_row_hash,
            plan_id,
            idempotency_key,
            patient_token,
            agent_name,
            model_version,
            action_type,
            risk_grade,
            str(quarantined),
            hitl_override_reason or "",
            payload_json,
            created_at,
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLedger:
    """Append-only SQLite WAL audit store with per-operation FileLock writes."""

    def __init__(
        self,
        db_path: Path,
        *,
        filelock_timeout_sec: float = 10.0,
    ) -> None:
        self._db_path = db_path
        self._lock_path = Path(f"{db_path}.lock")
        self._filelock_timeout_sec = filelock_timeout_sec
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _initialize_schema(self) -> None:
        with FileLock(str(self._lock_path), timeout=self._filelock_timeout_sec):
            conn = self._connect()
            try:
                version = int(conn.execute("PRAGMA user_version;").fetchone()[0])
                if version < _SCHEMA_VERSION:
                    with conn:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS audit_events (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                plan_id TEXT UNIQUE NOT NULL,
                                idempotency_key TEXT UNIQUE NOT NULL,
                                patient_token TEXT NOT NULL,
                                agent_name TEXT NOT NULL,
                                model_version TEXT NOT NULL,
                                action_type TEXT NOT NULL,
                                risk_grade TEXT NOT NULL,
                                quarantined INTEGER NOT NULL,
                                hitl_override_reason TEXT,
                                payload_json TEXT NOT NULL,
                                prev_row_hash TEXT NOT NULL,
                                row_hash TEXT NOT NULL,
                                created_at TEXT NOT NULL
                            );
                            """
                        )
                        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION};")
            finally:
                conn.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AuditEventRecord:
        return AuditEventRecord(
            event_id=int(row["id"]),
            plan_id=str(row["plan_id"]),
            idempotency_key=str(row["idempotency_key"]),
            patient_token=str(row["patient_token"]),
            agent_name=str(row["agent_name"]),
            model_version=str(row["model_version"]),
            action_type=cast(ActionType, str(row["action_type"])),
            risk_grade=RiskGrade(str(row["risk_grade"])),
            quarantined=bool(row["quarantined"]),
            hitl_override_reason=(
                str(row["hitl_override_reason"])
                if row["hitl_override_reason"] is not None
                else None
            ),
            payload_json=str(row["payload_json"]),
            prev_row_hash=str(row["prev_row_hash"]),
            row_hash=str(row["row_hash"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def record_event(
        self,
        *,
        plan_id: str,
        idempotency_key: str,
        patient_token: str,
        agent_name: str,
        model_version: str,
        action_type: ActionType,
        risk_grade: RiskGrade,
        quarantined: bool,
        payload_json: str,
        hitl_override_reason: str | None = None,
        known_phi: tuple[str, ...] = (),
        created_at: datetime | None = None,
    ) -> AuditEventRecord:
        """Append a hash-chained audit row after enforcing zero-PHI checks."""
        for text_field in (patient_token, payload_json, hitl_override_reason or ""):
            if PHIRedactor.contains_phi(text_field, known_identifiers=known_phi):
                raise ValueError("PHI detected in audit ledger payload; persistence blocked.")

        existing = self.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        timestamp = (created_at or datetime.now(UTC)).isoformat()
        with FileLock(str(self._lock_path), timeout=self._filelock_timeout_sec):
            conn = self._connect()
            try:
                dup = conn.execute(
                    "SELECT * FROM audit_events WHERE idempotency_key = ?;",
                    (idempotency_key,),
                ).fetchone()
                if dup is not None:
                    return self._row_to_record(dup)

                last_row = conn.execute(
                    "SELECT row_hash FROM audit_events ORDER BY id DESC LIMIT 1;"
                ).fetchone()
                prev_hash = str(last_row["row_hash"]) if last_row is not None else _GENESIS_HASH
                q_int = 1 if quarantined else 0
                row_hash = _compute_row_hash(
                    prev_row_hash=prev_hash,
                    plan_id=plan_id,
                    idempotency_key=idempotency_key,
                    patient_token=patient_token,
                    agent_name=agent_name,
                    model_version=model_version,
                    action_type=action_type,
                    risk_grade=risk_grade.value,
                    quarantined=q_int,
                    hitl_override_reason=hitl_override_reason,
                    payload_json=payload_json,
                    created_at=timestamp,
                )
                with conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO audit_events (
                            plan_id, idempotency_key, patient_token, agent_name,
                            model_version, action_type, risk_grade, quarantined,
                            hitl_override_reason, payload_json, prev_row_hash,
                            row_hash, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            plan_id,
                            idempotency_key,
                            patient_token,
                            agent_name,
                            model_version,
                            action_type,
                            risk_grade.value,
                            q_int,
                            hitl_override_reason,
                            payload_json,
                            prev_hash,
                            row_hash,
                            timestamp,
                        ),
                    )
                    inserted_id = cursor.lastrowid
                inserted = conn.execute(
                    "SELECT * FROM audit_events WHERE id = ?;", (inserted_id,)
                ).fetchone()
                return self._row_to_record(inserted)
            finally:
                conn.close()

    def get_by_idempotency_key(self, idempotency_key: str) -> AuditEventRecord | None:
        """Read an audit event by idempotency key via SQLite MVCC (no FileLock)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM audit_events WHERE idempotency_key = ?;",
                (idempotency_key,),
            ).fetchone()
            return self._row_to_record(row) if row is not None else None
        finally:
            conn.close()

    def get_events(self, *, limit: int = 100) -> tuple[AuditEventRecord, ...]:
        """Read audit events via SQLite MVCC without acquiring FileLock."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY id ASC LIMIT ?;",
                (limit,),
            ).fetchall()
            return tuple(self._row_to_record(row) for row in rows)
        finally:
            conn.close()

    def verify_chain_integrity(self) -> bool:
        """Verify SHA-256 hash chain linkage across all persisted audit rows."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM audit_events ORDER BY id ASC;").fetchall()
        finally:
            conn.close()

        expected_prev = _GENESIS_HASH
        for row in rows:
            if str(row["prev_row_hash"]) != expected_prev:
                return False
            recomputed = _compute_row_hash(
                prev_row_hash=expected_prev,
                plan_id=str(row["plan_id"]),
                idempotency_key=str(row["idempotency_key"]),
                patient_token=str(row["patient_token"]),
                agent_name=str(row["agent_name"]),
                model_version=str(row["model_version"]),
                action_type=str(row["action_type"]),
                risk_grade=str(row["risk_grade"]),
                quarantined=int(row["quarantined"]),
                hitl_override_reason=(
                    str(row["hitl_override_reason"])
                    if row["hitl_override_reason"] is not None
                    else None
                ),
                payload_json=str(row["payload_json"]),
                created_at=str(row["created_at"]),
            )
            if str(row["row_hash"]) != recomputed:
                return False
            expected_prev = recomputed
        return True

    def checkpoint(self, mode: Literal["PASSIVE", "TRUNCATE"] = "PASSIVE") -> None:
        """Execute a WAL checkpoint under write FileLock."""
        with FileLock(str(self._lock_path), timeout=self._filelock_timeout_sec):
            conn = self._connect()
            try:
                conn.execute(f"PRAGMA wal_checkpoint({mode});")
            finally:
                conn.close()
