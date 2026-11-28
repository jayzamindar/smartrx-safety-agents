"""Deterministic HL7 FHIR R4 JSON payload generators (zero LLM command synthesis)."""

from __future__ import annotations

from typing import Any

from smartrx_safety_agents.models.clinical import (
    ALLOWED_ACTION_TYPES,
    ActionType,
    ClinicalAlert,
    NormalizedMedication,
)

_RXNORM_SYSTEM = "http://www.nlm.nih.gov/research/umls/rxnorm"


def _validate_identifier(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned or "*" in cleaned:
        raise ValueError(f"Invalid or wildcard clinical identifier for {field_name}: {value!r}")
    return cleaned


def build_medication_request(
    med: NormalizedMedication,
    *,
    patient_token: str,
    status: str = "active",
) -> dict[str, Any]:
    """Build a deterministic HL7 FHIR R4 MedicationRequest resource."""
    safe_patient = _validate_identifier(patient_token, "patient_token")
    safe_rxcui = _validate_identifier(med.rxcui, "rxcui")
    return {
        "resourceType": "MedicationRequest",
        "status": status,
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": _RXNORM_SYSTEM,
                    "code": safe_rxcui,
                    "display": med.scd_name,
                }
            ],
            "text": med.scd_name,
        },
        "subject": {"reference": f"Patient/{safe_patient}"},
        "dosageInstruction": [
            {
                "text": f"{med.frequency} via {med.route}",
            }
        ],
    }


def build_detected_issue(
    alert: ClinicalAlert,
    *,
    patient_token: str,
) -> dict[str, Any]:
    """Build a deterministic HL7 FHIR R4 DetectedIssue resource."""
    safe_patient = _validate_identifier(patient_token, "patient_token")
    fhir_severity = (
        "high"
        if alert.severity in ("contraindicated", "major")
        else ("moderate" if alert.severity == "moderate" else "low")
    )
    return {
        "resourceType": "DetectedIssue",
        "id": _validate_identifier(alert.alert_id, "alert_id"),
        "status": "preliminary",
        "severity": fhir_severity,
        "code": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": alert.rule_category,
                    "display": alert.recommended_action,
                }
            ]
        },
        "patient": {"reference": f"Patient/{safe_patient}"},
        "detail": alert.rationale,
        "reference": alert.citation,
    }


def build_clinical_task(
    *,
    patient_token: str,
    action_type: ActionType,
    description: str,
    priority: str = "urgent",
) -> dict[str, Any]:
    """Build a deterministic HL7 FHIR R4 Task resource for pharmacist escalation or labs."""
    safe_patient = _validate_identifier(patient_token, "patient_token")
    if action_type not in ALLOWED_ACTION_TYPES:
        raise ValueError(f"Unallowlisted ActionType: {action_type!r}")
    return {
        "resourceType": "Task",
        "status": "requested",
        "intent": "order",
        "priority": priority,
        "code": {
            "coding": [
                {
                    "system": "https://smartrx.local/fhir/CodeSystem/clinical-action",
                    "code": action_type,
                    "display": action_type.replace("_", " ").title(),
                }
            ]
        },
        "description": description,
        "for": {"reference": f"Patient/{safe_patient}"},
    }


def generate_fhir_payload(
    action_type: ActionType,
    *,
    patient_token: str,
    medications: tuple[NormalizedMedication, ...] = (),
    alerts: tuple[ClinicalAlert, ...] = (),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Deterministically generate a complete HL7 FHIR R4 Bundle for an ActionType."""
    if action_type not in ALLOWED_ACTION_TYPES:
        raise ValueError(f"Invalid ActionType for FHIR generation: {action_type!r}")

    safe_patient = _validate_identifier(patient_token, "patient_token")
    entries: list[dict[str, Any]] = []

    med_status = "on-hold" if action_type == "HOLD_PRESCRIPTION" else "active"
    for med in medications:
        entries.append(
            {
                "resource": build_medication_request(
                    med, patient_token=safe_patient, status=med_status
                )
            }
        )

    for alert in alerts:
        entries.append({"resource": build_detected_issue(alert, patient_token=safe_patient)})

    if action_type in (
        "HOLD_PRESCRIPTION",
        "REQUEST_RENAL_HEPATIC_LABS",
        "ESCALATE_TO_CLINICAL_PHARMACIST",
        "PROPOSE_THERAPEUTIC_ALTERNATIVE",
    ):
        priority = "stat" if action_type == "HOLD_PRESCRIPTION" else "urgent"
        entries.append(
            {
                "resource": build_clinical_task(
                    patient_token=safe_patient,
                    action_type=action_type,
                    description=f"Deterministic clinical action: {action_type}",
                    priority=priority,
                )
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "collection" if dry_run else "transaction",
        "dryRun": dry_run,
        "entry": entries,
    }
