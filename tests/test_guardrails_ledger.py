"""Unit tests for deterministic guardrails, HMAC signing, and SQLite WAL audit ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from smartrx_safety_agents.guardrails import (
    GuardrailEngine,
    PlanVerificationError,
    verify_plan_signature,
)
from smartrx_safety_agents.models.clinical import (
    ClinicalAlert,
    NormalizedMedication,
    RiskGrade,
)
from smartrx_safety_agents.persistence import AuditLedger

_TEST_SECRET = "unit-test-super-strong-signing-secret-12345"  # noqa: S105


def _sample_med() -> NormalizedMedication:
    return NormalizedMedication(
        rxcui="11289",
        scd_name="warfarin 5 mg oral tablet",
        raw_name="warfarin",
        frequency="once daily",
        route="oral",
        is_nti=True,
    )


def _sample_alert() -> ClinicalAlert:
    return ClinicalAlert(
        alert_id="ddi-11289-703",
        rule_category="DDI",
        severity="major",
        risk_score=4,
        risk_grade=RiskGrade.RED,
        recommended_action="HOLD_PRESCRIPTION",
        affected_rxcuis=("11289", "703"),
        rationale="Major CYP2C9 interaction increasing bleeding risk.",
        citation="RxNorm:11289-703 | PMID:15640376",
        requires_npi_attestation=True,
    )


def test_unconditional_fhir_overwrite_and_dry_run() -> None:
    """Draft LLM payloads are unconditionally discarded and overwritten by FHIR R4 JSON."""
    engine = GuardrailEngine(signing_secret=_TEST_SECRET)
    draft_llm = {"shell_command": "rm -rf /", "wildcards": "*"}

    plan = engine.enforce(
        plan_id="plan-001",
        idempotency_key="idem-001",
        patient_token="pt_abc123",
        action_type="HOLD_PRESCRIPTION",
        risk_score=4,
        risk_grade=RiskGrade.RED,
        medications=(_sample_med(),),
        alerts=(_sample_alert(),),
        draft_execution_payload=draft_llm,
        dry_run=True,
    )

    assert "shell_command" not in plan.execution_payload
    assert plan.execution_payload["resourceType"] == "Bundle"
    assert plan.execution_payload["dryRun"] is True
    resource_types = {e["resource"]["resourceType"] for e in plan.execution_payload["entry"]}
    assert resource_types == {"MedicationRequest", "DetectedIssue", "Task"}
    assert any("Dry-run simulation mode" in step for step in plan.rollback_steps)
    assert verify_plan_signature(plan, _TEST_SECRET) is True


def test_invalid_action_type_quarantined_fail_closed() -> None:
    """Actions outside canonical ActionType allowlist are quarantined fail-closed."""
    engine = GuardrailEngine(signing_secret=_TEST_SECRET)

    plan = engine.enforce(
        plan_id="plan-bad-enum",
        idempotency_key="idem-bad-enum",
        patient_token="pt_abc123",
        action_type="EXECUTE_ARBITRARY_ORDER",
        risk_score=5,
        risk_grade=RiskGrade.RED,
    )

    assert plan.quarantined is True
    assert plan.quarantine_reason == "INVALID_ACTION_ENUM_TYPE"
    assert plan.action_type == "ESCALATE_TO_CLINICAL_PHARMACIST"


def test_hmac_verification_ttl_expiration_and_replay_defense() -> None:
    """Verify HMAC tampering, expired TTL (>=300s), and replayed plan_id rejection."""
    engine = GuardrailEngine(signing_secret=_TEST_SECRET)
    base_time = datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC)

    plan = engine.enforce(
        plan_id="plan-ttl-001",
        idempotency_key="idem-ttl-001",
        patient_token="pt_ttl",
        action_type="APPROVE_RECONCILED_LIST",
        risk_score=1,
        risk_grade=RiskGrade.GREEN,
        medications=(_sample_med(),),
        ttl_seconds=300,
        now=base_time,
    )

    # First verification succeeds within TTL
    engine.verify_plan(plan, now=base_time + timedelta(seconds=60))

    # Replay of same plan_id is rejected
    with pytest.raises(PlanVerificationError, match="Replayed plan_id"):
        engine.verify_plan(plan, now=base_time + timedelta(seconds=65))

    # Expired plan (current_time >= expires_at) is rejected
    with pytest.raises(PlanVerificationError, match="expired"):
        engine.verify_plan(plan, now=base_time + timedelta(seconds=300), check_replay=False)

    # Tampered payload fails HMAC verification
    tampered = plan.model_copy(update={"risk_score": 5})
    assert verify_plan_signature(tampered, _TEST_SECRET) is False
    with pytest.raises(PlanVerificationError, match="signature"):
        engine.verify_plan(tampered, now=base_time + timedelta(seconds=10), check_replay=False)


def test_idempotency_key_deduplication_returns_cached_plan() -> None:
    """Duplicate idempotency_key within TTL returns the exact cached sealed plan."""
    engine = GuardrailEngine(signing_secret=_TEST_SECRET)
    base_time = datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC)

    first = engine.enforce(
        plan_id="plan-idem-1",
        idempotency_key="idem-shared-key",
        patient_token="pt_idem",
        action_type="FLAG_DRUG_INTERACTION",
        risk_score=3,
        risk_grade=RiskGrade.YELLOW,
        now=base_time,
    )
    second = engine.enforce(
        plan_id="plan-idem-2",
        idempotency_key="idem-shared-key",
        patient_token="pt_idem",
        action_type="HOLD_PRESCRIPTION",
        risk_score=5,
        risk_grade=RiskGrade.RED,
        now=base_time + timedelta(seconds=30),
    )

    assert second == first


def test_production_secret_fail_closed() -> None:
    """Production environment with empty or weak secret must raise RuntimeError."""
    with pytest.raises(RuntimeError):
        GuardrailEngine(signing_secret="changeme", environment="production")


def test_audit_ledger_wal_hash_chain_and_tamper_detection(tmp_path: Path) -> None:
    """SQLite WAL ledger enforces hash-chaining, idempotency, and tamper detection."""
    db_path = tmp_path / "smartrx_ledger.db"
    ledger = AuditLedger(db_path)

    payload_1 = json.dumps({"action": "HOLD_PRESCRIPTION", "rxcui": "11289"})
    payload_2 = json.dumps({"action": "APPROVE_RECONCILED_LIST", "rxcui": "6809"})

    ev1 = ledger.record_event(
        plan_id="plan-1",
        idempotency_key="idem-1",
        patient_token="pt_111",
        agent_name="SafetyAgent",
        model_version="deterministic-v1",
        action_type="HOLD_PRESCRIPTION",
        risk_grade=RiskGrade.RED,
        quarantined=False,
        payload_json=payload_1,
    )
    ev1_dup = ledger.record_event(
        plan_id="plan-1-dup",
        idempotency_key="idem-1",
        patient_token="pt_111",
        agent_name="SafetyAgent",
        model_version="deterministic-v1",
        action_type="HOLD_PRESCRIPTION",
        risk_grade=RiskGrade.RED,
        quarantined=False,
        payload_json=payload_1,
    )
    assert ev1_dup.event_id == ev1.event_id

    ev2 = ledger.record_event(
        plan_id="plan-2",
        idempotency_key="idem-2",
        patient_token="pt_222",
        agent_name="LiaisonAgent",
        model_version="gemini-3.8-flash-high",
        action_type="APPROVE_RECONCILED_LIST",
        risk_grade=RiskGrade.GREEN,
        quarantined=False,
        hitl_override_reason="Verified by PharmD",
        payload_json=payload_2,
    )
    assert ev2.prev_row_hash == ev1.row_hash
    assert ledger.verify_chain_integrity() is True
    assert len(ledger.get_events()) == 2
    ledger.checkpoint("TRUNCATE")

    # Simulate direct SQLite tampering on row 1
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute(
                "UPDATE audit_events SET action_type = 'APPROVE_RECONCILED_LIST' WHERE id = 1;"
            )
    finally:
        conn.close()

    assert ledger.verify_chain_integrity() is False


def test_audit_ledger_blocks_phi_persistence(tmp_path: Path) -> None:
    """AuditLedger rejects any event containing unredacted PHI before SQLite commit."""
    ledger = AuditLedger(tmp_path / "phi_block.db")

    with pytest.raises(ValueError, match="PHI detected"):
        ledger.record_event(
            plan_id="plan-phi",
            idempotency_key="idem-phi",
            patient_token="pt_safe",
            agent_name="SafetyAgent",
            model_version="deterministic-v1",
            action_type="HOLD_PRESCRIPTION",
            risk_grade=RiskGrade.RED,
            quarantined=False,
            payload_json=json.dumps({"note": "SSN 123-45-6789"}),
        )

    assert ledger.get_events() == ()
