"""Click CLI entrypoint for SmartRx Safety Agents."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click
import uvicorn

from smartrx_safety_agents.agents.llm_client import MultiTierLLMClient
from smartrx_safety_agents.agents.orchestrator import SmartRxOrchestrator
from smartrx_safety_agents.api.mcp_server import SmartRxMCPServer
from smartrx_safety_agents.api.server import create_app
from smartrx_safety_agents.config import get_settings
from smartrx_safety_agents.guardrails.engine import GuardrailEngine
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.models.clinical import (
    ClinicalOutput,
    NormalizedMedication,
    RiskGrade,
)
from smartrx_safety_agents.persistence.ledger import AuditLedger


@click.group()
def main() -> None:
    """SmartRx Guard clinical medication reconciliation CLI."""


@main.command()
def status() -> None:
    """Print active non-secret runtime configuration status."""
    settings = get_settings()
    click.echo(
        f"smartrx-safety-agents env={settings.environment} "
        f"model={settings.gemini_model_name} port={settings.smartrx_port}"
    )


@main.command()
@click.option("--patient-id", default="MRN-CLI-001", help="Raw patient identifier (tokenized).")
@click.option("--med-rxcui", default="29046", help="RxCUI of prescribed medication.")
@click.option("--med-name", default="lisinopril 10 mg", help="Medication name.")
@click.option("--input-file", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False, help="Run simulation without EHR mutation.")
def reconcile(
    patient_id: str,
    med_rxcui: str,
    med_name: str,
    input_file: Path | None,
    dry_run: bool,
) -> None:
    """Run the 6-agent clinical medication reconciliation pipeline."""
    settings = get_settings()
    signing_secret = (
        settings.plan_signing_secret.get_secret_value()
        if settings.plan_signing_secret is not None
        else "dev-only-non-prod-signing-secret-32c!"
    )
    meds: tuple[NormalizedMedication, ...]
    clinical: ClinicalOutput | None = None
    intake_text = f"Prescribed {med_name} (RxCUI {med_rxcui})"

    if input_file is not None:
        raw_data: dict[str, Any] = json.loads(input_file.read_text(encoding="utf-8"))
        patient_id = str(raw_data.get("raw_patient_id", patient_id))
        intake_text = str(raw_data.get("raw_intake_text", intake_text))
        meds = tuple(
            NormalizedMedication.model_validate(m) for m in raw_data.get("medications", ())
        )
        if "clinical" in raw_data and raw_data["clinical"] is not None:
            clinical = ClinicalOutput.model_validate(raw_data["clinical"])
    else:
        meds = (
            NormalizedMedication(
                rxcui=med_rxcui,
                scd_name=med_name,
                raw_name=med_name,
                dose_mg=10.0,
                frequency="once daily",
                route="oral",
            ),
        )

    from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor

    patient_token = PHIRedactor.tokenize_patient_id(patient_id)
    ledger = AuditLedger(
        settings.smartrx_db_path, filelock_timeout_sec=settings.filelock_timeout_sec
    )
    orchestrator = SmartRxOrchestrator(
        llm_client=MultiTierLLMClient(settings=settings),
        deterministic_engine=DeterministicClinicalEngine(),
        guardrail_engine=GuardrailEngine(
            signing_secret=signing_secret, environment=settings.environment
        ),
        audit_ledger=ledger,
    )
    state = asyncio.run(
        orchestrator.run_reconciliation(
            plan_id=f"cli-{patient_token}",
            idempotency_key=f"cli-idem-{patient_token}-{dry_run}",
            raw_patient_id=patient_id,
            raw_intake_text=intake_text,
            raw_ehr_summary="",
            fallback_medications=meds,
            fallback_clinical=clinical,
            dry_run=dry_run,
        )
    )
    output = {
        "plan_id": state.plan_id,
        "patient_token": state.patient_token,
        "risk_grade": state.liaison.overall_risk_grade.value if state.liaison else "UNKNOWN",
        "action": state.liaison.recommended_action if state.liaison else "UNKNOWN",
        "dry_run": dry_run,
    }
    click.echo(json.dumps(output, indent=2))


@main.command()
def benchmark() -> None:
    """Execute deterministic clinical safety benchmark scorecard (TC-001 to TC-008)."""
    engine = DeterministicClinicalEngine()

    def _med(
        rxcui: str, name: str, *, is_nti: bool = False, conf: float = 0.98
    ) -> NormalizedMedication:
        return NormalizedMedication(
            rxcui=rxcui,
            scd_name=name,
            raw_name=name,
            dose_mg=5.0,
            frequency="once daily",
            route="oral",
            is_nti=is_nti,
            ocr_confidence=conf,
        )

    cases: list[tuple[str, RiskGrade, str]] = []
    bench_pt = "pt_bench"

    # TC-001: Warfarin + Amiodarone -> RED HOLD_PRESCRIPTION
    s1, _ = engine.evaluate(
        intake=_make_intake(_med("11289", "warfarin", is_nti=True)),
        clinical=ClinicalOutput(
            patient_token=bench_pt,
            active_medications=(_med("703", "amiodarone"),),
            egfr_ml_min=70.0,
        ),
    )
    cases.append(("TC-001", s1.overall_risk_grade, s1.recommended_action))

    # TC-002: Penicillin allergy + Amoxicillin -> RED HOLD_PRESCRIPTION
    s2, _ = engine.evaluate(
        intake=_make_intake(_med("723", "amoxicillin")),
        clinical=ClinicalOutput(patient_token=bench_pt, allergies=("penicillin",)),
    )
    cases.append(("TC-002", s2.overall_risk_grade, s2.recommended_action))

    # TC-003: Missing eGFR for NTI Digoxin -> REQUEST_RENAL_HEPATIC_LABS
    s3, _ = engine.evaluate(
        intake=_make_intake(_med("3407", "digoxin", is_nti=True)),
        clinical=ClinicalOutput(patient_token=bench_pt, egfr_ml_min=None),
    )
    cases.append(("TC-003", s3.overall_risk_grade, s3.recommended_action))

    # TC-004: Low OCR confidence on NTI Warfarin -> RED HOLD_PRESCRIPTION
    s4, _ = engine.evaluate(
        intake=_make_intake(_med("11289", "warfarin", is_nti=True, conf=0.55)),
        clinical=ClinicalOutput(patient_token=bench_pt, egfr_ml_min=75.0),
    )
    cases.append(("TC-004", s4.overall_risk_grade, s4.recommended_action))

    # TC-005: Therapeutic duplication Lisinopril + Enalapril -> YELLOW
    s5, _ = engine.evaluate(
        intake=_make_intake(_med("29046", "lisinopril")),
        clinical=ClinicalOutput(
            patient_token=bench_pt, active_medications=(_med("3827", "enalapril"),)
        ),
    )
    cases.append(("TC-005", s5.overall_risk_grade, s5.recommended_action))

    # TC-006: Geriatric Beer's Criteria Diphenhydramine -> PROPOSE_THERAPEUTIC_ALTERNATIVE
    s6, _ = engine.evaluate(
        intake=_make_intake(_med("3498", "diphenhydramine")),
        clinical=ClinicalOutput(patient_token=bench_pt),
        patient_age=72,
    )
    cases.append(("TC-006", s6.overall_risk_grade, s6.recommended_action))

    # TC-007: Payer unavailable -> CMS fallback (YELLOW)
    s7, i7 = engine.evaluate(
        intake=_make_intake(_med("29046", "lisinopril")),
        clinical=ClinicalOutput(patient_token=bench_pt),
        payer_formulary=None,
    )
    cases.append(("TC-007", s7.overall_risk_grade, f"cms_fallback={i7.used_cms_fallback}"))

    # TC-008: Clean reconciliation with payer formulary -> GREEN APPROVE_RECONCILED_LIST
    s8, _ = engine.evaluate(
        intake=_make_intake(_med("29046", "lisinopril")),
        clinical=ClinicalOutput(patient_token=bench_pt),
        payer_formulary={
            "29046": {"covered": True, "tier": 1, "copay": 10.0, "requires_pa": False}
        },
    )
    cases.append(("TC-008", s8.overall_risk_grade, s8.recommended_action))

    for tc_id, grade, action in cases:
        click.echo(f"{tc_id}: grade={grade.value} action={action}")


def _make_intake(med: NormalizedMedication) -> Any:
    from smartrx_safety_agents.models.clinical import IntakeOutput

    bench_pt = "pt_bench"
    return IntakeOutput(
        patient_token=bench_pt,
        medications=(med,),
        low_confidence_nti_detected=med.is_nti and med.ocr_confidence < 0.70,
        confidence=med.ocr_confidence,
    )


@main.command("verify-audit")
@click.option("--db-path", type=click.Path(path_type=Path), default=None)
def verify_audit(db_path: Path | None) -> None:
    """Verify SHA-256 hash-chain integrity across the AuditLedger."""
    settings = get_settings()
    ledger = AuditLedger(db_path or settings.smartrx_db_path)
    valid = ledger.verify_chain_integrity()
    count = len(ledger.get_events(limit=10_000))
    click.echo(json.dumps({"chain_valid": valid, "event_count": count}))
    if not valid:
        raise click.ClickException("AuditLedger hash-chain verification failed.")


@main.command()
@click.option("--host", default="0.0.0.0")  # noqa: S104
@click.option("--port", default=8080, type=int)
def serve(host: str, port: int) -> None:
    """Launch the FastAPI REST & SSE gateway."""
    uvicorn.run(create_app(), host=host, port=port)


@main.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--host", default="0.0.0.0")  # noqa: S104
@click.option("--port", default=8080, type=int)
def mcp(transport: str, host: str, port: int) -> None:
    """Launch the SmartRx MCP server over stdio or SSE."""
    app = create_app()
    if transport == "sse":
        uvicorn.run(app, host=host, port=port)
        return
    mcp_server = SmartRxMCPServer(
        orchestrator=app.state.orchestrator,
        ledger=app.state.ledger,
        max_payload_bytes=app.state.settings.max_payload_size_bytes,
    )
    asyncio.run(mcp_server.serve_stdio())


if __name__ == "__main__":
    main()
