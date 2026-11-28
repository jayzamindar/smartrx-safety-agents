"""Unified deterministic clinical safety orchestrator (Tertiary SRE Engine)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from smartrx_safety_agents.heuristics.allergy_checker import AllergyChecker
from smartrx_safety_agents.heuristics.ddi_engine import DDIEngine, DrugCatalog, load_catalog
from smartrx_safety_agents.heuristics.dosing_validator import DosingValidator
from smartrx_safety_agents.heuristics.formulary_checker import FormularyChecker
from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor
from smartrx_safety_agents.models.clinical import (
    ALLOWED_ACTION_TYPES,
    ActionType,
    ClinicalAlert,
    ClinicalOutput,
    InsuranceOutput,
    IntakeOutput,
    NormalizedMedication,
    RiskGrade,
    SafetyOutput,
)

_ACTION_PRIORITY: dict[ActionType, int] = {
    "HOLD_PRESCRIPTION": 6,
    "ESCALATE_TO_CLINICAL_PHARMACIST": 5,
    "REQUEST_RENAL_HEPATIC_LABS": 4,
    "PROPOSE_THERAPEUTIC_ALTERNATIVE": 3,
    "FLAG_DRUG_INTERACTION": 2,
    "APPROVE_RECONCILED_LIST": 1,
}


class DeterministicClinicalEngine:
    """Orchestrates all 5 deterministic clinical safety checkers offline."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog: DrugCatalog = load_catalog(catalog_path)
        self.phi_redactor = PHIRedactor()
        self.ddi_engine = DDIEngine(self.catalog)
        self.allergy_checker = AllergyChecker(self.catalog)
        self.dosing_validator = DosingValidator(self.catalog)
        self.formulary_checker = FormularyChecker(self.catalog)

    def evaluate(
        self,
        intake: IntakeOutput,
        clinical: ClinicalOutput,
        *,
        patient_age: int | None = None,
        payer_formulary: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[SafetyOutput, InsuranceOutput]:
        """Run all deterministic safety and formulary checks and compute RiskGrade/ActionType."""
        combined_meds: tuple[NormalizedMedication, ...] = (
            intake.medications + clinical.active_medications
        )

        alerts: list[ClinicalAlert] = []
        alerts.extend(self.ddi_engine.check(combined_meds))
        alerts.extend(self.allergy_checker.check(combined_meds, clinical.allergies))
        alerts.extend(self.dosing_validator.check(combined_meds, clinical, patient_age=patient_age))

        insurance = self.formulary_checker.check(
            intake.medications or combined_meds,
            payer_formulary=payer_formulary,
        )

        overall_grade = self._compute_overall_grade(alerts, intake, insurance)
        recommended_action = self._select_action(alerts, overall_grade)
        missing_nti_labs = any(a.recommended_action == "REQUEST_RENAL_HEPATIC_LABS" for a in alerts)

        quarantined = recommended_action not in ALLOWED_ACTION_TYPES
        quarantine_reason = "INVALID_ACTION_ENUM_TYPE" if quarantined else None

        safety = SafetyOutput(
            alerts=tuple(alerts),
            overall_risk_grade=overall_grade,
            recommended_action=recommended_action,
            missing_nti_labs=missing_nti_labs,
            quarantined=quarantined,
            quarantine_reason=quarantine_reason,
        )
        return safety, insurance

    @staticmethod
    def _compute_overall_grade(
        alerts: list[ClinicalAlert],
        intake: IntakeOutput,
        insurance: InsuranceOutput,
    ) -> RiskGrade:
        if (
            any(a.risk_grade == RiskGrade.RED for a in alerts)
            or intake.confidence < 0.70
            or intake.low_confidence_nti_detected
        ):
            return RiskGrade.RED
        if (
            any(a.risk_grade == RiskGrade.YELLOW for a in alerts)
            or intake.confidence < 0.90
            or insurance.requires_pa
            or insurance.used_cms_fallback
        ):
            return RiskGrade.YELLOW
        return RiskGrade.GREEN

    @staticmethod
    def _select_action(alerts: list[ClinicalAlert], overall_grade: RiskGrade) -> ActionType:
        if not alerts:
            if overall_grade == RiskGrade.RED:
                return "HOLD_PRESCRIPTION"
            if overall_grade == RiskGrade.YELLOW:
                return "FLAG_DRUG_INTERACTION"
            return "APPROVE_RECONCILED_LIST"
        best = max(alerts, key=lambda a: _ACTION_PRIORITY[a.recommended_action])
        return best.recommended_action
