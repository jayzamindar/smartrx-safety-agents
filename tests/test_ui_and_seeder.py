"""Comprehensive tests for Pharmacist HITL Workbench helpers and FHIR R4 seeder."""

from __future__ import annotations

import json

import httpx

from smartrx_safety_agents.agents.orchestrator import BlackboardState
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor
from smartrx_safety_agents.models.clinical import (
    AgentStatus,
    ClinicalOutput,
    IntakeOutput,
    LiaisonOutput,
    NormalizedMedication,
    RiskGrade,
    SafetyOutput,
)
from smartrx_safety_agents.seed_data import (
    build_benchmark_scenarios,
    build_fhir_transaction_bundle,
    post_bundle_to_hapi_fhir,
    run_benchmark_suite,
)
from smartrx_safety_agents.ui.dashboard import (
    build_bpmh_diff,
    build_circuit_breaker_banner,
    classify_traffic_light,
    format_agent_breadcrumbs,
    run_what_if_swap,
    validate_adjudication_submission,
)


def _med(
    rxcui: str,
    name: str,
    *,
    dose_mg: float = 10.0,
    is_nti: bool = False,
    ocr_confidence: float = 0.98,
) -> NormalizedMedication:
    return NormalizedMedication(
        rxcui=rxcui,
        scd_name=name,
        raw_name=name,
        dose_mg=dose_mg,
        frequency="once daily",
        route="oral",
        is_nti=is_nti,
        ocr_confidence=ocr_confidence,
    )


def test_traffic_light_and_adjudication_validation() -> None:
    red_safety = SafetyOutput(
        overall_risk_grade=RiskGrade.RED,
        recommended_action="HOLD_PRESCRIPTION",
    )
    yellow_safety = SafetyOutput(
        overall_risk_grade=RiskGrade.YELLOW,
        recommended_action="FLAG_DRUG_INTERACTION",
    )
    green_safety = SafetyOutput(
        overall_risk_grade=RiskGrade.GREEN,
        recommended_action="APPROVE_RECONCILED_LIST",
    )
    clean_intake = IntakeOutput(patient_token="pt_ui1", confidence=0.98)
    low_ocr_intake = IntakeOutput(
        patient_token="pt_ui2", low_confidence_nti_detected=True, confidence=0.60
    )

    red_badge = classify_traffic_light(red_safety, clean_intake)
    assert red_badge.grade == RiskGrade.RED
    assert red_badge.blocked is True

    assert classify_traffic_light(green_safety, low_ocr_intake).blocked is True
    assert classify_traffic_light(yellow_safety, clean_intake).grade == RiskGrade.YELLOW
    assert classify_traffic_light(green_safety, clean_intake).grade == RiskGrade.GREEN

    # Tier 1 RED lock requires both Clinical Justification Code and NPI Attestation
    ok_missing_code, msg1 = validate_adjudication_submission(
        risk_grade=RiskGrade.RED,
        decision="Accept",
        justification_code=None,
        npi_attestation="1234567890",
        reason_text=None,
    )
    assert ok_missing_code is False
    assert msg1 is not None

    ok_missing_npi, _ = validate_adjudication_submission(
        risk_grade=RiskGrade.RED,
        decision="Accept",
        justification_code="CJC-01",
        npi_attestation="",
        reason_text=None,
    )
    assert ok_missing_npi is False

    ok_red, _ = validate_adjudication_submission(
        risk_grade=RiskGrade.RED,
        decision="Accept",
        justification_code="CJC-01",
        npi_attestation="1234567890",
        reason_text=None,
    )
    assert ok_red is True

    # Tier 2 YELLOW Modify requires reason_text
    ok_yellow_bad, _ = validate_adjudication_submission(
        risk_grade=RiskGrade.YELLOW,
        decision="Modify",
        justification_code=None,
        npi_attestation=None,
        reason_text=" ",
    )
    assert ok_yellow_bad is False


