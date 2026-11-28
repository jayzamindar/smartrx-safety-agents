"""FastAPI REST & SSE Gateway with 10MB streaming body guard, timing-safe auth & WAL drain."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from smartrx_safety_agents.agents.llm_client import MultiTierLLMClient
from smartrx_safety_agents.agents.orchestrator import SmartRxOrchestrator
from smartrx_safety_agents.config import Settings, get_settings
from smartrx_safety_agents.guardrails.engine import GuardrailEngine
from smartrx_safety_agents.heuristics.ddi_engine import CatalogNotFoundError, load_catalog
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.models.clinical import (
    ClinicalOutput,
    NormalizedMedication,
    RiskGrade,
    StrictClinicalModel,
)
from smartrx_safety_agents.persistence.ledger import AuditLedger

_API_KEY_QUERY_RE = re.compile(r'apiKey=[^&\s"]+')


class SensitiveQueryParamFilter(logging.Filter):
    """Sanitize `?apiKey=...` query parameters in uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "apiKey=" in msg:
            record.msg = _API_KEY_QUERY_RE.sub("apiKey=***", msg)
            record.args = ()
        return True


class _PayloadTooLargeError(Exception):
    """Internal signal raised when streaming request body exceeds max_bytes."""


class PayloadSizeLimitMiddleware:
    """Dual-layer 10MB body size defense (Content-Length + streaming chunk byte counter)."""

    def __init__(self, app: ASGIApp, *, max_bytes: int = 10_485_760) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        raw_len = headers.get(b"content-length")
        if raw_len is not None:
            try:
                if int(raw_len.decode("ascii")) > self.max_bytes:
                    response = JSONResponse(
                        {"detail": "Payload Too Large (exceeds 10MB ceiling)."},
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        total_bytes = 0

        async def _counting_receive() -> Message:
            nonlocal total_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                total_bytes += len(body)
                if total_bytes > self.max_bytes:
                    raise _PayloadTooLargeError()
            return message

        try:
            await self.app(scope, _counting_receive, send)
        except _PayloadTooLargeError:
            response = JSONResponse(
                {"detail": "Payload Too Large (streaming body exceeded 10MB ceiling)."},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
            await response(scope, receive, send)


class ReconcileRequest(StrictClinicalModel):
    """Inbound clinical medication reconciliation request payload."""

    plan_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    raw_patient_id: str = Field(..., min_length=1)
    raw_intake_text: str = Field(..., min_length=1)
    raw_ehr_summary: str = Field(default="")
    medications: tuple[NormalizedMedication, ...] = Field(default_factory=tuple)
    clinical: ClinicalOutput | None = Field(default=None)
    patient_age: int | None = Field(default=None, ge=0, le=130)
    payer_formulary: dict[str, dict[str, Any]] | None = Field(default=None)
    known_names: tuple[str, ...] = Field(default_factory=tuple)
    known_mrns: tuple[str, ...] = Field(default_factory=tuple)
    dry_run: bool = Field(default=False)


class AdjudicateRequest(StrictClinicalModel):
    """Pharmacist HITL adjudication request with mandatory Tier 1 RED attestation."""

    plan_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    patient_token: str = Field(..., min_length=1)
    decision: Literal["Accept", "Modify", "Dismiss"]
    risk_grade: RiskGrade
    clinical_justification_code: str | None = Field(default=None)
    npi_attestation: str | None = Field(default=None)
    reason_text: str | None = Field(default=None)


def _build_auth_dependency(
    settings: Settings,
) -> Callable[..., Coroutine[Any, Any, None]]:
    async def _require_api_key(
        request: Request,
        api_key_query: str | None = Query(default=None, alias="apiKey"),
    ) -> None:
        auth_required = (
            settings.environment == "production"
            or settings.require_auth
            or settings.mcp_api_key is not None
        )
        if not auth_required:
            return

        if settings.mcp_api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Server MCP_API_KEY is not configured.",
            )
        expected = settings.mcp_api_key.get_secret_value()
        candidate: str | None = None
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            candidate = auth_header[7:].strip()
        elif request.headers.get("x-api-key"):
            candidate = request.headers.get("x-api-key", "").strip()
        elif api_key_query:
            candidate = api_key_query.strip()

        if not candidate or not hmac.compare_digest(candidate, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key.",
            )

    return _require_api_key


def create_app(
    *,
    settings: Settings | None = None,
    ledger: AuditLedger | None = None,
    llm_client: MultiTierLLMClient | None = None,
) -> FastAPI:
    """Create and configure the SmartRx FastAPI REST & SSE gateway."""
    cfg = settings or get_settings()
    signing_secret = (
        cfg.plan_signing_secret.get_secret_value()
        if cfg.plan_signing_secret is not None
        else "dev-only-non-prod-signing-secret-32c!"
    )
    audit_ledger = ledger or AuditLedger(
        cfg.smartrx_db_path, filelock_timeout_sec=cfg.filelock_timeout_sec
    )
    det_engine = DeterministicClinicalEngine()
    guardrail = GuardrailEngine(signing_secret=signing_secret, environment=cfg.environment)
    client = llm_client or MultiTierLLMClient(settings=cfg)
    orchestrator = SmartRxOrchestrator(
        llm_client=client,
        deterministic_engine=det_engine,
        guardrail_engine=guardrail,
        audit_ledger=audit_ledger,
    )
    active_streams: set[asyncio.Event] = set()
    shutting_down = False

    uvicorn_access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SensitiveQueryParamFilter) for f in uvicorn_access.filters):
        uvicorn_access.addFilter(SensitiveQueryParamFilter())

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        nonlocal shutting_down
        shutting_down = True
        for stop_event in list(active_streams):
            stop_event.set()
        await asyncio.sleep(0)
        await asyncio.to_thread(audit_ledger.checkpoint, "TRUNCATE")

    app = FastAPI(
        title="SmartRx Safety Agents Gateway",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.add_middleware(PayloadSizeLimitMiddleware, max_bytes=cfg.max_payload_size_bytes)

    auth_dep = _build_auth_dependency(cfg)
    app.state.settings = cfg
    app.state.ledger = audit_ledger
    app.state.orchestrator = orchestrator
    app.state.auth_dep = auth_dep

    from smartrx_safety_agents.api.mcp_server import SmartRxMCPServer, attach_mcp_routes

    mcp_server = SmartRxMCPServer(
        orchestrator=orchestrator,
        ledger=audit_ledger,
        max_payload_bytes=cfg.max_payload_size_bytes,
    )
    app.state.mcp_server = mcp_server
    attach_mcp_routes(app, mcp_server, auth_dep)

    async def _health_check() -> JSONResponse:
        try:
            catalog = load_catalog()
            wal_ok = await asyncio.to_thread(audit_ledger.verify_chain_integrity)
            return JSONResponse(
                {
                    "status": "ok",
                    "wal_mode": True,
                    "chain_valid": wal_ok,
                    "catalog_rules": len(catalog.ddi_pairs),
                },
                status_code=status.HTTP_200_OK,
            )
        except (CatalogNotFoundError, Exception) as exc:
            return JSONResponse(
                {"status": "degraded", "detail": str(exc)},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    app.add_api_route("/health", _health_check, methods=["GET"])
    app.add_api_route("/v1/health", _health_check, methods=["GET"])

    @app.post("/api/v1/reconcile", dependencies=[Depends(auth_dep)])
    async def reconcile(req: ReconcileRequest) -> dict[str, Any]:
        state = await orchestrator.run_reconciliation(
            plan_id=req.plan_id,
            idempotency_key=req.idempotency_key,
            raw_patient_id=req.raw_patient_id,
            raw_intake_text=req.raw_intake_text,
            raw_ehr_summary=req.raw_ehr_summary,
            fallback_medications=req.medications,
            fallback_clinical=req.clinical,
            patient_age=req.patient_age,
            payer_formulary=req.payer_formulary,
            known_names=req.known_names,
            known_mrns=req.known_mrns,
            dry_run=req.dry_run,
        )
        return {
            "plan_id": state.plan_id,
            "patient_token": state.patient_token,
            "turn_count": state.turn_count,
            "circuit_breaker_tripped": state.circuit_breaker_tripped,
            "liaison": state.liaison.model_dump(mode="json") if state.liaison else None,
            "remediation_plan": (
                state.remediation_plan.model_dump(mode="json") if state.remediation_plan else None
            ),
            "safety": state.safety.model_dump(mode="json") if state.safety else None,
            "insurance": state.insurance.model_dump(mode="json") if state.insurance else None,
            "auditor": state.auditor.model_dump(mode="json") if state.auditor else None,
        }

    @app.get("/api/v1/reconcile/stream", dependencies=[Depends(auth_dep)])
    async def reconcile_stream(
        plan_id: str = Query(..., min_length=1),
        patient_id: str = Query(..., min_length=1),
    ) -> StreamingResponse:
        stop_event = asyncio.Event()
        active_streams.add(stop_event)

        async def _event_gen() -> AsyncIterator[str]:
            stages = ("intake_history", "safety_gate", "insurance", "liaison_auditor", "sealed")
            try:
                for stage in stages:
                    if shutting_down or stop_event.is_set():
                        break
                    payload = json.dumps(
                        {"plan_id": plan_id, "stage": stage, "patient": patient_id}
                    )
                    yield f"event: {stage}\ndata: {payload}\n\n"
                    await asyncio.sleep(0)
            finally:
                active_streams.discard(stop_event)

        return StreamingResponse(_event_gen(), media_type="text/event-stream")

    @app.post("/api/v1/adjudicate", dependencies=[Depends(auth_dep)])
    async def adjudicate(req: AdjudicateRequest) -> dict[str, Any]:
        if req.risk_grade == RiskGrade.RED:
            if not (req.clinical_justification_code and req.clinical_justification_code.strip()):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Tier 1 RED adjudication requires clinical_justification_code.",
                )
            if not (req.npi_attestation and req.npi_attestation.strip()):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Tier 1 RED adjudication requires digital npi_attestation.",
                )
        elif req.risk_grade == RiskGrade.YELLOW and req.decision in {"Modify", "Dismiss"}:
            if not (req.reason_text and req.reason_text.strip()):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Tier 2 YELLOW Modify/Dismiss requires reason_text.",
                )

        from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor

        npi_token = (
            PHIRedactor.tokenize_patient_id(req.npi_attestation) if req.npi_attestation else "NONE"
        )
        override_note = (
            f"{req.decision}|code={req.clinical_justification_code or 'NONE'}"
            f"|npi_token={npi_token}|reason={req.reason_text or ''}"
        )
        safe_payload = {
            "plan_id": req.plan_id,
            "idempotency_key": req.idempotency_key,
            "patient_token": req.patient_token,
            "decision": req.decision,
            "risk_grade": req.risk_grade.value,
            "clinical_justification_code": req.clinical_justification_code,
            "npi_token": npi_token,
            "reason_text": req.reason_text,
        }
        record = await asyncio.to_thread(
            audit_ledger.record_event,
            plan_id=f"{req.plan_id}:adjudicate",
            idempotency_key=req.idempotency_key,
            patient_token=req.patient_token,
            agent_name="PharmacistHITL",
            model_version="human-attestation",
            action_type=(
                "APPROVE_RECONCILED_LIST"
                if req.decision == "Accept"
                else "ESCALATE_TO_CLINICAL_PHARMACIST"
            ),
            risk_grade=req.risk_grade,
            quarantined=False,
            payload_json=json.dumps(safe_payload, sort_keys=True),
            hitl_override_reason=override_note,
        )
        return {
            "status": "recorded",
            "event_id": record.event_id,
            "row_hash": record.row_hash,
            "decision": req.decision,
        }

    @app.get("/api/v1/audit/verify", dependencies=[Depends(auth_dep)])
    async def verify_audit() -> dict[str, Any]:
        valid = await asyncio.to_thread(audit_ledger.verify_chain_integrity)
        events = await asyncio.to_thread(audit_ledger.get_events, limit=1000)
        return {"chain_valid": valid, "event_count": len(events)}

    return app
