"""Blackboard orchestrator with parallel intake/history, 3-turn circuit breaker & audit."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Final

from pydantic import Field

from smartrx_safety_agents.agents.llm_client import MultiTierLLMClient
from smartrx_safety_agents.agents.specialists import (
    AdversarialAuditorAgent,
    AgentTelemetry,
    ClinicalHistoryAgent,
    InsuranceAgent,
    IntakeAgent,
    PharmacistLiaisonAgent,
    SafetyAuditorAgent,
)
from smartrx_safety_agents.guardrails.engine import GuardrailEngine
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
    StrictClinicalModel,
)
from smartrx_safety_agents.models.remediation import RemediationPlan
from smartrx_safety_agents.persistence.ledger import AuditLedger

_MAX_CIRCUIT_BREAKER_TURNS: Final[int] = 3


class BlackboardState(StrictClinicalModel):
    """Immutable snapshot of the 6-agent Blackboard reconciliation state."""

    plan_id: str
    idempotency_key: str
    patient_token: str
    intake: IntakeOutput | None = None
    clinical: ClinicalOutput | None = None
    safety: SafetyOutput | None = None
    insurance: InsuranceOutput | None = None
    auditor: AuditorOutput | None = None
    liaison: LiaisonOutput | None = None
    remediation_plan: RemediationPlan | None = None
    turn_count: int = 0
    circuit_breaker_tripped: bool = False
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    tier_trace: dict[str, str] = Field(default_factory=dict)


class SmartRxOrchestrator:
    """Coordinates the 5-stage deterministic-first 6-agent reconciliation pipeline."""

    def __init__(
        self,
        *,
        llm_client: MultiTierLLMClient,
        deterministic_engine: DeterministicClinicalEngine,
        guardrail_engine: GuardrailEngine,
        audit_ledger: AuditLedger,
    ) -> None:
        self._llm = llm_client
        self._deterministic_engine = deterministic_engine
        self._guardrail = guardrail_engine
        self._ledger = audit_ledger
        self._phi_redactor = PHIRedactor()

        self._intake_agent = IntakeAgent(llm_client)
        self._clinical_agent = ClinicalHistoryAgent(llm_client)
        self._safety_agent = SafetyAuditorAgent(deterministic_engine)
        self._insurance_agent = InsuranceAgent(llm_client)
        self._auditor_agent = AdversarialAuditorAgent(llm_client)
        self._liaison_agent = PharmacistLiaisonAgent(llm_client)

    async def _record_step(
        self,
        *,
        plan_id: str,
        step_suffix: str,
        patient_token: str,
        telemetry: AgentTelemetry,
        safety: SafetyOutput,
        payload: dict[str, Any],
        known_phi: tuple[str, ...],
    ) -> None:
        step_key = f"{plan_id}:{step_suffix}"
        enriched = {
            "prompt_version": telemetry.prompt_version,
            "tier_used": telemetry.tier_used,
            "data": payload,
        }
        await asyncio.to_thread(
            self._ledger.record_event,
            plan_id=step_key,
            idempotency_key=step_key,
            patient_token=patient_token,
            agent_name=telemetry.agent_name,
            model_version=telemetry.model_version,
            action_type=safety.recommended_action,
            risk_grade=safety.overall_risk_grade,
            quarantined=safety.quarantined,
            payload_json=json.dumps(enriched, sort_keys=True, ensure_ascii=False),
            known_phi=known_phi,
        )

    async def run_reconciliation(
        self,
        *,
        plan_id: str,
        idempotency_key: str,
        raw_patient_id: str,
        raw_intake_text: str,
        raw_ehr_summary: str,
        fallback_medications: tuple[NormalizedMedication, ...] = (),
        fallback_clinical: ClinicalOutput | None = None,
        patient_age: int | None = None,
        payer_formulary: dict[str, dict[str, Any]] | None = None,
        known_names: tuple[str, ...] = (),
        known_mrns: tuple[str, ...] = (),
        dry_run: bool = False,
    ) -> BlackboardState:
        """Execute the 5-stage 6-agent pipeline with 3-turn circuit breaker and audit."""
        patient_token = PHIRedactor.tokenize_patient_id(raw_patient_id)
        known_phi = (*known_names, *known_mrns, raw_patient_id)

        scrubbed_intake = self._phi_redactor.redact(
            raw_intake_text, known_names=known_names, known_mrns=known_mrns
        ).redacted_text
        scrubbed_ehr = self._phi_redactor.redact(
            raw_ehr_summary, known_names=known_names, known_mrns=known_mrns
        ).redacted_text

        # Stage 1: Parallel Intake & Clinical History
        (intake_out, intake_tel), (clinical_out, clinical_tel) = await asyncio.gather(
            self._intake_agent.run(
                patient_token=patient_token,
                raw_intake_text=scrubbed_intake,
                fallback_medications=fallback_medications,
                known_names=known_names,
                known_mrns=known_mrns,
            ),
            self._clinical_agent.run(
                patient_token=patient_token,
                raw_ehr_summary=scrubbed_ehr,
                fallback_clinical=fallback_clinical,
                known_names=known_names,
                known_mrns=known_mrns,
            ),
        )

        # Stage 2: Deterministic Safety Gate BEFORE any LLM synthesis
        safety_out, det_insurance, safety_tel = await self._safety_agent.run(
            intake=intake_out,
            clinical=clinical_out,
            patient_age=patient_age,
            payer_formulary=payer_formulary,
        )

        # Stage 3: Insurance & Formulary Evaluation
        insurance_out, insurance_tel = await self._insurance_agent.run(
            patient_token=patient_token,
            medications=intake_out.medications,
            deterministic_insurance=det_insurance,
        )

        # Stage 4: Adversarial Critic & Pharmacist Liaison with 3-Turn Circuit Breaker
        feedback: tuple[str, ...] = ()
        liaison_out: LiaisonOutput | None = None
        auditor_out: AuditorOutput | None = None
        liaison_tel: AgentTelemetry | None = None
        auditor_tel: AgentTelemetry | None = None
        turn_count = 0
        circuit_breaker_tripped = False

        for turn in range(1, _MAX_CIRCUIT_BREAKER_TURNS + 1):
            turn_count = turn
            liaison_out, liaison_tel = await self._liaison_agent.run(
                plan_id=plan_id,
                intake=intake_out,
                safety=safety_out,
                insurance=insurance_out,
                feedback=feedback,
                dry_run=dry_run,
            )
            auditor_out, auditor_tel = await self._auditor_agent.run(
                intake=intake_out,
                clinical=clinical_out,
                safety=safety_out,
                liaison=liaison_out,
                known_phi=known_phi,
            )
            if auditor_out.audit_passed:
                break
            feedback = auditor_out.unverified_claims or ("Adversarial audit failed; revise.",)
            if turn == _MAX_CIRCUIT_BREAKER_TURNS:
                circuit_breaker_tripped = True
                liaison_out = liaison_out.model_copy(
                    update={
                        "status": AgentStatus.HALT_FOR_HUMAN,
                        "overall_risk_grade": RiskGrade.RED,
                        "recommended_action": "ESCALATE_TO_CLINICAL_PHARMACIST",
                        "requires_hitl_attestation": True,
                        "pharmacist_summary": (
                            "HALT_FOR_HUMAN: 3-turn adversarial circuit breaker triggered; "
                            "manual clinical pharmacist review required."
                        ),
                    }
                )

        assert liaison_out is not None and auditor_out is not None  # noqa: S101
        assert liaison_tel is not None and auditor_tel is not None  # noqa: S101

        # Stage 5: GuardrailEngine FHIR R4 Overwrite + HMAC Signing + AuditLedger Persistence
        max_risk_score = max((a.risk_score for a in safety_out.alerts), default=1)
        if circuit_breaker_tripped:
            max_risk_score = 5

        remediation_plan = self._guardrail.enforce(
            plan_id=plan_id,
            idempotency_key=idempotency_key,
            patient_token=patient_token,
            action_type=liaison_out.recommended_action,
            risk_score=max_risk_score,
            risk_grade=liaison_out.overall_risk_grade,
            medications=intake_out.medications,
            alerts=safety_out.alerts,
            draft_execution_payload={"resources": list(liaison_out.fhir_resources)},
            dry_run=dry_run,
        )

        # Persist every stage + prompt version to the hash-chained AuditLedger.
        await self._record_step(
            plan_id=plan_id,
            step_suffix="intake",
            patient_token=patient_token,
            telemetry=intake_tel,
            safety=safety_out,
            payload=intake_out.model_dump(mode="json"),
            known_phi=known_phi,
        )
        await self._record_step(
            plan_id=plan_id,
            step_suffix="clinical",
            patient_token=patient_token,
            telemetry=clinical_tel,
            safety=safety_out,
            payload=clinical_out.model_dump(mode="json"),
            known_phi=known_phi,
        )
        await self._record_step(
            plan_id=plan_id,
            step_suffix="safety",
            patient_token=patient_token,
            telemetry=safety_tel,
            safety=safety_out,
            payload=safety_out.model_dump(mode="json"),
            known_phi=known_phi,
        )
        await self._record_step(
            plan_id=plan_id,
            step_suffix="insurance",
            patient_token=patient_token,
            telemetry=insurance_tel,
            safety=safety_out,
            payload=insurance_out.model_dump(mode="json"),
            known_phi=known_phi,
        )
        await self._record_step(
            plan_id=plan_id,
            step_suffix="auditor",
            patient_token=patient_token,
            telemetry=auditor_tel,
            safety=safety_out,
            payload=auditor_out.model_dump(mode="json"),
            known_phi=known_phi,
        )
        await self._record_step(
            plan_id=plan_id,
            step_suffix="liaison",
            patient_token=patient_token,
            telemetry=liaison_tel,
            safety=safety_out,
            payload={
                "liaison": liaison_out.model_dump(mode="json"),
                "plan_digest": remediation_plan.plan_digest,
                "circuit_breaker_tripped": circuit_breaker_tripped,
                "turn_count": turn_count,
            },
            known_phi=known_phi,
        )

        prompt_versions = {
            intake_tel.agent_name: intake_tel.prompt_version,
            clinical_tel.agent_name: clinical_tel.prompt_version,
            safety_tel.agent_name: safety_tel.prompt_version,
            insurance_tel.agent_name: insurance_tel.prompt_version,
            auditor_tel.agent_name: auditor_tel.prompt_version,
            liaison_tel.agent_name: liaison_tel.prompt_version,
        }
        tier_trace = {
            intake_tel.agent_name: intake_tel.tier_used,
            clinical_tel.agent_name: clinical_tel.tier_used,
            safety_tel.agent_name: safety_tel.tier_used,
            insurance_tel.agent_name: insurance_tel.tier_used,
            auditor_tel.agent_name: auditor_tel.tier_used,
            liaison_tel.agent_name: liaison_tel.tier_used,
        }

        return BlackboardState(
            plan_id=plan_id,
            idempotency_key=idempotency_key,
            patient_token=patient_token,
            intake=intake_out,
            clinical=clinical_out,
            safety=safety_out,
            insurance=insurance_out,
            auditor=auditor_out,
            liaison=liaison_out,
            remediation_plan=remediation_plan,
            turn_count=turn_count,
            circuit_breaker_tripped=circuit_breaker_tripped,
            prompt_versions=prompt_versions,
            tier_trace=tier_trace,
        )
