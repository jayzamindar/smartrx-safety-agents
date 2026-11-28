"""Benchmark and unit tests for deterministic clinical safety heuristics (TC-001 to TC-008)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from smartrx_safety_agents.heuristics import (
    CatalogNotFoundError,
    DeterministicClinicalEngine,
    PHIRedactor,
    load_catalog,
)
from smartrx_safety_agents.models.clinical import (
    ClinicalOutput,
    IntakeOutput,
    NormalizedMedication,
    PatientLabObservation,
    RiskGrade,
)


def _med(
    *,
    rxcui: str,
    scd_name: str,
    raw_name: str | None = None,
    is_nti: bool = False,
    ocr_confidence: float = 1.0,
) -> NormalizedMedication:
    return NormalizedMedication(
        rxcui=rxcui,
        scd_name=scd_name,
        raw_name=raw_name or scd_name,
        frequency="once daily",
        route="oral",
        is_nti=is_nti,
        ocr_confidence=ocr_confidence,
    )


def _clean_payer_plan(*rxcuis: str) -> dict[str, dict[str, object]]:
    return {
        rx: {
            "covered": True,
            "formulary_tier": 1,
            "estimated_copay_usd": 10.0,
            "requires_pa": False,
        }
        for rx in rxcuis
    }


def test_tc001_major_ddi_warfarin_amiodarone_triggers_red_hold() -> None:
    """TC-001: Major DDI (Warfarin + Amiodarone) triggers RED HOLD_PRESCRIPTION."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc001",
        medications=(
            _med(rxcui="703", scd_name="amiodarone 200 mg oral tablet", raw_name="amiodarone"),
        ),
        confidence=0.95,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc001",
        active_medications=(
            _med(
                rxcui="11289",
                scd_name="warfarin 5 mg oral tablet",
                raw_name="warfarin",
                is_nti=True,
            ),
        ),
        labs=(
            PatientLabObservation(
                loinc_code="1742-6",
                name="alt",
                value=22.0,
                unit="u/l",
                observed_at=datetime.now(UTC),
            ),
        ),
    )

    safety, _ = engine.evaluate(intake, clinical, payer_formulary=_clean_payer_plan("703", "11289"))

    assert safety.overall_risk_grade == RiskGrade.RED
    assert safety.recommended_action == "HOLD_PRESCRIPTION"
    assert any(
        a.rule_category == "DDI" and a.requires_npi_attestation and a.citation
        for a in safety.alerts
    )


def test_tc002_allergy_cross_reactivity_with_nfkc_normalization() -> None:
    """TC-002: Penicillin allergy (with NFKC fullwidth/nbsp) + Amoxicillin triggers RED HOLD."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc002",
        medications=(
            _med(rxcui="723", scd_name="amoxicillin 500 mg capsule", raw_name="amoxicillin"),
        ),
        confidence=0.98,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc002",
        allergies=("Ｐｅｎｉｃｉｌｌｉｎ\u00a0",),
    )

    safety, _ = engine.evaluate(intake, clinical, payer_formulary=_clean_payer_plan("723"))

    assert safety.overall_risk_grade == RiskGrade.RED
    assert safety.recommended_action == "HOLD_PRESCRIPTION"
    assert any(a.rule_category == "ALLERGY" and a.requires_npi_attestation for a in safety.alerts)


def test_tc003_missing_renal_labs_for_nti_or_dabigatran() -> None:
    """TC-003: Missing eGFR for Digoxin/Dabigatran triggers REQUEST_RENAL_HEPATIC_LABS."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc003",
        medications=(
            _med(rxcui="1037042", scd_name="dabigatran 150 mg capsule", raw_name="dabigatran"),
        ),
        confidence=0.95,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc003",
        egfr_ml_min=None,
        partial_ehr_record=True,
    )

    safety, _ = engine.evaluate(intake, clinical, payer_formulary=_clean_payer_plan("1037042"))

    assert safety.overall_risk_grade == RiskGrade.RED
    assert safety.recommended_action == "REQUEST_RENAL_HEPATIC_LABS"
    assert safety.missing_nti_labs is True


