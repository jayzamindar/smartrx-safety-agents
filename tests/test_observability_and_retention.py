"""Tests for OpenTelemetry observability, in-memory metrics, and JSONL retention."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smartrx_safety_agents.models.audit import AuditEventRecord
from smartrx_safety_agents.models.clinical import RiskGrade
from smartrx_safety_agents.observability import (
    InMemoryMetricsLedger,
    TelemetryManager,
    get_metrics_ledger,
    get_telemetry_manager,
    shutdown_telemetry,
    trace_span,
)
from smartrx_safety_agents.persistence.ledger import AuditLedger, JsonlAuditExporter


def _sample_record(
    *,
    event_id: int = 1,
    created_at: datetime | None = None,
) -> AuditEventRecord:
    ts = created_at or datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC)
    return AuditEventRecord(
        event_id=event_id,
        plan_id=f"plan-{event_id}",
        idempotency_key=f"idem-{event_id}",
        patient_token="pt_obs_test",
        agent_name="SafetyAuditorAgent",
        model_version="deterministic_clinical_v1",
        action_type="HOLD_PRESCRIPTION",
        risk_grade=RiskGrade.RED,
        quarantined=False,
        hitl_override_reason=None,
        payload_json='{"resourceType":"DetectedIssue"}',
        prev_row_hash="0" * 64,
        row_hash="a" * 64,
        created_at=ts,
    )


def test_in_memory_metrics_ledger_thread_safety() -> None:
    ledger = InMemoryMetricsLedger()

    def _worker() -> None:
        for _ in range(25):
            ledger.record_batch(
                resources_audited=2,
                alerts_flagged=1,
                quarantined_actions=1,
                escalations_triggered=1,
            )
            ledger.increment("custom.counter")
            ledger.record_latency("reconcile", 12.5)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = ledger.snapshot()
    assert snap["batches_processed"] == 100
    assert snap["resources_audited"] == 200
    assert snap["alerts_flagged"] == 100
    assert snap["quarantined_actions"] == 100
    assert snap["escalations_triggered"] == 100
    assert snap["counters"]["custom.counter"] == 100
    assert snap["latencies_ms"]["reconcile"]["count"] == 100
    assert snap["latencies_ms"]["reconcile"]["avg_ms"] == 12.5

    ledger.reset()
    assert ledger.snapshot()["batches_processed"] == 0


def test_trace_span_and_telemetry_shutdown() -> None:
    mgr = TelemetryManager()
    mock_tp = MagicMock()
    mock_mp = MagicMock()
    mgr._tracer_provider = mock_tp
    mgr._meter_provider = mock_mp

    with trace_span("clinical.reconcile", {"patient_token": "pt_1", "tier": 3}, manager=mgr):
        pass

    with pytest.raises(RuntimeError, match="boom"):
        with trace_span("clinical.fail", manager=mgr):
            raise RuntimeError("boom")

    snap = mgr.metrics_ledger.snapshot()
    assert snap["counters"]["clinical.reconcile.calls"] == 1
    assert snap["counters"]["clinical.fail.calls"] == 1
    assert snap["counters"]["clinical.fail.errors"] == 1
    assert snap["latencies_ms"]["clinical.reconcile"]["count"] == 1

    mgr.shutdown()
    mgr.shutdown()  # Idempotent second call
    assert mgr.is_shutdown is True
    mock_tp.shutdown.assert_called_once()
    mock_mp.shutdown.assert_called_once()

    # Singleton lifecycle & teardown
    singleton = get_telemetry_manager()
    assert get_metrics_ledger() is singleton.metrics_ledger
    shutdown_telemetry()
    assert singleton.is_shutdown is True


def test_jsonl_daily_export_rotation_and_retention_pruning(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit_logs"
    exporter = JsonlAuditExporter(
        audit_dir,
        max_file_bytes=450,
        max_retention_days=30,
        max_total_size_mb=1,
    )
    now = datetime(2026, 11, 27, 15, 0, 0, tzinfo=UTC)

    # Create an expired log (> 30 days old)
    old_date = (now - timedelta(days=35)).strftime("%Y-%m-%d")
    old_file = audit_dir / f"audit-{old_date}.jsonl"
    old_file.write_text('{"expired":true}\n', encoding="utf-8")

    # Export multiple records to trigger same-day rotation
    written_paths: list[Path] = []
    for idx in range(1, 5):
        p = exporter.export_event(_sample_record(event_id=idx, created_at=now), now=now)
        written_paths.append(p)

    assert not old_file.exists()
    assert (audit_dir / "audit-2026-11-27.jsonl").exists()
    assert any(p.name == "audit-2026-11-27.1.jsonl" for p in written_paths)

    # Verify UTF-8 JSONL contents
    first_line = (audit_dir / "audit-2026-11-27.jsonl").read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(first_line)
    assert parsed["plan_id"] == "plan-1"

    # Test total size cap pruning with 0MB cap (keeps only protected/newest)
    tight_exporter = JsonlAuditExporter(
        audit_dir,
        max_file_bytes=450,
        max_retention_days=30,
        max_total_size_mb=0,
    )
    removed = tight_exporter.prune_only(now=now)
    assert len(removed) >= 1


def test_audit_ledger_auto_exports_jsonl(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    audit_dir = tmp_path / "jsonl"
    ledger = AuditLedger(db_path, audit_log_dir=audit_dir)

    rec = ledger.record_event(
        plan_id="plan-jsonl-1",
        idempotency_key="idem-jsonl-1",
        patient_token="pt_jsonl",
        agent_name="SafetyAuditorAgent",
        model_version="deterministic_clinical_v1",
        action_type="HOLD_PRESCRIPTION",
        risk_grade=RiskGrade.RED,
        quarantined=False,
        payload_json='{"resourceType":"DetectedIssue"}',
        created_at=datetime(2026, 11, 27, 10, 0, 0, tzinfo=UTC),
    )
    assert rec.plan_id == "plan-jsonl-1"
    expected_jsonl = audit_dir / "audit-2026-11-27.jsonl"
    assert expected_jsonl.exists()
    assert "plan-jsonl-1" in expected_jsonl.read_text(encoding="utf-8")
