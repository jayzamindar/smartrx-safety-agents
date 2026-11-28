"""Strict Pydantic v2 clinical medication reconciliation and 6-agent output schemas."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

ActionType = Literal[
    "APPROVE_RECONCILED_LIST",
    "FLAG_DRUG_INTERACTION",
    "HOLD_PRESCRIPTION",
    "PROPOSE_THERAPEUTIC_ALTERNATIVE",
    "REQUEST_RENAL_HEPATIC_LABS",
    "ESCALATE_TO_CLINICAL_PHARMACIST",
]

ALLOWED_ACTION_TYPES: frozenset[str] = frozenset(get_args(ActionType))


class RiskGrade(StrEnum):
    """Three-tier HITL clinical safety risk grade."""

    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class AgentStatus(StrEnum):
    """Execution status for hierarchical-parallel clinical agents."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    HALT_FOR_HUMAN = "HALT_FOR_HUMAN"
    FAILED = "FAILED"


_ZERO_WIDTH_TRANS = str.maketrans("", "", "\u200b\u200c\u200d\ufeff\u00ad")


def normalize_clinical_identifier(value: str) -> str:
    """Normalize clinical identifiers/codes via Unicode NFKC, zero-width strip, and casefold."""
    cleaned = value.translate(_ZERO_WIDTH_TRANS)
    return unicodedata.normalize("NFKC", cleaned).strip().casefold()


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_clinical_identifier(value)
    return normalized if normalized else None


def _normalize_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_clinical_identifier(v) for v in values if v.strip())


