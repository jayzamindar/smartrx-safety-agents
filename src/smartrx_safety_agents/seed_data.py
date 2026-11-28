"""Synthetic HL7 FHIR R4 bundle seeder & TC-001..TC-008 benchmark runner (zero PHI)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import Field

from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor
from smartrx_safety_agents.models.clinical import (
    ActionType,
    ClinicalOutput,
    IntakeOutput,
    NormalizedMedication,
    RiskGrade,
    StrictClinicalModel,
)


class BenchmarkScenario(StrictClinicalModel):
    """Synthetic zero-PHI benchmark scenario for TC-001 through TC-008."""

    tc_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    patient_token: str = Field(..., min_length=1)
    patient_age: int = Field(..., ge=0, le=120)
    intake: IntakeOutput
    clinical: ClinicalOutput
    payer_formulary: dict[str, dict[str, Any]] | None = Field(default=None)
    expected_risk_grade: RiskGrade
    expected_action: ActionType | None = Field(default=None)
    expected_cms_fallback: bool = Field(default=False)


def _med(
    rxcui: str,
    name: str,
    *,
    dose_mg: float = 5.0,
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


def build_benchmark_scenarios() -> tuple[BenchmarkScenario, ...]:
    """Construct deterministic synthetic scenarios TC-001 through TC-008."""
    pts = [f"pt_tc00{i}" for i in range(1, 9)]
    return (
        BenchmarkScenario(
            tc_id="TC-001",
            title="Major DDI: Warfarin + Amiodarone",
            patient_token=pts[0],
            patient_age=64,
            intake=IntakeOutput(
                patient_token=pts[0],
                medications=(_med("11289", "warfarin sodium 5 mg", is_nti=True),),
                confidence=0.98,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[0],
                active_medications=(_med("703", "amiodarone hydrochloride 200 mg", dose_mg=200.0),),
                egfr_ml_min=70.0,
            ),
            expected_risk_grade=RiskGrade.RED,
            expected_action="HOLD_PRESCRIPTION",
        ),
        BenchmarkScenario(
            tc_id="TC-002",
            title="Allergy Cross-Reactivity: Penicillin + Amoxicillin",
            patient_token=pts[1],
            patient_age=42,
            intake=IntakeOutput(
                patient_token=pts[1],
                medications=(_med("723", "amoxicillin 500 mg", dose_mg=500.0),),
                confidence=0.97,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[1],
                allergies=("penicillin",),
                egfr_ml_min=90.0,
            ),
            expected_risk_grade=RiskGrade.RED,
            expected_action="HOLD_PRESCRIPTION",
        ),
        BenchmarkScenario(
            tc_id="TC-003",
            title="Missing eGFR Lab for NTI Digoxin",
            patient_token=pts[2],
            patient_age=71,
            intake=IntakeOutput(
                patient_token=pts[2],
                medications=(_med("3407", "digoxin 0.125 mg", dose_mg=0.125, is_nti=True),),
                confidence=0.96,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[2],
                egfr_ml_min=None,
            ),
            expected_risk_grade=RiskGrade.RED,
            expected_action="REQUEST_RENAL_HEPATIC_LABS",
        ),
        BenchmarkScenario(
            tc_id="TC-004",
            title="Low OCR Confidence on NTI Warfarin",
            patient_token=pts[3],
            patient_age=58,
            intake=IntakeOutput(
                patient_token=pts[3],
                medications=(
                    _med("11289", "warfarin sodium 5 mg", is_nti=True, ocr_confidence=0.55),
                ),
                low_confidence_nti_detected=True,
                confidence=0.55,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[3],
                egfr_ml_min=75.0,
            ),
            expected_risk_grade=RiskGrade.RED,
            expected_action="HOLD_PRESCRIPTION",
        ),
        BenchmarkScenario(
            tc_id="TC-005",
            title="Therapeutic Class Duplication: Lisinopril + Enalapril",
            patient_token=pts[4],
            patient_age=55,
            intake=IntakeOutput(
                patient_token=pts[4],
                medications=(_med("29046", "lisinopril 10 mg", dose_mg=10.0),),
                confidence=0.98,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[4],
                active_medications=(_med("3827", "enalapril 10 mg", dose_mg=10.0),),
                egfr_ml_min=80.0,
            ),
            expected_risk_grade=RiskGrade.YELLOW,
            expected_action="FLAG_DRUG_INTERACTION",
        ),
        BenchmarkScenario(
            tc_id="TC-006",
            title="Geriatric AGS Beer's Criteria: Diphenhydramine",
            patient_token=pts[5],
            patient_age=74,
            intake=IntakeOutput(
                patient_token=pts[5],
                medications=(_med("3498", "diphenhydramine 25 mg", dose_mg=25.0),),
                confidence=0.98,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[5],
                egfr_ml_min=70.0,
            ),
            expected_risk_grade=RiskGrade.YELLOW,
            expected_action="PROPOSE_THERAPEUTIC_ALTERNATIVE",
        ),
        BenchmarkScenario(
            tc_id="TC-007",
            title="Payer Formulary Unavailable -> CMS Fallback",
            patient_token=pts[6],
            patient_age=50,
            intake=IntakeOutput(
                patient_token=pts[6],
                medications=(_med("29046", "lisinopril 10 mg", dose_mg=10.0),),
                confidence=0.98,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[6],
                egfr_ml_min=85.0,
            ),
            payer_formulary=None,
            expected_risk_grade=RiskGrade.YELLOW,
            expected_cms_fallback=True,
        ),
        BenchmarkScenario(
            tc_id="TC-008",
            title="Clean Reconciliation -> GREEN Auto-Verify",
            patient_token=pts[7],
            patient_age=48,
            intake=IntakeOutput(
                patient_token=pts[7],
                medications=(_med("29046", "lisinopril 10 mg", dose_mg=10.0),),
                confidence=0.99,
            ),
            clinical=ClinicalOutput(
                patient_token=pts[7],
                egfr_ml_min=95.0,
            ),
            payer_formulary={
                "29046": {"covered": True, "tier": 1, "copay": 10.0, "requires_pa": False}
            },
            expected_risk_grade=RiskGrade.GREEN,
            expected_action="APPROVE_RECONCILED_LIST",
        ),
    )


def build_fhir_transaction_bundle(scenario: BenchmarkScenario) -> dict[str, Any]:
    """Generate a synthetic zero-PHI HL7 FHIR R4 transaction Bundle for a scenario."""
    entries: list[dict[str, Any]] = [
        {
            "resource": {
                "resourceType": "Patient",
                "id": scenario.patient_token,
                "identifier": [
                    {
                        "system": "urn:smartrx:synthetic-token",
                        "value": scenario.patient_token,
                    }
                ],
                "active": True,
            },
            "request": {"method": "PUT", "url": f"Patient/{scenario.patient_token}"},
        }
    ]

    for idx, allergy in enumerate(scenario.clinical.allergies, start=1):
        entries.append(
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "id": f"{scenario.patient_token}-allergy-{idx}",
                    "patient": {"reference": f"Patient/{scenario.patient_token}"},
                    "code": {"text": allergy},
                },
                "request": {
                    "method": "PUT",
                    "url": f"AllergyIntolerance/{scenario.patient_token}-allergy-{idx}",
                },
            }
        )

    for idx, med in enumerate(scenario.clinical.active_medications, start=1):
        entries.append(
            {
                "resource": {
                    "resourceType": "MedicationStatement",
                    "id": f"{scenario.patient_token}-medstmt-{idx}",
                    "status": "active",
                    "subject": {"reference": f"Patient/{scenario.patient_token}"},
                    "medicationCodeableConcept": {
                        "coding": [
                            {
                                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                "code": med.rxcui,
                                "display": med.scd_name,
                            }
                        ]
                    },
                },
                "request": {
                    "method": "PUT",
                    "url": f"MedicationStatement/{scenario.patient_token}-medstmt-{idx}",
                },
            }
        )

    if scenario.clinical.egfr_ml_min is not None:
        entries.append(
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": f"{scenario.patient_token}-egfr",
                    "status": "final",
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "33914-3",
                                "display": "eGFR",
                            }
                        ]
                    },
                    "subject": {"reference": f"Patient/{scenario.patient_token}"},
                    "valueQuantity": {
                        "value": scenario.clinical.egfr_ml_min,
                        "unit": "mL/min/1.73m2",
                    },
                },
                "request": {
                    "method": "PUT",
                    "url": f"Observation/{scenario.patient_token}-egfr",
                },
            }
        )

    for idx, med in enumerate(scenario.intake.medications, start=1):
        entries.append(
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id": f"{scenario.patient_token}-medreq-{idx}",
                    "status": "active",
                    "intent": "order",
                    "subject": {"reference": f"Patient/{scenario.patient_token}"},
                    "medicationCodeableConcept": {
                        "coding": [
                            {
                                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                "code": med.rxcui,
                                "display": med.scd_name,
                            }
                        ]
                    },
                },
                "request": {
                    "method": "PUT",
                    "url": f"MedicationRequest/{scenario.patient_token}-medreq-{idx}",
                },
            }
        )

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": entries,
    }
    if PHIRedactor.contains_phi(json.dumps(bundle)):
        raise ValueError(f"Synthetic bundle for {scenario.tc_id} unexpectedly triggered PHI check.")
    return bundle


def post_bundle_to_hapi_fhir(
    bundle: dict[str, Any],
    *,
    fhir_base_url: str = "http://localhost:8080/fhir",
    client: httpx.Client | None = None,
) -> httpx.Response:
    """POST a synthetic HL7 FHIR R4 transaction bundle to a HAPI FHIR endpoint."""
    url = fhir_base_url.rstrip("/")
    headers = {"Content-Type": "application/fhir+json"}
    if client is not None:
        resp = client.post(url, json=bundle, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp
    with httpx.Client(timeout=10.0) as owned_client:
        resp = owned_client.post(url, json=bundle, headers=headers)
        resp.raise_for_status()
        return resp


def run_benchmark_suite(
    engine: DeterministicClinicalEngine | None = None,
) -> list[dict[str, Any]]:
    """Run all 8 benchmark scenarios TC-001..TC-008 against DeterministicClinicalEngine."""
    det_engine = engine or DeterministicClinicalEngine()
    results: list[dict[str, Any]] = []
    for scenario in build_benchmark_scenarios():
        safety, insurance = det_engine.evaluate(
            scenario.intake,
            scenario.clinical,
            patient_age=scenario.patient_age,
            payer_formulary=scenario.payer_formulary,
        )
        grade_ok = safety.overall_risk_grade == scenario.expected_risk_grade
        action_ok = (
            scenario.expected_action is None
            or safety.recommended_action == scenario.expected_action
        )
        cms_ok = (not scenario.expected_cms_fallback) or insurance.used_cms_fallback
        results.append(
            {
                "tc_id": scenario.tc_id,
                "passed": grade_ok and action_ok and cms_ok,
                "risk_grade": safety.overall_risk_grade.value,
                "recommended_action": safety.recommended_action,
                "used_cms_fallback": insurance.used_cms_fallback,
            }
        )
    return results
