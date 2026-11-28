"""Phase 12 Adversarial Red-Team Edge-Case & Concurrency Regression Suite."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from smartrx_safety_agents.api.mcp_server import SmartRxMCPServer
from smartrx_safety_agents.guardrails.engine import GuardrailEngine
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.models.clinical import (
    ClinicalOutput,
    IntakeOutput,
    NormalizedMedication,
    RiskGrade,
    normalize_clinical_identifier,
)
from smartrx_safety_agents.persistence.ledger import AuditLedger


def test_adversarial_zero_width_homoglyph_bypass_blocked() -> None:
    """Zero-width chars (ZWSP, ZWNJ, BOM, soft hyphen) cannot bypass allergy/DDI matching."""
    assert normalize_clinical_identifier("peni\u200bcillin\ufeff") == "penicillin"
    assert normalize_clinical_identifier("war\u200dfarin\u00ad") == "warfarin"

    engine = DeterministicClinicalEngine()
    safety, _ = engine.evaluate(
        IntakeOutput(
            patient_token="pt_zwsp",
            medications=(
                NormalizedMedication(
                    rxcui="723",
                    scd_name="amoxicillin 500 mg capsule",
                    raw_name="amoxicillin",
                    frequency="once daily",
                    route="oral",
                ),
            ),
            confidence=0.98,
        ),
        ClinicalOutput(
            patient_token="pt_zwsp",
            allergies=("peni\u200bcil\u200dlin\ufeff",),
        ),
    )
    assert safety.overall_risk_grade == RiskGrade.RED
    assert safety.recommended_action == "HOLD_PRESCRIPTION"


def test_adversarial_empty_medications_and_boundary_egfr_thresholds() -> None:
    """Empty medication list returns GREEN; boundary eGFR values respect strict < thresholds."""
    engine = DeterministicClinicalEngine()

    # Empty medications with clean formulary -> GREEN / APPROVE_RECONCILED_LIST
    empty_safety, _ = engine.evaluate(
        IntakeOutput(patient_token="pt_empty", medications=(), confidence=1.0),
        ClinicalOutput(patient_token="pt_empty"),
        payer_formulary={},
    )
    assert empty_safety.overall_risk_grade == RiskGrade.GREEN
    assert empty_safety.recommended_action == "APPROVE_RECONCILED_LIST"

    # Digoxin (RxCUI 3407): contraindicated_egfr=15.0, min_egfr=30.0
    digoxin = NormalizedMedication(
        rxcui="3407",
        scd_name="digoxin 0.125 mg oral tablet",
        raw_name="digoxin",
        frequency="once daily",
        route="oral",
        is_nti=True,
    )
    # eGFR = 0.0 -> contraindicated RED HOLD_PRESCRIPTION
    zero_egfr, _ = engine.evaluate(
        IntakeOutput(patient_token="pt_egfr0", medications=(digoxin,), confidence=0.98),
        ClinicalOutput(patient_token="pt_egfr0", egfr_ml_min=0.0),
    )
    assert zero_egfr.overall_risk_grade == RiskGrade.RED
    assert zero_egfr.recommended_action == "HOLD_PRESCRIPTION"

    # eGFR = 15.0 (exact boundary) -> not < 15.0, falls into < 30.0 renal adjustment (YELLOW)
    boundary_15, _ = engine.evaluate(
        IntakeOutput(patient_token="pt_egfr15", medications=(digoxin,), confidence=0.98),
        ClinicalOutput(patient_token="pt_egfr15", egfr_ml_min=15.0),
    )
    assert boundary_15.overall_risk_grade == RiskGrade.YELLOW
    assert boundary_15.recommended_action == "PROPOSE_THERAPEUTIC_ALTERNATIVE"


def test_adversarial_concurrent_sqlite_wal_read_write_contention(tmp_path: Path) -> None:
    """Concurrent multi-threaded FileLock writes and MVCC reads preserve hash-chain integrity."""
    ledger = AuditLedger(tmp_path / "concurrent.db", filelock_timeout_sec=10.0)
    guardrail = GuardrailEngine(signing_secret="concurrent-test-signing-secret-32c!")

    def _worker(idx: int) -> None:
        plan = guardrail.enforce(
            plan_id=f"plan-conc-{idx}",
            idempotency_key=f"idem-conc-{idx}",
            patient_token=f"pt_{idx}",
            action_type="APPROVE_RECONCILED_LIST",
            risk_score=1,
            risk_grade=RiskGrade.GREEN,
        )
        ledger.record_event(
            plan_id=plan.plan_id,
            idempotency_key=plan.idempotency_key,
            patient_token=plan.patient_token,
            agent_name="AdversarialWorker",
            model_version="deterministic-sre-heuristics-v1",
            action_type=plan.action_type,
            risk_grade=plan.risk_grade,
            quarantined=plan.quarantined,
            payload_json='{"ok":true}',
        )
        _ = ledger.get_events(limit=20)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_worker, i) for i in range(18)]
        for fut in futures:
            fut.result()

    assert ledger.verify_chain_integrity() is True


@pytest.mark.asyncio
async def test_adversarial_mcp_oversized_jsonrpc_rejected(tmp_path: Path) -> None:
    """SmartRxMCPServer rejects JSON-RPC payloads exceeding 10MB ceiling with -32600."""
    import json

    from smartrx_safety_agents.agents.llm_client import MultiTierLLMClient
    from smartrx_safety_agents.agents.orchestrator import SmartRxOrchestrator

    ledger = AuditLedger(tmp_path / "mcp.db")
    orchestrator = SmartRxOrchestrator(
        llm_client=MultiTierLLMClient(),
        deterministic_engine=DeterministicClinicalEngine(),
        guardrail_engine=GuardrailEngine(signing_secret="mcp-test-signing-secret-32-chars!"),
        audit_ledger=ledger,
    )
    mcp = SmartRxMCPServer(orchestrator=orchestrator, ledger=ledger, max_payload_bytes=1024)
    oversized = (
        '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"pad":"' + ("a" * 2048) + '"}}'
    )
    raw_resp = await mcp.handle_raw_line(oversized.encode("utf-8"))
    resp = json.loads(raw_resp.decode("utf-8"))
    assert resp["error"]["code"] == -32600

    with pytest.raises(ValueError, match="patient_token"):
        from smartrx_safety_agents.guardrails.fhir_generator import build_clinical_task

        build_clinical_task(patient_token="   ", action_type="HOLD_PRESCRIPTION", description="x")


def test_adversarial_phi_redactor_blocks_homoglyph_identifiers() -> None:
    """PHIRedactor.contains_phi catches fullwidth/zero-width homoglyph PHI identifiers."""
    from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor

    assert (
        PHIRedactor.contains_phi(
            "Patient Ｊｏｈｎ\u200b Ｄｏｅ",
            known_identifiers=("John Doe",),
        )
        is True
    )
