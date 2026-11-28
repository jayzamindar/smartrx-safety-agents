"""Deterministic clinical rollback and contingency step synthesis."""

from __future__ import annotations

from smartrx_safety_agents.models.clinical import ALLOWED_ACTION_TYPES, ActionType

_ROLLBACK_TEMPLATES: dict[ActionType, tuple[str, ...]] = {
    "APPROVE_RECONCILED_LIST": (
        "Revert EHR MedicationReconciliation commit using prior BPMH snapshot ID.",
        "Notify prescribing clinician of reconciliation status rollback.",
    ),
    "FLAG_DRUG_INTERACTION": (
        "Dismiss or resolve DetectedIssue advisory flag after pharmacist chart documentation.",
        "Restore active medication status if interaction is clinically mitigated.",
    ),
    "HOLD_PRESCRIPTION": (
        "Release prescription hold only after documented pharmacist NPI attestation.",
        "Restore prior active MedicationRequest status in EHR order queue.",
    ),
    "PROPOSE_THERAPEUTIC_ALTERNATIVE": (
        "Cancel proposed alternative MedicationRequest draft if prescriber declines.",
        "Maintain original therapy with documented clinical monitoring plan.",
    ),
    "REQUEST_RENAL_HEPATIC_LABS": (
        "Cancel pending laboratory order Task if recent eGFR/hepatic panel is verified.",
        "Resume prescription review once organ-function lab results are attached.",
    ),
    "ESCALATE_TO_CLINICAL_PHARMACIST": (
        "Close pharmacist escalation Task upon documented HITL clinical adjudication.",
        "Apply structured Clinical Justification Code before overriding hold state.",
    ),
}


def synthesize_rollback(
    action_type: ActionType,
    *,
    affected_rxcuis: tuple[str, ...] = (),
    dry_run: bool = False,
) -> tuple[str, ...]:
    """Generate deterministic clinical rollback steps for a canonical ActionType."""
    if action_type not in ALLOWED_ACTION_TYPES:
        raise ValueError(f"Unsupported ActionType for rollback synthesis: {action_type!r}")
    steps = list(_ROLLBACK_TEMPLATES[action_type])
    if affected_rxcuis:
        rxcui_list = ", ".join(affected_rxcuis)
        steps.append(f"Target RxCUIs for rollback verification: {rxcui_list}.")
    if dry_run:
        steps.append("Dry-run simulation mode: no external EHR state was mutated.")
    return tuple(steps)