class StrictClinicalModel(BaseModel):
    """Base contract enforcing strict immutability and zero extra fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class NormalizedMedication(StrictClinicalModel):
    """Normalized medication representation mapped to RxNorm/SNOMED/NDC."""

    rxcui: str = Field(..., min_length=1)
    scd_name: str = Field(..., min_length=1)
    raw_name: str = Field(..., min_length=1)
    snomed_code: str | None = Field(default=None)
    ndc: str | None = Field(default=None)
    dose_mg: float | None = Field(default=None, ge=0.0)
    frequency: str = Field(..., min_length=1)
    route: str = Field(..., min_length=1)
    is_nti: bool = Field(default=False)
    ocr_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("rxcui", "scd_name", "raw_name", "frequency", "route", mode="before")
    @classmethod
    def _normalize_required_str(cls, v: object) -> object:
        if isinstance(v, str):
            return normalize_clinical_identifier(v)
        return v

    @field_validator("snomed_code", "ndc", mode="before")
    @classmethod
    def _normalize_optional_str(cls, v: object) -> object:
        if isinstance(v, str):
            return _normalize_optional(v)
        return v


class IntakeOutput(StrictClinicalModel):
    """Output contract for Agent 2: Intake & Terminology Agent."""

    patient_token: str = Field(..., min_length=1)
    medications: tuple[NormalizedMedication, ...] = Field(default_factory=tuple)
    low_confidence_nti_detected: bool = Field(default=False)
    discrepancies: tuple[str, ...] = Field(default_factory=tuple)
    confidence: float = Field(..., ge=0.0, le=1.0)


class PatientLabObservation(StrictClinicalModel):
    """Normalized renal/hepatic laboratory observation."""

    loinc_code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    value: float | None = Field(default=None)
    unit: str = Field(..., min_length=1)
    observed_at: datetime

    @field_validator("loinc_code", "name", "unit", mode="before")
    @classmethod
    def _normalize_lab_fields(cls, v: object) -> object:
        if isinstance(v, str):
            return normalize_clinical_identifier(v)
        return v


class ClinicalOutput(StrictClinicalModel):
    """Output contract for Agent 3: Clinical History Agent."""

    patient_token: str = Field(..., min_length=1)
    active_medications: tuple[NormalizedMedication, ...] = Field(default_factory=tuple)
    allergies: tuple[str, ...] = Field(default_factory=tuple)
    labs: tuple[PatientLabObservation, ...] = Field(default_factory=tuple)
    egfr_ml_min: float | None = Field(default=None, ge=0.0)
    hepatic_impaired: bool = Field(default=False)
    partial_ehr_record: bool = Field(default=False)

    @field_validator("allergies", mode="before")
    @classmethod
    def _normalize_allergies(cls, v: object) -> object:
        if isinstance(v, (list, tuple)):
            return _normalize_tuple(tuple(str(item) for item in v))
        return v


class ClinicalAlert(StrictClinicalModel):
    """Deterministic clinical safety finding with verifiable source citation."""

    alert_id: str = Field(..., min_length=1)
    rule_category: Literal["DDI", "ALLERGY", "DUPLICATION", "DOSING", "BEERS_CRITERIA", "OCR_NTI"]
    severity: Literal["contraindicated", "major", "moderate", "minor"]
    risk_score: int = Field(..., ge=1, le=5)
    risk_grade: RiskGrade
    recommended_action: ActionType
    affected_rxcuis: tuple[str, ...] = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    citation: str = Field(..., min_length=1)
    requires_npi_attestation: bool = Field(default=False)

    @field_validator("affected_rxcuis", mode="before")
    @classmethod
    def _normalize_rxcuis(cls, v: object) -> object:
        if isinstance(v, (list, tuple)):
            return _normalize_tuple(tuple(str(item) for item in v))
        return v


class SafetyOutput(StrictClinicalModel):
    """Output contract for Agent 4: Safety & Contraindication Agent."""

    alerts: tuple[ClinicalAlert, ...] = Field(default_factory=tuple)
    overall_risk_grade: RiskGrade
    recommended_action: ActionType
    missing_nti_labs: bool = Field(default=False)
    quarantined: bool = Field(default=False)
    quarantine_reason: str | None = Field(default=None)


class FormularyAlternative(StrictClinicalModel):
    """Covered therapeutic alternative from payer or CMS fallback formulary."""

    rxcui: str = Field(..., min_length=1)
    drug_name: str = Field(..., min_length=1)
    formulary_tier: int = Field(..., ge=1, le=5)
    estimated_copay_usd: float = Field(..., ge=0.0)
    requires_pa: bool = Field(default=False)

    @field_validator("rxcui", "drug_name", mode="before")
    @classmethod
    def _normalize_alt(cls, v: object) -> object:
        if isinstance(v, str):
            return normalize_clinical_identifier(v)
        return v


class InsuranceOutput(StrictClinicalModel):
    """Output contract for Agent 5: Insurance & Formulary Agent."""

    covered: bool
    formulary_tier: int = Field(..., ge=1, le=5)
    estimated_copay_usd: float = Field(..., ge=0.0)
    requires_pa: bool = Field(default=False)
    pa_deadline: datetime | None = Field(default=None)
    used_cms_fallback: bool = Field(default=False)
    alternatives: tuple[FormularyAlternative, ...] = Field(default_factory=tuple)


class AuditorOutput(StrictClinicalModel):
    """Output contract for Agent 6a: Adversarial Hallucination & PHI Critic."""

    hallucination_detected: bool = Field(default=False)
    phi_leak_detected: bool = Field(default=False)
    unverified_claims: tuple[str, ...] = Field(default_factory=tuple)
    verified_citations: tuple[str, ...] = Field(default_factory=tuple)
    audit_passed: bool


class LiaisonOutput(StrictClinicalModel):
    """Output contract for Agent 6b: Pharmacist Liaison & HITL Compiler."""

    plan_id: str = Field(..., min_length=1)
    patient_token: str = Field(..., min_length=1)
    status: AgentStatus
    overall_risk_grade: RiskGrade
    recommended_action: ActionType
    fhir_resources: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    rollback_steps: tuple[str, ...] = Field(default_factory=tuple)
    pharmacist_summary: str = Field(..., min_length=1)
    requires_hitl_attestation: bool = Field(default=False)
    confidence: float = Field(..., ge=0.0, le=1.0)