def test_bpmh_diff_and_what_if_sandbox() -> None:
    med_continued = _med("29046", "lisinopril 10 mg", dose_mg=10.0)
    med_modified_new = _med("11289", "warfarin sodium 5 mg", dose_mg=5.0, is_nti=True)
    med_modified_old = _med("11289", "warfarin sodium 2.5 mg", dose_mg=2.5, is_nti=True)
    med_added = _med("83367", "atorvastatin 20 mg", dose_mg=20.0)
    med_discontinued = _med("703", "amiodarone 200 mg", dose_mg=200.0)

    intake = IntakeOutput(
        patient_token="pt_diff",
        medications=(med_continued, med_modified_new, med_added),
        confidence=0.98,
    )
    clinical = ClinicalOutput(
        patient_token="pt_diff",
        active_medications=(med_continued, med_modified_old, med_discontinued),
        egfr_ml_min=75.0,
    )
    engine = DeterministicClinicalEngine()
    safety, _ = engine.evaluate(intake, clinical)
    diff = build_bpmh_diff(intake, clinical, safety)
    statuses = {item.rxcui: item.diff_status for item in diff}
    assert statuses["29046"] == "Continued"
    assert statuses["11289"] == "Modified"
    assert statuses["83367"] == "Added"
    assert statuses["703"] == "Discontinued"

    # What-If Sandbox: swap Warfarin (11289) for Lisinopril (29046) to remove DDI alert
    sandbox_intake = IntakeOutput(
        patient_token="pt_diff",
        medications=(med_modified_new,),
        confidence=0.98,
    )
    sandbox_clinical = ClinicalOutput(
        patient_token="pt_diff",
        active_medications=(med_discontinued,),
        egfr_ml_min=75.0,
    )
    before_safety, _ = engine.evaluate(sandbox_intake, sandbox_clinical)
    assert before_safety.overall_risk_grade == RiskGrade.RED

    sim_safety, _ = run_what_if_swap(
        sandbox_intake,
        sandbox_clinical,
        replace_rxcui="11289",
        replacement_med=_med("29046", "lisinopril 10 mg", dose_mg=10.0),
        engine=engine,
    )
    assert sim_safety.overall_risk_grade != RiskGrade.RED


def test_circuit_breaker_banner_and_breadcrumbs() -> None:
    normal_state = BlackboardState(
        plan_id="p-norm",
        idempotency_key="i-norm",
        patient_token="pt_norm",
        tier_trace={"IntakeAgent": "deterministic_fallback"},
    )
    assert build_circuit_breaker_banner(normal_state) is None
    crumbs = format_agent_breadcrumbs(normal_state)
    assert len(crumbs) == 6
    assert "Intake [deterministic_fallback]" in crumbs

    tripped_state = BlackboardState(
        plan_id="p-cb",
        idempotency_key="i-cb",
        patient_token="pt_cb",
        turn_count=3,
        circuit_breaker_tripped=True,
        liaison=LiaisonOutput(
            plan_id="p-cb",
            patient_token="pt_cb",
            status=AgentStatus.HALT_FOR_HUMAN,
            overall_risk_grade=RiskGrade.RED,
            recommended_action="ESCALATE_TO_CLINICAL_PHARMACIST",
            pharmacist_summary="Halted.",
            confidence=0.5,
        ),
    )
    banner = build_circuit_breaker_banner(tripped_state)
    assert banner is not None
    assert banner["color_hex"] == "#EF6C00"
    assert "HALT_FOR_HUMAN" in banner["title"]


def test_fhir_r4_synthetic_seeder_and_benchmark_tc001_to_tc008() -> None:
    scenarios = build_benchmark_scenarios()
    assert len(scenarios) == 8

    for scenario in scenarios:
        bundle = build_fhir_transaction_bundle(scenario)
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "transaction"
        resource_types = {e["resource"]["resourceType"] for e in bundle["entry"]}
        assert "Patient" in resource_types
        assert "MedicationRequest" in resource_types
        assert PHIRedactor.contains_phi(json.dumps(bundle)) is False

    # Verify HTTP POST to HAPI FHIR endpoint with MockTransport
    posted_urls: list[str] = []

    def _mock_fhir(request: httpx.Request) -> httpx.Response:
        posted_urls.append(str(request.url))
        return httpx.Response(200, json={"resourceType": "Bundle", "type": "transaction-response"})

    first_bundle = build_fhir_transaction_bundle(scenarios[0])
    with httpx.Client(transport=httpx.MockTransport(_mock_fhir)) as client:
        resp = post_bundle_to_hapi_fhir(
            first_bundle, fhir_base_url="http://localhost:8080/fhir", client=client
        )
    assert resp.status_code == 200
    assert posted_urls == ["http://localhost:8080/fhir"]

    # Verify all 8 benchmark cases pass deterministically
    results = run_benchmark_suite()
    assert len(results) == 8
    assert all(r["passed"] is True for r in results), f"Benchmark failures: {results}"