def test_tc004_low_ocr_confidence_on_nti_triggers_red_lock() -> None:
    """TC-004: Low OCR confidence (<0.70) on NTI Warfarin triggers Tier 1 RED HOLD_PRESCRIPTION."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc004",
        medications=(
            _med(
                rxcui="11289",
                scd_name="warfarin 5 mg oral tablet",
                raw_name="warfarin",
                is_nti=True,
                ocr_confidence=0.58,
            ),
        ),
        low_confidence_nti_detected=True,
        confidence=0.58,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc004",
        labs=(
            PatientLabObservation(
                loinc_code="1742-6",
                name="ast",
                value=20.0,
                unit="u/l",
                observed_at=datetime.now(UTC),
            ),
        ),
    )

    safety, _ = engine.evaluate(intake, clinical, payer_formulary=_clean_payer_plan("11289"))

    assert safety.overall_risk_grade == RiskGrade.RED
    assert safety.recommended_action == "HOLD_PRESCRIPTION"
    assert any(a.rule_category == "OCR_NTI" and a.requires_npi_attestation for a in safety.alerts)


def test_tc005_therapeutic_class_duplication_lipitor_atorvastatin() -> None:
    """TC-005: Lipitor + Atorvastatin duplication triggers YELLOW FLAG_DRUG_INTERACTION."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc005",
        medications=(
            _med(rxcui="83367", scd_name="lipitor 20 mg oral tablet", raw_name="lipitor"),
        ),
        confidence=0.95,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc005",
        active_medications=(
            _med(rxcui="83367", scd_name="atorvastatin 20 mg oral tablet", raw_name="atorvastatin"),
        ),
    )

    safety, _ = engine.evaluate(intake, clinical, payer_formulary=_clean_payer_plan("83367"))

    assert safety.overall_risk_grade == RiskGrade.YELLOW
    assert safety.recommended_action == "FLAG_DRUG_INTERACTION"
    assert any(a.rule_category == "DUPLICATION" for a in safety.alerts)


def test_tc005b_therapeutic_class_duplication_ace_inhibitors() -> None:
    """TC-005b: Lisinopril + Enalapril ACE-inhibitor class duplication triggers YELLOW."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc005b",
        medications=(
            _med(rxcui="29046", scd_name="lisinopril 10 mg oral tablet", raw_name="lisinopril"),
        ),
        confidence=0.96,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc005b",
        active_medications=(
            _med(rxcui="3827", scd_name="enalapril 10 mg oral tablet", raw_name="enalapril"),
        ),
    )

    safety, _ = engine.evaluate(
        intake, clinical, payer_formulary=_clean_payer_plan("29046", "3827")
    )

    assert safety.overall_risk_grade == RiskGrade.YELLOW
    assert safety.recommended_action == "FLAG_DRUG_INTERACTION"


def test_tc006_geriatric_beers_criteria_proposes_alternative() -> None:
    """TC-006: Geriatric (>=65) AGS Beer's Criteria triggers PROPOSE_THERAPEUTIC_ALTERNATIVE."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc006",
        medications=(
            _med(
                rxcui="3498", scd_name="diphenhydramine 25 mg capsule", raw_name="diphenhydramine"
            ),
        ),
        confidence=0.94,
    )
    clinical = ClinicalOutput(patient_token="pt_tc006")

    safety, _ = engine.evaluate(
        intake,
        clinical,
        patient_age=74,
        payer_formulary=_clean_payer_plan("3498"),
    )

    assert safety.overall_risk_grade == RiskGrade.YELLOW
    assert safety.recommended_action == "PROPOSE_THERAPEUTIC_ALTERNATIVE"
    assert any(
        a.rule_category == "BEERS_CRITERIA" and "PMID:37139824" in a.citation for a in safety.alerts
    )


