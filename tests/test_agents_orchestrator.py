"""Comprehensive verification suite for Phase 3 prompts, LLM client, 6 agents & orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from smartrx_safety_agents.agents.llm_client import (
    ALLOWED_GEMINI_FIELDS,
    MultiTierLLMClient,
    clean_gemini_schema,
    load_prompt_module,
    strip_think_tags,
)
from smartrx_safety_agents.agents.orchestrator import SmartRxOrchestrator
from smartrx_safety_agents.agents.specialists import AdversarialAuditorAgent
from smartrx_safety_agents.config import Settings
from smartrx_safety_agents.guardrails.engine import GuardrailEngine, verify_plan_signature
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.models.clinical import (
    AgentStatus,
    ClinicalOutput,
    IntakeOutput,
    LiaisonOutput,
    NormalizedMedication,
    RiskGrade,
    SafetyOutput,
)
from smartrx_safety_agents.persistence.ledger import AuditLedger

_SIGNING_SECRET = "test-signing-secret-at-least-32-chars!"  # noqa: S105


async def _noop_sleep(_seconds: float) -> None:
    return None


def _make_med(
    *,
    rxcui: str,
    name: str,
    is_nti: bool = False,
    ocr_confidence: float = 0.98,
) -> NormalizedMedication:
    return NormalizedMedication(
        rxcui=rxcui,
        scd_name=name,
        raw_name=name,
        dose_mg=5.0,
        frequency="once daily",
        route="oral",
        is_nti=is_nti,
        ocr_confidence=ocr_confidence,
    )


def test_prompt_modules_load_and_block_traversal() -> None:
    modules = (
        "intake_terminology.md",
        "clinical_history.md",
        "safety_auditor.md",
        "insurance_formulary.md",
        "adversarial_auditor.md",
        "pharmacist_liaison.md",
    )
    for mod in modules:
        content, version = load_prompt_module(mod)
        assert len(content.splitlines()) < 80
        assert version == "v1.0.0"

    with pytest.raises(ValueError, match="Path traversal blocked"):
        load_prompt_module("../../GEMINI.md")


def test_clean_gemini_schema_and_strip_think_tags() -> None:
    raw_schema = LiaisonOutput.model_json_schema()
    cleaned = clean_gemini_schema(raw_schema)
    assert "$defs" not in cleaned
    assert "$schema" not in cleaned

    def _assert_allowed(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                assert k in ALLOWED_GEMINI_FIELDS, f"Disallowed field: {k}"
                if k == "properties" and isinstance(v, dict):
                    for prop_schema in v.values():
                        _assert_allowed(prop_schema)
                else:
                    _assert_allowed(v)

    _assert_allowed(cleaned)

    raw_llm = '<think>internal reasoning</think>\n```json\n{"ok": true}\n```'
    assert strip_think_tags(raw_llm) == '{"ok": true}'


@pytest.mark.asyncio
async def test_pre_llm_phi_scrubbing_prevents_phi_egress() -> None:
    captured_bodies: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(request.content.decode("utf-8"))
        body = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "patient_token": "pt_masked",
                                        "medications": [],
                                        "low_confidence_nti_detected": False,
                                        "discrepancies": [],
                                        "confidence": 0.95,
                                    }
                                )
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20},
        }
        return httpx.Response(200, json=body)

    settings = Settings(
        gemini_api_key=SecretStr("fake-gemini-key-1234567890"),
        max_output_tokens=8192,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as http_client:
        client = MultiTierLLMClient(
            settings=settings,
            http_client=http_client,
            sleep_fn=_noop_sleep,
        )
        result = await client.generate_structured(
            system_prompt="Normalize meds.",
            user_payload=(
                "Patient Name: Jane Doe, MRN-998877, SSN 123-45-6789, "
                "DOB: 1955-04-12 takes Lisinopril 10mg."
            ),
            response_model=IntakeOutput,
            fallback_fn=lambda: IntakeOutput(patient_token="pt_masked", confidence=0.95),
            known_names=("Jane Doe",),
            known_mrns=("MRN-998877",),
        )

    assert result.tier_used == "primary_gemini"
    assert result.redaction_count >= 4
    assert len(captured_bodies) == 1
    sent_body = captured_bodies[0]
    for raw_phi in ("Jane Doe", "MRN-998877", "123-45-6789", "1955-04-12"):
        assert raw_phi not in sent_body
    assert "<untrusted_telemetry_data>" in sent_body


@pytest.mark.asyncio
async def test_three_tier_fallback_cascade_and_budget_breaker() -> None:
    call_urls: list[str] = []

    def _primary_fails_secondary_succeeds(request: httpx.Request) -> httpx.Response:
        call_urls.append(str(request.url))
        if "generativelanguage.googleapis.com" in str(request.url):
            return httpx.Response(503, json={"error": "overloaded"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<think>checking</think>```json\n"
                                '{"patient_token":"pt_1","medications":[],"low_confidence_nti_detected":false,'
                                '"discrepancies":[],"confidence":0.92}\n```'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15},
            },
        )

    settings = Settings(
        gemini_api_key=SecretStr("fake-gemini-key-1234567890"),
        openrouter_api_key=SecretStr("fake-openrouter-key-1234567890"),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_primary_fails_secondary_succeeds)
    ) as http_client:
        client = MultiTierLLMClient(
            settings=settings,
            http_client=http_client,
            sleep_fn=_noop_sleep,
        )
        sec_res = await client.generate_structured(
            system_prompt="Normalize.",
            user_payload="Lisinopril 10mg",
            response_model=IntakeOutput,
            fallback_fn=lambda: IntakeOutput(patient_token="pt_1", confidence=0.5),
        )
        assert sec_res.tier_used == "secondary_openrouter"
        assert sec_res.parsed.confidence == 0.92
        assert any("generativelanguage.googleapis.com" in u for u in call_urls)
        assert any("openrouter.ai" in u for u in call_urls)

    # Both primary and secondary fail -> Tier 3 Deterministic Fallback
    def _all_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_all_fail)) as http_client:
        client2 = MultiTierLLMClient(
            settings=settings,
            http_client=http_client,
            sleep_fn=_noop_sleep,
        )
        ter_res = await client2.generate_structured(
            system_prompt="Normalize.",
            user_payload="Lisinopril 10mg",
            response_model=IntakeOutput,
            fallback_fn=lambda: IntakeOutput(patient_token="pt_1", confidence=0.88),
        )
        assert ter_res.tier_used == "deterministic_fallback"
        assert ter_res.parsed.confidence == 0.88

        # Budget circuit breaker routes straight to deterministic fallback
        client2.session_tokens_used = settings.max_session_token_budget
        budget_res = await client2.generate_structured(
            system_prompt="Normalize.",
            user_payload="Lisinopril 10mg",
            response_model=IntakeOutput,
            fallback_fn=lambda: IntakeOutput(patient_token="pt_1", confidence=0.77),
        )
        assert budget_res.tier_used == "deterministic_fallback"
        assert budget_res.parsed.confidence == 0.77


@pytest.mark.asyncio
async def test_adversarial_auditor_detects_hallucinated_rxcui_and_phi() -> None:
    client = MultiTierLLMClient(settings=Settings(), sleep_fn=_noop_sleep)
    auditor = AdversarialAuditorAgent(client)
    med = _make_med(rxcui="11289", name="warfarin sodium 5 mg", is_nti=True)
    intake = IntakeOutput(patient_token="pt_abc", medications=(med,), confidence=0.95)
    clinical = ClinicalOutput(patient_token="pt_abc")
    safety = SafetyOutput(
        alerts=(),
        overall_risk_grade=RiskGrade.GREEN,
        recommended_action="APPROVE_RECONCILED_LIST",
    )
    bad_liaison = LiaisonOutput(
        plan_id="plan-bad",
        patient_token="pt_abc",
        status=AgentStatus.SUCCESS,
        overall_risk_grade=RiskGrade.GREEN,
        recommended_action="APPROVE_RECONCILED_LIST",
        pharmacist_summary="Patient Jane Doe should also take RxCUI: 9999999.",
        confidence=0.95,
    )
    out, _tel = await auditor.run(
        intake=intake,
        clinical=clinical,
        safety=safety,
        liaison=bad_liaison,
        known_phi=("Jane Doe",),
    )
    assert out.hallucination_detected is True
    assert out.phi_leak_detected is True
    assert out.audit_passed is False
    assert any("9999999" in c for c in out.unverified_claims)


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_ddi_and_ledger_hash_chain(tmp_path: Path) -> None:
    ledger = AuditLedger(tmp_path / "ledger.db")
    guardrail = GuardrailEngine(signing_secret=_SIGNING_SECRET)
    det_engine = DeterministicClinicalEngine()
    llm_client = MultiTierLLMClient(settings=Settings(), sleep_fn=_noop_sleep)
    orchestrator = SmartRxOrchestrator(
        llm_client=llm_client,
        deterministic_engine=det_engine,
        guardrail_engine=guardrail,
        audit_ledger=ledger,
    )

    warfarin = _make_med(rxcui="11289", name="warfarin sodium 5 mg", is_nti=True)
    amiodarone = _make_med(rxcui="703", name="amiodarone hydrochloride 200 mg")

    state = await orchestrator.run_reconciliation(
        plan_id="plan-ddi-001",
        idempotency_key="idem-ddi-001",
        raw_patient_id="MRN-554433",
        raw_intake_text="Patient Name: John Smith, MRN-554433 prescribed warfarin 5mg.",
        raw_ehr_summary="Active med: amiodarone 200mg. SSN 123-45-6789.",
        fallback_medications=(warfarin,),
        fallback_clinical=ClinicalOutput(
            patient_token="placeholder",
            active_medications=(amiodarone,),
            egfr_ml_min=65.0,
        ),
        known_names=("John Smith",),
        known_mrns=("MRN-554433",),
    )

    assert state.circuit_breaker_tripped is False
    assert state.turn_count == 1
    assert state.safety is not None
    assert state.safety.overall_risk_grade == RiskGrade.RED
    assert state.safety.recommended_action == "HOLD_PRESCRIPTION"
    assert state.remediation_plan is not None
    assert verify_plan_signature(state.remediation_plan, _SIGNING_SECRET) is True
    assert state.remediation_plan.execution_payload["resourceType"] == "Bundle"

    events = ledger.get_events(limit=20)
    assert len(events) == 6
    assert ledger.verify_chain_integrity() is True
    for ev in events:
        assert "John Smith" not in ev.payload_json
        assert "123-45-6789" not in ev.payload_json
        assert "v1.0.0" in ev.payload_json


@pytest.mark.asyncio
async def test_orchestrator_three_turn_circuit_breaker_halts_for_human(tmp_path: Path) -> None:
    ledger = AuditLedger(tmp_path / "cb_ledger.db")
    guardrail = GuardrailEngine(signing_secret=_SIGNING_SECRET)
    det_engine = DeterministicClinicalEngine()

    # Force LiaisonAgent via Primary Gemini mock to repeatedly emit an unverified RxCUI
    # so AdversarialAuditorAgent rejects all 3 turns and trips the Circuit Breaker.
    def _hallucinating_liaison(request: httpx.Request) -> httpx.Response:
        # Only intercept LiaisonOutput calls (check schema/prompt)
        body_text = request.content.decode("utf-8")
        if "Pharmacist Liaison" in body_text:
            payload = {
                "plan_id": "plan-cb-001",
                "patient_token": "pt_cb",
                "status": "SUCCESS",
                "overall_risk_grade": "GREEN",
                "recommended_action": "APPROVE_RECONCILED_LIST",
                "fhir_resources": [],
                "rollback_steps": [],
                "pharmacist_summary": "Hallucinated RxCUI: 9999999 recommendation.",
                "requires_hitl_attestation": False,
                "confidence": 0.99,
            }
            return httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10},
                },
            )
        return httpx.Response(500, json={"error": "use fallback"})

    settings = Settings(gemini_api_key=SecretStr("fake-gemini-key-1234567890"))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_hallucinating_liaison)
    ) as http_client:
        llm_client = MultiTierLLMClient(
            settings=settings,
            http_client=http_client,
            sleep_fn=_noop_sleep,
        )
        orchestrator = SmartRxOrchestrator(
            llm_client=llm_client,
            deterministic_engine=det_engine,
            guardrail_engine=guardrail,
            audit_ledger=ledger,
        )
        lisinopril = _make_med(rxcui="29046", name="lisinopril 10 mg")
        state = await orchestrator.run_reconciliation(
            plan_id="plan-cb-001",
            idempotency_key="idem-cb-001",
            raw_patient_id="MRN-112233",
            raw_intake_text="Lisinopril 10mg",
            raw_ehr_summary="No allergies.",
            fallback_medications=(lisinopril,),
            fallback_clinical=ClinicalOutput(patient_token="pt_cb", egfr_ml_min=85.0),
        )

    assert state.turn_count == 3
    assert state.circuit_breaker_tripped is True
    assert state.liaison is not None
    assert state.liaison.status == AgentStatus.HALT_FOR_HUMAN
    assert state.liaison.overall_risk_grade == RiskGrade.RED
    assert state.liaison.recommended_action == "ESCALATE_TO_CLINICAL_PHARMACIST"
    assert state.liaison.requires_hitl_attestation is True
    assert ledger.verify_chain_integrity() is True
