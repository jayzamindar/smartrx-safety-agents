"""Typed implementations of the 6 SmartRx clinical pharmacy specialist agents."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Final

from smartrx_safety_agents.agents.llm_client import MultiTierLLMClient, load_prompt_module
from smartrx_safety_agents.guardrails.fhir_generator import generate_fhir_payload
from smartrx_safety_agents.guardrails.rollback import synthesize_rollback
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor
from smartrx_safety_agents.models.clinical import (
    AgentStatus,
    AuditorOutput,
    ClinicalOutput,
    InsuranceOutput,
    IntakeOutput,
    LiaisonOutput,
    NormalizedMedication,
    RiskGrade,
    SafetyOutput,
)

_RXCUI_MENTION_RE: Final[re.Pattern[str]] = re.compile(r"\bRxCUI[:#\s-]*(\d{4,8})\b", re.IGNORECASE)


@dataclass(frozen=True)
class AgentTelemetry:
    """Execution metadata recorded per specialist invocation."""

    agent_name: str
    prompt_version: str
    tier_used: str
    model_version: str


class IntakeAgent:
    """Agent 1: Normalizes incoming prescriptions/OCR text to RxNorm RxCUIs."""

    PROMPT_MODULE: Final[str] = "intake_terminology.md"

    def __init__(self, llm_client: MultiTierLLMClient) -> None:
        self._llm = llm_client
        self.prompt_text, self.prompt_version = load_prompt_module(self.PROMPT_MODULE)

    async def run(
        self,
        *,
        patient_token: str,
        raw_intake_text: str,
        fallback_medications: tuple[NormalizedMedication, ...] = (),
        known_names: tuple[str, ...] = (),
        known_mrns: tuple[str, ...] = (),
    ) -> tuple[IntakeOutput, AgentTelemetry]:
        """Normalize prescription input with mandatory pre-LLM PHI scrubbing."""

        def _fallback() -> IntakeOutput:
            low_nti = any(m.is_nti and m.ocr_confidence < 0.70 for m in fallback_medications)
            min_conf = min((m.ocr_confidence for m in fallback_medications), default=1.0)
            return IntakeOutput(
                patient_token=patient_token,
                medications=fallback_medications,
                low_confidence_nti_detected=low_nti,
                discrepancies=(),
                confidence=min_conf,
            )

        payload = json.dumps(
            {
                "patient_token": patient_token,
                "raw_intake_text": raw_intake_text,
            },
            ensure_ascii=False,
        )
        result = await self._llm.generate_structured(
            system_prompt=self.prompt_text,
            user_payload=payload,
            response_model=IntakeOutput,
            fallback_fn=_fallback,
            known_names=known_names,
            known_mrns=known_mrns,
        )
        # Ensure patient_token is never altered by LLM output.
        normalized = result.parsed.model_copy(update={"patient_token": patient_token})
        return normalized, AgentTelemetry(
            agent_name="IntakeAgent",
            prompt_version=self.prompt_version,
            tier_used=result.tier_used,
            model_version=result.model_version,
        )


class ClinicalHistoryAgent:
    """Agent 2: Consolidates longitudinal EHR medications, allergies, and organ labs."""

    PROMPT_MODULE: Final[str] = "clinical_history.md"

    def __init__(self, llm_client: MultiTierLLMClient) -> None:
        self._llm = llm_client
        self.prompt_text, self.prompt_version = load_prompt_module(self.PROMPT_MODULE)

    async def run(
        self,
        *,
        patient_token: str,
        raw_ehr_summary: str,
        fallback_clinical: ClinicalOutput | None = None,
        known_names: tuple[str, ...] = (),
        known_mrns: tuple[str, ...] = (),
    ) -> tuple[ClinicalOutput, AgentTelemetry]:
        """Extract longitudinal clinical history with pre-LLM PHI scrubbing."""

        def _fallback() -> ClinicalOutput:
            if fallback_clinical is not None:
                return fallback_clinical.model_copy(update={"patient_token": patient_token})
            return ClinicalOutput(patient_token=patient_token, partial_ehr_record=True)

        payload = json.dumps(
            {
                "patient_token": patient_token,
                "raw_ehr_summary": raw_ehr_summary,
            },
            ensure_ascii=False,
        )
        result = await self._llm.generate_structured(
            system_prompt=self.prompt_text,
            user_payload=payload,
            response_model=ClinicalOutput,
            fallback_fn=_fallback,
            known_names=known_names,
            known_mrns=known_mrns,
        )
        normalized = result.parsed.model_copy(update={"patient_token": patient_token})
        return normalized, AgentTelemetry(
            agent_name="ClinicalHistoryAgent",
            prompt_version=self.prompt_version,
            tier_used=result.tier_used,
            model_version=result.model_version,
        )


class SafetyAuditorAgent:
    """Agent 3: Deterministic-first safety gate executing BEFORE any LLM synthesis."""

    PROMPT_MODULE: Final[str] = "safety_auditor.md"

    def __init__(self, deterministic_engine: DeterministicClinicalEngine) -> None:
        self._engine = deterministic_engine
        self.prompt_text, self.prompt_version = load_prompt_module(self.PROMPT_MODULE)

    async def run(
        self,
        *,
        intake: IntakeOutput,
        clinical: ClinicalOutput,
        patient_age: int | None = None,
        payer_formulary: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[SafetyOutput, InsuranceOutput, AgentTelemetry]:
        """Execute deterministic DDI, allergy, dosing, and formulary engines first."""
        safety, insurance = self._engine.evaluate(
            intake,
            clinical,
            patient_age=patient_age,
            payer_formulary=payer_formulary,
        )
        return (
            safety,
            insurance,
            AgentTelemetry(
                agent_name="SafetyAuditorAgent",
                prompt_version=self.prompt_version,
                tier_used="deterministic_first",
                model_version="deterministic-sre-heuristics-v1",
            ),
        )


class InsuranceAgent:
    """Agent 4: Evaluates payer coverage, tier, PA, and CMS fallback alternatives."""

    PROMPT_MODULE: Final[str] = "insurance_formulary.md"

    def __init__(self, llm_client: MultiTierLLMClient) -> None:
        self._llm = llm_client
        self.prompt_text, self.prompt_version = load_prompt_module(self.PROMPT_MODULE)

    async def run(
        self,
        *,
        patient_token: str,
        medications: tuple[NormalizedMedication, ...],
        deterministic_insurance: InsuranceOutput,
    ) -> tuple[InsuranceOutput, AgentTelemetry]:
        """Enrich or confirm deterministic formulary coverage without overriding rules."""
        payload = json.dumps(
            {
                "patient_token": patient_token,
                "rxcuis": [m.rxcui for m in medications],
                "deterministic_insurance": deterministic_insurance.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        result = await self._llm.generate_structured(
            system_prompt=self.prompt_text,
            user_payload=payload,
            response_model=InsuranceOutput,
            fallback_fn=lambda: deterministic_insurance,
        )
        # Preserve authoritative deterministic coverage & CMS fallback flags.
        anchored = result.parsed.model_copy(
            update={
                "covered": deterministic_insurance.covered,
                "formulary_tier": deterministic_insurance.formulary_tier,
                "requires_pa": deterministic_insurance.requires_pa,
                "used_cms_fallback": deterministic_insurance.used_cms_fallback,
            }
        )
        return anchored, AgentTelemetry(
            agent_name="InsuranceAgent",
            prompt_version=self.prompt_version,
            tier_used=result.tier_used,
            model_version=result.model_version,
        )


class AdversarialAuditorAgent:
    """Agent 5: Cross-verifies claims against raw RxCUI/FHIR evidence and PHI leaks."""

    PROMPT_MODULE: Final[str] = "adversarial_auditor.md"

    def __init__(self, llm_client: MultiTierLLMClient) -> None:
        self._llm = llm_client
        self.prompt_text, self.prompt_version = load_prompt_module(self.PROMPT_MODULE)

    async def run(
        self,
        *,
        intake: IntakeOutput,
        clinical: ClinicalOutput,
        safety: SafetyOutput,
        liaison: LiaisonOutput,
        known_phi: tuple[str, ...] = (),
    ) -> tuple[AuditorOutput, AgentTelemetry]:
        """Verify zero hallucinations, zero PHI leaks, and strict safety consensus."""
        known_rxcuis = {m.rxcui for m in intake.medications + clinical.active_medications}
        verified_citations = tuple(a.citation for a in safety.alerts)
        unverified: list[str] = []

        for mentioned_rxcui in _RXCUI_MENTION_RE.findall(liaison.pharmacist_summary):
            if mentioned_rxcui.casefold() not in known_rxcuis:
                unverified.append(f"Unverified RxCUI referenced in summary: {mentioned_rxcui}")

        if liaison.recommended_action != safety.recommended_action:
            unverified.append(
                f"Action mismatch: liaison={liaison.recommended_action} "
                f"vs safety={safety.recommended_action}"
            )
        if liaison.overall_risk_grade != safety.overall_risk_grade:
            unverified.append(
                f"RiskGrade mismatch: liaison={liaison.overall_risk_grade} "
                f"vs safety={safety.overall_risk_grade}"
            )

        phi_leak = PHIRedactor.contains_phi(
            liaison.pharmacist_summary, known_identifiers=known_phi
        )
        det_hallucination = len(unverified) > 0

        def _fallback() -> AuditorOutput:
            return AuditorOutput(
                hallucination_detected=det_hallucination,
                phi_leak_detected=phi_leak,
                unverified_claims=tuple(unverified),
                verified_citations=verified_citations,
                audit_passed=not (det_hallucination or phi_leak),
            )

        payload = json.dumps(
            {
                "known_rxcuis": sorted(known_rxcuis),
                "safety_action": safety.recommended_action,
                "safety_grade": safety.overall_risk_grade.value,
                "verified_citations": list(verified_citations),
                "liaison_summary": liaison.pharmacist_summary,
                "liaison_action": liaison.recommended_action,
                "liaison_grade": liaison.overall_risk_grade.value,
            },
            ensure_ascii=False,
        )
        result = await self._llm.generate_structured(
            system_prompt=self.prompt_text,
            user_payload=payload,
            response_model=AuditorOutput,
            fallback_fn=_fallback,
        )
        merged_hallucination = det_hallucination or result.parsed.hallucination_detected
        merged_phi = phi_leak or result.parsed.phi_leak_detected
        merged_claims = tuple(dict.fromkeys([*unverified, *result.parsed.unverified_claims]))
        merged_citations = tuple(
            dict.fromkeys([*verified_citations, *result.parsed.verified_citations])
        )
        merged_passed = (
            not merged_hallucination and not merged_phi and result.parsed.audit_passed
        )
        audited = AuditorOutput(
            hallucination_detected=merged_hallucination,
            phi_leak_detected=merged_phi,
            unverified_claims=merged_claims,
            verified_citations=merged_citations,
            audit_passed=merged_passed,
        )
        return audited, AgentTelemetry(
            agent_name="AdversarialAuditorAgent",
            prompt_version=self.prompt_version,
            tier_used=result.tier_used,
            model_version=result.model_version,
        )


class PharmacistLiaisonAgent:
    """Agent 6: Compiles 3-Tier HITL report and deterministic HL7 FHIR R4 payloads."""

    PROMPT_MODULE: Final[str] = "pharmacist_liaison.md"

    def __init__(self, llm_client: MultiTierLLMClient) -> None:
        self._llm = llm_client
        self.prompt_text, self.prompt_version = load_prompt_module(self.PROMPT_MODULE)

    async def run(
        self,
        *,
        plan_id: str,
        intake: IntakeOutput,
        safety: SafetyOutput,
        insurance: InsuranceOutput,
        feedback: tuple[str, ...] = (),
        dry_run: bool = False,
    ) -> tuple[LiaisonOutput, AgentTelemetry]:
        """Synthesize pharmacist summary while anchoring FHIR R4 and safety grades."""
        affected_rxcuis = tuple(m.rxcui for m in intake.medications)
        rollback_steps = synthesize_rollback(
            safety.recommended_action,
            affected_rxcuis=affected_rxcuis,
            dry_run=dry_run,
        )
        fhir_bundle = generate_fhir_payload(
            safety.recommended_action,
            patient_token=intake.patient_token,
            medications=intake.medications,
            alerts=safety.alerts,
            dry_run=dry_run,
        )
        fhir_resources: tuple[dict[str, Any], ...] = (fhir_bundle,)
        requires_hitl = safety.overall_risk_grade != RiskGrade.GREEN or safety.quarantined

        def _fallback() -> LiaisonOutput:
            alert_notes = "; ".join(f"{a.rule_category}:{a.citation}" for a in safety.alerts)
            summary = (
                f"Risk={safety.overall_risk_grade.value}; Action={safety.recommended_action}; "
                f"Tier={insurance.formulary_tier}; Alerts=[{alert_notes or 'none'}]"
            )
            return LiaisonOutput(
                plan_id=plan_id,
                patient_token=intake.patient_token,
                status=AgentStatus.SUCCESS,
                overall_risk_grade=safety.overall_risk_grade,
                recommended_action=safety.recommended_action,
                fhir_resources=fhir_resources,
                rollback_steps=rollback_steps,
                pharmacist_summary=summary,
                requires_hitl_attestation=requires_hitl,
                confidence=intake.confidence,
            )

        payload = json.dumps(
            {
                "plan_id": plan_id,
                "patient_token": intake.patient_token,
                "safety": safety.model_dump(mode="json"),
                "insurance": insurance.model_dump(mode="json"),
                "feedback": list(feedback),
            },
            ensure_ascii=False,
        )
        result = await self._llm.generate_structured(
            system_prompt=self.prompt_text,
            user_payload=payload,
            response_model=LiaisonOutput,
            fallback_fn=_fallback,
        )
        anchored = result.parsed.model_copy(
            update={
                "plan_id": plan_id,
                "patient_token": intake.patient_token,
                "overall_risk_grade": safety.overall_risk_grade,
                "recommended_action": safety.recommended_action,
                "fhir_resources": fhir_resources,
                "rollback_steps": rollback_steps,
                "requires_hitl_attestation": requires_hitl,
            }
        )
        return anchored, AgentTelemetry(
            agent_name="PharmacistLiaisonAgent",
            prompt_version=self.prompt_version,
            tier_used=result.tier_used,
            model_version=result.model_version,
        )