def test_tc007_cms_formulary_fallback_and_prior_auth() -> None:
    """TC-007: Unavailable payer plan triggers CMS fallback and PA evaluation."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc007",
        medications=(
            _med(rxcui="1037042", scd_name="dabigatran 150 mg capsule", raw_name="dabigatran"),
        ),
        confidence=0.95,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc007",
        egfr_ml_min=65.0,
        labs=(
            PatientLabObservation(
                loinc_code="1742-6",
                name="alt",
                value=19.0,
                unit="u/l",
                observed_at=datetime.now(UTC),
            ),
        ),
    )

    safety, insurance = engine.evaluate(intake, clinical, payer_formulary=None)

    assert insurance.used_cms_fallback is True
    assert insurance.requires_pa is True
    assert len(insurance.alternatives) >= 1
    assert safety.overall_risk_grade == RiskGrade.YELLOW


def test_tc008_clean_reconciliation_approves_green() -> None:
    """TC-008: Clean reconciliation with zero conflicts and >=0.90 confidence returns GREEN."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_tc008",
        medications=(
            _med(rxcui="6809", scd_name="metformin 500 mg oral tablet", raw_name="metformin"),
        ),
        confidence=0.97,
    )
    clinical = ClinicalOutput(
        patient_token="pt_tc008",
        egfr_ml_min=82.0,
    )

    safety, insurance = engine.evaluate(
        intake,
        clinical,
        payer_formulary=_clean_payer_plan("6809"),
    )

    assert safety.overall_risk_grade == RiskGrade.GREEN
    assert safety.recommended_action == "APPROVE_RECONCILED_LIST"
    assert safety.alerts == ()
    assert insurance.used_cms_fallback is False


def test_renal_contraindication_and_hepatic_impairment_bounds() -> None:
    """Verify renal eGFR < contraindication threshold and hepatic impairment flags."""
    engine = DeterministicClinicalEngine()
    intake = IntakeOutput(
        patient_token="pt_renal",
        medications=(
            _med(rxcui="6809", scd_name="metformin 500 mg oral tablet", raw_name="metformin"),
        ),
        confidence=0.95,
    )
    clinical = ClinicalOutput(
        patient_token="pt_renal",
        egfr_ml_min=22.0,
        hepatic_impaired=True,
    )

    safety, _ = engine.evaluate(intake, clinical, payer_formulary=_clean_payer_plan("6809"))

    assert safety.overall_risk_grade == RiskGrade.RED
    assert safety.recommended_action == "HOLD_PRESCRIPTION"
    assert len(safety.alerts) == 2


def test_catalog_not_found_error_fail_closed(tmp_path: Path) -> None:
    """Missing or corrupted catalog must raise CatalogNotFoundError fail-closed."""
    missing = tmp_path / "nonexistent.json"
    with pytest.raises(CatalogNotFoundError):
        load_catalog(missing)

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CatalogNotFoundError):
        load_catalog(corrupt)


def test_phi_redactor_zero_leak_and_reversible_token_map() -> None:
    """PHIRedactor strips all PHI identifiers and supports local restoration."""
    redactor = PHIRedactor()
    raw = (
        "Patient: Jane Doe | MRN: MRN-99421 | SSN: 123-45-6789 | "
        "DOB: 1951-04-12 | Phone: (555) 234-5678 | Email: jane.doe@example.org"
    )
    result = redactor.redact(raw, known_names=("Jane Doe",), known_mrns=("MRN-99421",))

    assert result.redaction_count == 6
    assert not redactor.contains_phi(
        result.redacted_text,
        known_identifiers=("Jane Doe", "MRN-99421", "123-45-6789", "jane.doe@example.org"),
    )
    assert redactor.restore(result.redacted_text, result.token_map) == raw
    assert redactor.tokenize_patient_id("MRN-99421") == redactor.tokenize_patient_id("MRN-99421")
