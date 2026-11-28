"""Unit tests for strict clinical Pydantic v2 models and fail-closed config."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from smartrx_safety_agents.config import Settings
from smartrx_safety_agents.models import (
    ALLOWED_ACTION_TYPES,
    AgentStatus,
    AuditorOutput,
    ClinicalAlert,
    ClinicalOutput,
    FormularyAlternative,
    InsuranceOutput,
    IntakeOutput,
    LiaisonOutput,
    NormalizedMedication,
    PatientLabObservation,
    RiskGrade,
    SafetyOutput,
)


def _sample_med() -> NormalizedMedication:
    return NormalizedMedication(
        rxcui="11289",
        scd_name="Warfarin Sodium 5 MG Oral Tablet",
        raw_name="Warfarin 5mg",
        snomed_code="372756006",
        ndc="00056-0172-70",
        dose_mg=5.0,
        frequency="once daily",
        route="oral",
        is_nti=True,
        ocr_confidence=0.95,
    )


def test_action_type_allowlist_exact() -> None:
    assert ALLOWED_ACTION_TYPES == frozenset(
        {
            "APPROVE_RECONCILED_LIST",
            "FLAG_DRUG_INTERACTION",
            "HOLD_PRESCRIPTION",
            "PROPOSE_THERAPEUTIC_ALTERNATIVE",
            "REQUEST_RENAL_HEPATIC_LABS",
            "ESCALATE_TO_CLINICAL_PHARMACIST",
        }
    )


def test_strict_extra_forbid_and_frozen() -> None:
    med = _sample_med()
    with pytest.raises(ValidationError):
        NormalizedMedication(
            rxcui="11289",
            scd_name="Warfarin Sodium 5 MG Oral Tablet",
            raw_name="Warfarin 5mg",
            frequency="daily",
            route="oral",
            unexpected_field="reject_me",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        med.dose_mg = 10.0  # type: ignore[misc]


def test_unicode_nfkc_normalization() -> None:
    # Fullwidth "Warfarin" + non-breaking space
    med = NormalizedMedication(
        rxcui="\uff11\uff11\uff12\uff18\uff19\u00a0",
        scd_name="  \uff37\uff41\uff52\uff46\uff41\uff52\uff49\uff4e Sodium 5 MG  ",
        raw_name="WARFARIN",
        snomed_code=" \uff13\uff17\uff12\uff17\uff15\uff16\uff10\uff10\uff16 ",
        frequency="DAILY",
        route="ORAL",
    )
    assert med.rxcui == "11289"
    assert med.scd_name == "warfarin sodium 5 mg"
    assert med.raw_name == "warfarin"
    assert med.snomed_code == "372756006"
    assert med.frequency == "daily"
    assert med.route == "oral"


def test_intake_and_clinical_outputs() -> None:
    med = _sample_med()
    intake = IntakeOutput(
        patient_token="pt_tok_001",
        medications=(med,),
        low_confidence_nti_detected=False,
        discrepancies=(),
        confidence=0.96,
    )
    assert intake.medications[0].rxcui == "11289"

    with pytest.raises(ValidationError):
        IntakeOutput(
            patient_token="pt_tok_001",
            confidence=1.5,
        )

    lab = PatientLabObservation(
        loinc_code=" 33914-3 ",
        name=" eGFR ",
        value=42.0,
        unit=" mL/min/1.73m2 ",
        observed_at=datetime.now(UTC),
    )
    clinical = ClinicalOutput(
        patient_token="pt_tok_001",
        active_medications=(med,),
        allergies=(" \uff30\uff45\uff4e\uff49\uff43\uff49\uff4c\uff4c\uff49\uff4e ",),
        labs=(lab,),
        egfr_ml_min=42.0,
        hepatic_impaired=False,
        partial_ehr_record=False,
    )
    assert clinical.allergies == ("penicillin",)
    assert clinical.labs[0].loinc_code == "33914-3"


def test_safety_output_and_invalid_action_rejected() -> None:
    alert = ClinicalAlert(
        alert_id="ALT-001",
        rule_category="DDI",
        severity="major",
        risk_score=5,
        risk_grade=RiskGrade.RED,
        recommended_action="HOLD_PRESCRIPTION",
        affected_rxcuis=("11289", "1191"),
        rationale="Major bleeding risk with concurrent Warfarin and Aspirin.",
        citation="RxNorm:11289-1191 | PMID:12345678",
        requires_npi_attestation=True,
    )
    safety = SafetyOutput(
        alerts=(alert,),
        overall_risk_grade=RiskGrade.RED,
        recommended_action="ESCALATE_TO_CLINICAL_PHARMACIST",
        missing_nti_labs=False,
        quarantined=False,
    )
    assert safety.overall_risk_grade == RiskGrade.RED

    with pytest.raises(ValidationError):
        ClinicalAlert(
            alert_id="ALT-BAD",
            rule_category="DDI",
            severity="major",
            risk_score=5,
            risk_grade=RiskGrade.RED,
            recommended_action="TERMINATE_INSTANCE",  # type: ignore[arg-type]
            affected_rxcuis=("11289",),
            rationale="Invalid action.",
            citation="RxNorm:11289",
        )

    with pytest.raises(ValidationError):
        SafetyOutput(
            overall_risk_grade=RiskGrade.GREEN,
            recommended_action="APPROVE_RECONCILED_LIST",
            extra_field=True,  # type: ignore[call-arg]
        )


def test_insurance_auditor_and_liaison_outputs() -> None:
    alt = FormularyAlternative(
        rxcui="1364430",
        drug_name="Apixaban",
        formulary_tier=2,
        estimated_copay_usd=35.0,
        requires_pa=True,
    )
    insurance = InsuranceOutput(
        covered=True,
        formulary_tier=2,
        estimated_copay_usd=35.0,
        requires_pa=True,
        used_cms_fallback=True,
        alternatives=(alt,),
    )
    assert insurance.used_cms_fallback is True

    with pytest.raises(ValidationError):
        InsuranceOutput(
            covered=True,
            formulary_tier=6,
            estimated_copay_usd=10.0,
        )

    auditor = AuditorOutput(
        hallucination_detected=False,
        phi_leak_detected=False,
        unverified_claims=(),
        verified_citations=("PMID:12345678",),
        audit_passed=True,
    )
    assert auditor.audit_passed is True

    liaison = LiaisonOutput(
        plan_id="plan-0001",
        patient_token="pt_tok_001",
        status=AgentStatus.HALT_FOR_HUMAN,
        overall_risk_grade=RiskGrade.RED,
        recommended_action="HOLD_PRESCRIPTION",
        fhir_resources=({"resourceType": "DetectedIssue", "status": "final"},),
        rollback_steps=("Cancel pending MedicationRequest order",),
        pharmacist_summary="Hold Warfarin pending DDI review.",
        requires_hitl_attestation=True,
        confidence=0.92,
    )
    assert liaison.status == AgentStatus.HALT_FOR_HUMAN


def test_settings_fail_closed_in_production() -> None:
    dev_settings = Settings(environment="development")
    assert dev_settings.gemini_model_name == "gemini-3.8-flash-high"

    with pytest.raises(RuntimeError):
        Settings(environment="production")

    with pytest.raises(RuntimeError):
        Settings(
            environment="development",
            require_auth=True,
            mcp_api_key="short",  # type: ignore[arg-type]
        )

    prod_settings = Settings(
        environment="production",
        plan_signing_secret="super-strong-signing-secret-123456",  # type: ignore[arg-type]
        smartrx_safety_agents_webhook_secret="super-strong-webhook-secret-123456",  # type: ignore[arg-type]
        mcp_api_key="super-strong-mcp-api-key-123456",  # type: ignore[arg-type]
    )
    assert prod_settings.max_output_tokens == 8192
