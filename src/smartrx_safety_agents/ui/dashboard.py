"""Three-Column Pharmacist HITL Workbench (Streamlit + testable pure helpers)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from smartrx_safety_agents.agents.orchestrator import BlackboardState
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.models.clinical import (
    AgentStatus,
    ClinicalOutput,
    InsuranceOutput,
    IntakeOutput,
    NormalizedMedication,
    RiskGrade,
    SafetyOutput,
    StrictClinicalModel,
)

BPMHDiffStatus = Literal["Added", "Continued", "Discontinued", "Modified"]


class TrafficLightBadge(StrictClinicalModel):
    """3-Tier HITL confidence & clinical safety traffic-light badge."""

    grade: RiskGrade
    label: str = Field(..., min_length=1)
    color_hex: str = Field(..., min_length=4)
    blocked: bool = Field(default=False)


class BPMHDiffItem(StrictClinicalModel):
    """Single medication row in the BPMH reconciliation diff table."""

    rxcui: str = Field(..., min_length=1)
    drug_name: str = Field(..., min_length=1)
    diff_status: BPMHDiffStatus
    dose_mg: float | None = Field(default=None)
    frequency: str = Field(..., min_length=1)
    ocr_confidence: float = Field(..., ge=0.0, le=1.0)
    is_nti: bool = Field(default=False)
    risk_grade: RiskGrade
    requires_attestation: bool = Field(default=False)


def classify_traffic_light(safety: SafetyOutput, intake: IntakeOutput) -> TrafficLightBadge:
    """Compute the 3-Tier HITL traffic-light badge from safety and OCR confidence."""
    if (
        safety.overall_risk_grade == RiskGrade.RED
        or intake.low_confidence_nti_detected
        or intake.confidence < 0.70
    ):
        return TrafficLightBadge(
            grade=RiskGrade.RED,
            label="TIER 1: RED LOCK",
            color_hex="#D32F2F",
            blocked=True,
        )
    if safety.overall_risk_grade == RiskGrade.YELLOW or intake.confidence < 0.90:
        return TrafficLightBadge(
            grade=RiskGrade.YELLOW,
            label="TIER 2: YELLOW REVIEW",
            color_hex="#F9A825",
            blocked=False,
        )
    return TrafficLightBadge(
        grade=RiskGrade.GREEN,
        label="TIER 3: GREEN AUTO-VERIFY",
        color_hex="#2E7D32",
        blocked=False,
    )


def build_bpmh_diff(
    intake: IntakeOutput,
    clinical: ClinicalOutput,
    safety: SafetyOutput,
) -> tuple[BPMHDiffItem, ...]:
    """Build BPMH reconciliation diff items comparing incoming Rx vs EHR history."""
    active_by_rxcui = {m.rxcui: m for m in clinical.active_medications}
    alert_grade_by_rxcui: dict[str, RiskGrade] = {}
    for alert in safety.alerts:
        for rxcui in alert.affected_rxcuis:
            prev = alert_grade_by_rxcui.get(rxcui)
            if prev is None or alert.risk_grade == RiskGrade.RED:
                alert_grade_by_rxcui[rxcui] = alert.risk_grade

    items: list[BPMHDiffItem] = []
    seen_rxcuis: set[str] = set()

    for med in intake.medications:
        seen_rxcuis.add(med.rxcui)
        existing = active_by_rxcui.get(med.rxcui)
        if existing is None:
            diff_status: BPMHDiffStatus = "Added"
        elif existing.dose_mg != med.dose_mg or existing.frequency != med.frequency:
            diff_status = "Modified"
        else:
            diff_status = "Continued"
        grade = alert_grade_by_rxcui.get(med.rxcui, RiskGrade.GREEN)
        if med.is_nti and med.ocr_confidence < 0.70:
            grade = RiskGrade.RED
        items.append(
            BPMHDiffItem(
                rxcui=med.rxcui,
                drug_name=med.scd_name,
                diff_status=diff_status,
                dose_mg=med.dose_mg,
                frequency=med.frequency,
                ocr_confidence=med.ocr_confidence,
                is_nti=med.is_nti,
                risk_grade=grade,
                requires_attestation=grade == RiskGrade.RED,
            )
        )

    for active in clinical.active_medications:
        if active.rxcui in seen_rxcuis:
            continue
        grade = alert_grade_by_rxcui.get(active.rxcui, RiskGrade.GREEN)
        items.append(
            BPMHDiffItem(
                rxcui=active.rxcui,
                drug_name=active.scd_name,
                diff_status="Discontinued",
                dose_mg=active.dose_mg,
                frequency=active.frequency,
                ocr_confidence=active.ocr_confidence,
                is_nti=active.is_nti,
                risk_grade=grade,
                requires_attestation=grade == RiskGrade.RED,
            )
        )

    return tuple(items)


def run_what_if_swap(
    intake: IntakeOutput,
    clinical: ClinicalOutput,
    *,
    replace_rxcui: str,
    replacement_med: NormalizedMedication,
    engine: DeterministicClinicalEngine,
    patient_age: int | None = None,
    payer_formulary: dict[str, dict[str, Any]] | None = None,
) -> tuple[SafetyOutput, InsuranceOutput]:
    """Simulate a 'What-If' Sandbox drug swap through the deterministic safety engine."""
    updated_meds = tuple(
        replacement_med if m.rxcui == replace_rxcui else m for m in intake.medications
    )
    if not any(m.rxcui == replace_rxcui for m in intake.medications):
        updated_meds = (*intake.medications, replacement_med)
    simulated_intake = intake.model_copy(
        update={
            "medications": updated_meds,
            "low_confidence_nti_detected": any(
                m.is_nti and m.ocr_confidence < 0.70 for m in updated_meds
            ),
        }
    )
    return engine.evaluate(
        simulated_intake,
        clinical,
        patient_age=patient_age,
        payer_formulary=payer_formulary,
    )


def validate_adjudication_submission(
    *,
    risk_grade: RiskGrade,
    decision: Literal["Accept", "Modify", "Dismiss"],
    justification_code: str | None,
    npi_attestation: str | None,
    reason_text: str | None,
) -> tuple[bool, str | None]:
    """Validate pharmacist HITL adjudication inputs per 3-Tier governance rules."""
    if risk_grade == RiskGrade.RED:
        if not (justification_code and justification_code.strip()):
            return False, "Tier 1 RED lock requires a Clinical Justification Code."
        if not (npi_attestation and npi_attestation.strip()):
            return False, "Tier 1 RED lock requires Digital NPI Attestation."
    elif risk_grade == RiskGrade.YELLOW and decision in {"Modify", "Dismiss"}:
        if not (reason_text and reason_text.strip()):
            return False, "Tier 2 YELLOW Modify/Dismiss requires reason text."
    return True, None


def build_circuit_breaker_banner(state: BlackboardState) -> dict[str, str] | None:
    """Return an orange Circuit Breaker banner descriptor if HALT_FOR_HUMAN triggered."""
    halted = state.circuit_breaker_tripped or (
        state.liaison is not None and state.liaison.status == AgentStatus.HALT_FOR_HUMAN
    )
    if not halted:
        return None
    return {
        "severity": "warning",
        "color_hex": "#EF6C00",
        "title": "CIRCUIT BREAKER TRIGGERED: HALT_FOR_HUMAN",
        "message": (
            f"Agent consensus failed after {state.turn_count} turns. "
            "Automated execution is locked pending mandatory clinical pharmacist attestation."
        ),
    }


def format_agent_breadcrumbs(state: BlackboardState) -> tuple[str, ...]:
    """Format the 6-agent execution breadcrumb trail for the UI Safety Rail."""
    agents = (
        ("Intake", "IntakeAgent"),
        ("History", "ClinicalHistoryAgent"),
        ("Safety", "SafetyAuditorAgent"),
        ("Insurance", "InsuranceAgent"),
        ("Auditor", "AdversarialAuditorAgent"),
        ("Liaison", "PharmacistLiaisonAgent"),
    )
    return tuple(f"{label} [{state.tier_trace.get(key, 'pending')}]" for label, key in agents)


def render_dashboard(state: BlackboardState | None = None) -> None:  # pragma: no cover
    """Render the Three-Column Pharmacist HITL Workbench in Streamlit."""
    import streamlit as st

    st.set_page_config(page_title="SmartRx Guard — Pharmacist HITL Workbench", layout="wide")
    st.title("SmartRx Guard — Clinical Medication Reconciliation Workbench")

    if state is None or state.intake is None or state.clinical is None or state.safety is None:
        st.info("Load a reconciliation session or run a benchmark scenario to begin.")
        return

    badge = classify_traffic_light(state.safety, state.intake)
    banner = build_circuit_breaker_banner(state)
    if banner is not None:
        st.warning(f"**{banner['title']}** — {banner['message']}")

    col_left, col_center, col_right = st.columns([1.0, 1.3, 1.1])

    with col_left:
        st.subheader("1. Input Evidence")
        st.caption(f"Patient Token: `{state.patient_token}`")
        for med in state.intake.medications:
            conf_pct = f"{med.ocr_confidence * 100:.0f}%"
            nti_tag = " | NTI" if med.is_nti else ""
            st.markdown(f"- **{med.scd_name}** (`{med.rxcui}`) — OCR: `{conf_pct}`{nti_tag}")
        allergies_str = ", ".join(state.clinical.allergies) or "None"
        st.markdown(f"**12-Month EHR Allergies:** {allergies_str}")
        st.markdown(f"**eGFR:** `{state.clinical.egfr_ml_min}` mL/min")

    with col_center:
        st.subheader("2. BPMH Reconciliation Workbench")
        st.markdown(f"**Overall Grade:** `{badge.label}`")
        diff_items = build_bpmh_diff(state.intake, state.clinical, state.safety)
        for item in diff_items:
            st.markdown(
                f"- [{item.diff_status}] **{item.drug_name}** "
                f"(`{item.rxcui}`) — `{item.risk_grade.value}`"
            )

    with col_right:
        st.subheader("3. Safety Rail & Agent Breadcrumbs")
        st.markdown(" → ".join(format_agent_breadcrumbs(state)))
        for alert in state.safety.alerts:
            with st.expander(f"[{alert.risk_grade.value}] {alert.rule_category}: {alert.severity}"):
                st.write(alert.rationale)
                st.caption(f"Citation: {alert.citation}")
        if badge.blocked:
            st.error("Tier 1 RED Lock active: Clinical Justification Code & Digital NPI required.")
