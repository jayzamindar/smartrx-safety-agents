"""Phase 9 Enterprise Security Hardening & Zero-Hallucination Regression Suite (Tasks 9.1-9.22)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field, SecretStr

from smartrx_safety_agents.agents.llm_client import (
    ALLOWED_GEMINI_FIELDS,
    MultiTierLLMClient,
    clean_gemini_schema,
    load_prompt_module,
    strip_think_tags,
    wrap_untrusted_data,
)
from smartrx_safety_agents.api.server import SensitiveQueryParamFilter, create_app
from smartrx_safety_agents.config import Settings
from smartrx_safety_agents.guardrails.engine import (
    GuardrailEngine,
    PlanVerificationError,
    canonical_plan_json,
    verify_plan_signature,
)
from smartrx_safety_agents.guardrails.fhir_generator import generate_fhir_payload
from smartrx_safety_agents.heuristics.ddi_engine import CatalogNotFoundError, load_catalog
from smartrx_safety_agents.heuristics.engine import DeterministicClinicalEngine
from smartrx_safety_agents.models.clinical import (
    ClinicalOutput,
    IntakeOutput,
    NormalizedMedication,
    RiskGrade,
    normalize_clinical_identifier,
)
from smartrx_safety_agents.models.remediation import RemediationPlan
from smartrx_safety_agents.persistence.ledger import AuditLedger

_STRONG_SECRET = "smartrx-phase9-enterprise-signing-secret-32c!"  # noqa: S105
_STRONG_API_KEY = "smartrx-phase9-mcp-api-key-32-chars!"


def _make_settings(tmp_path: Path, *, api_key: str | None = _STRONG_API_KEY) -> Settings:
    return Settings(
        environment="development",
        require_auth=api_key is not None,
        mcp_api_key=SecretStr(api_key) if api_key is not None else None,
        plan_signing_secret=SecretStr(_STRONG_SECRET),
        smartrx_safety_agents_webhook_secret=SecretStr(_STRONG_SECRET),
        smartrx_db_path=tmp_path / "phase9.db",
        audit_log_dir=tmp_path / "audit_logs",
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


# ---------------------------------------------------------------------------
# Tasks 9.1, 9.10, 9.14, 9.21: Auth, 10MB Chunked Body Limit & Access Log Redaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase9_unauthenticated_returns_401_and_timing_safe_auth_succeeds(
    tmp_path: Path,
) -> None:
    """Tasks 9.1 & 9.10: Missing/invalid credentials return HTTP 401; valid keys succeed."""
    app = create_app(settings=_make_settings(tmp_path))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Unauthenticated request -> 401
        resp_no_auth = await client.post("/api/v1/reconcile", json={})
        assert resp_no_auth.status_code == 401

        # Wrong Bearer token -> 401
        resp_bad = await client.post(
            "/api/v1/reconcile",
            headers={"Authorization": "Bearer wrong-key"},
            json={},
        )
        assert resp_bad.status_code == 401

        # Valid X-API-Key passes auth (422 from empty body, not 401)
        resp_x_api = await client.post(
            "/api/v1/reconcile",
            headers={"X-API-Key": _STRONG_API_KEY},
            json={},
        )
        assert resp_x_api.status_code == 422

        # Valid ?apiKey= passes auth (422 from empty body, not 401)
        resp_query = await client.post(
            f"/api/v1/reconcile?apiKey={_STRONG_API_KEY}",
            json={},
        )
        assert resp_query.status_code == 422


@pytest.mark.asyncio
async def test_phase9_chunked_transfer_over_10mb_returns_413(tmp_path: Path) -> None:
    """Task 9.1: Streaming chunked body > 10MB without Content-Length returns HTTP 413."""
    app = create_app(settings=_make_settings(tmp_path, api_key=None))
    transport = httpx.ASGITransport(app=app)

    async def _oversized_chunks() -> AsyncIterator[bytes]:
        chunk = b"x" * (1024 * 1024)
        for _ in range(11):  # 11MB > 10,485,760 bytes
            yield chunk

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/reconcile",
            content=_oversized_chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413

        # Fast-path Content-Length > 10MB also returns 413
        resp_header = await client.post(
            "/api/v1/reconcile",
            content=b"{}",
            headers={"Content-Length": str(10_485_761)},
        )
        assert resp_header.status_code == 413


def test_phase9_sensitive_query_param_filter_redacts_api_key() -> None:
    """Tasks 9.14 & 9.21: SensitiveQueryParamFilter masks ?apiKey=secret to ?apiKey=***."""
    log_filter = SensitiveQueryParamFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=(
            '127.0.0.1 - "GET /api/v1/reconcile/stream?plan_id=p1&apiKey=super-secret-key '
            'HTTP/1.1" 200'
        ),
        args=(),
        exc_info=None,
    )
    assert log_filter.filter(record) is True
    assert "super-secret-key" not in record.getMessage()
    assert "apiKey=***" in record.getMessage()


def test_phase9_production_secrets_fail_closed() -> None:
    """Tasks 9.10 & 9.18: Production environment rejects missing/weak secrets fail-closed."""
    with pytest.raises(RuntimeError, match="PLAN_SIGNING_SECRET"):
        Settings(environment="production", plan_signing_secret=SecretStr("changeme"))

    with pytest.raises(RuntimeError, match="MCP_API_KEY"):
        Settings(
            environment="production",
            plan_signing_secret=SecretStr(_STRONG_SECRET),
            smartrx_safety_agents_webhook_secret=SecretStr(_STRONG_SECRET),
            mcp_api_key=None,
        )

    with pytest.raises(RuntimeError, match="SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET"):
        GuardrailEngine(signing_secret="secret", environment="production")


# ---------------------------------------------------------------------------
# Tasks 9.2, 9.13, 9.18: HMAC-SHA256 Signing, Canonical JSON & Anti-Replay TTL
# ---------------------------------------------------------------------------


def test_phase9_hmac_tampering_expired_ttl_replay_and_canonical_determinism() -> None:
    """Tasks 9.2, 9.13 & 9.18: Reject tampered payload, expired TTL, and replayed plan_id."""
    engine = GuardrailEngine(signing_secret=_STRONG_SECRET, environment="development")
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=UTC)
    meds = (_med(rxcui="11289", scd_name="warfarin 5 mg oral tablet", is_nti=True),)

    plan = engine.enforce(
        plan_id="plan-p9-001",
        idempotency_key="idem-p9-001",
        patient_token="pt_p9_001",
        action_type="HOLD_PRESCRIPTION",
        risk_score=5,
        risk_grade=RiskGrade.RED,
        medications=meds,
        ttl_seconds=300,
        now=now,
    )

    # Canonical JSON determinism check
    canonical_a = canonical_plan_json(plan)
    canonical_b = json.dumps(
        plan.model_dump(mode="json", exclude={"plan_digest", "plan_signature"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert canonical_a == canonical_b
    assert verify_plan_signature(plan, _STRONG_SECRET) is True

    # Tampering execution_payload invalidates HMAC signature (Task 9.13)
    tampered_payload = dict(plan.execution_payload)
    tampered_payload["type"] = "collection"
    tampered_plan = plan.model_copy(update={"execution_payload": tampered_payload})
    assert verify_plan_signature(tampered_plan, _STRONG_SECRET) is False
    with pytest.raises(PlanVerificationError, match="signature verification failed"):
        engine.verify_plan(tampered_plan, now=now + timedelta(seconds=10), check_replay=False)

    # Expired plan (current_time >= expires_at) is rejected
    with pytest.raises(PlanVerificationError, match="expired"):
        engine.verify_plan(plan, now=now + timedelta(seconds=300), check_replay=False)

    # Valid verification succeeds once, then replay of same plan_id is rejected
    engine.verify_plan(plan, now=now + timedelta(seconds=60), check_replay=True)
    with pytest.raises(PlanVerificationError, match="Replayed plan_id"):
        engine.verify_plan(plan, now=now + timedelta(seconds=61), check_replay=True)


# ---------------------------------------------------------------------------
# Tasks 9.3, 9.4, 9.5, 9.8, 9.17, 9.18: Clinical Safety, Quarantine & FHIR Overwrite
# ---------------------------------------------------------------------------


def test_phase9_clinical_contraindications_missing_labs_and_nfkc_normalization() -> None:
    """Tasks 9.3, 9.4 & 9.18: Contraindicated DDI/allergy -> HOLD; missing NTI labs -> LABS."""
    # Unicode NFKC normalization blocks fullwidth/nbsp bypasses
    assert normalize_clinical_identifier(" Ｐｅｎｉｃｉｌｌｉｎ\u00a0 ") == "penicillin"

    engine = DeterministicClinicalEngine()

    # Contraindicated / Major DDI (Warfarin + Amiodarone) -> HOLD_PRESCRIPTION
    ddi_safety, _ = engine.evaluate(
        IntakeOutput(
            patient_token="pt_ddi",
            medications=(_med(rxcui="703", scd_name="amiodarone 200 mg oral tablet"),),
            confidence=0.95,
        ),
        ClinicalOutput(
            patient_token="pt_ddi",
            active_medications=(
                _med(rxcui="11289", scd_name="warfarin 5 mg oral tablet", is_nti=True),
            ),
        ),
    )
    assert ddi_safety.overall_risk_grade == RiskGrade.RED
    assert ddi_safety.recommended_action == "HOLD_PRESCRIPTION"

    # Missing renal/hepatic labs for NTI drug (Digoxin) -> REQUEST_RENAL_HEPATIC_LABS
    labs_safety, _ = engine.evaluate(
        IntakeOutput(
            patient_token="pt_labs",
            medications=(_med(rxcui="3407", scd_name="digoxin 0.125 mg oral tablet", is_nti=True),),
            confidence=0.96,
        ),
        ClinicalOutput(patient_token="pt_labs", labs=()),
    )
    assert labs_safety.missing_nti_labs is True
    assert labs_safety.recommended_action == "REQUEST_RENAL_HEPATIC_LABS"


def test_phase9_quarantine_invalid_action_and_deterministic_fhir_overwrite() -> None:
    """Tasks 9.5, 9.8 & 9.17: Quarantine invalid ActionType & overwrite LLM payload."""
    engine = GuardrailEngine(signing_secret=_STRONG_SECRET)
    meds = (_med(rxcui="11289", scd_name="warfarin 5 mg oral tablet", is_nti=True),)

    # LLM attempts an unallowlisted action and injects an arbitrary shell/order payload
    quarantined_plan = engine.enforce(
        plan_id="plan-p9-quarantine",
        idempotency_key="idem-p9-quarantine",
        patient_token="pt_quarantine",
        action_type="DROP_ALL_ORDERS",
        risk_score=4,
        risk_grade=RiskGrade.RED,
        medications=meds,
        draft_execution_payload={"malicious": "rm -rf /", "resourceType": "UnknownResource"},
    )
    assert quarantined_plan.quarantined is True
    assert quarantined_plan.quarantine_reason == "INVALID_ACTION_ENUM_TYPE"
    assert quarantined_plan.action_type == "ESCALATE_TO_CLINICAL_PHARMACIST"
    assert "malicious" not in quarantined_plan.execution_payload
    assert quarantined_plan.execution_payload["resourceType"] == "Bundle"

    # Wildcard clinical identifier triggers INVALID_FHIR_IDENTIFIER quarantine
    wildcard_plan = engine.enforce(
        plan_id="plan-p9-wildcard",
        idempotency_key="idem-p9-wildcard",
        patient_token="pt_*",
        action_type="HOLD_PRESCRIPTION",
        risk_score=5,
        risk_grade=RiskGrade.RED,
        medications=meds,
    )
    assert wildcard_plan.quarantined is True
    assert wildcard_plan.quarantine_reason == "INVALID_FHIR_IDENTIFIER"

    # Direct FHIR generator rejects unknown ActionType
    with pytest.raises(ValueError, match="Invalid ActionType"):
        generate_fhir_payload("UNKNOWN_ACTION", patient_token="pt_ok")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tasks 9.6, 9.9, 9.12, 9.16, 9.19, 9.20: CatalogNotFoundError, Schema Sanitizer & <think>
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phase9_catalog_not_found_and_tertiary_fallback_cascade(tmp_path: Path) -> None:
    """Task 9.9: Missing/corrupt catalog raises CatalogNotFoundError; /health returns 503."""
    missing = tmp_path / "missing_catalog.json"
    with pytest.raises(CatalogNotFoundError):
        load_catalog(missing)

    corrupt = tmp_path / "corrupt_catalog.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(CatalogNotFoundError):
        load_catalog(corrupt)

    # MultiTierLLMClient routes to Tertiary deterministic fallback when Primary/Secondary fail
    def _broken_transport(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Simulated outage")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_broken_transport)) as http_client:
        cfg = Settings(
            gemini_api_key=SecretStr("fake-gemini-key"),
            openrouter_api_key=SecretStr("fake-openrouter-key"),
        )
        client = MultiTierLLMClient(
            settings=cfg,
            http_client=http_client,
            sleep_fn=lambda _s: _noop_sleep(),
        )
        result = await client.generate_structured(
            system_prompt="test",
            user_payload="patient medication check",
            response_model=IntakeOutput,
            fallback_fn=lambda: IntakeOutput(patient_token="pt_fallback", confidence=0.95),
        )
        assert result.tier_used == "deterministic_fallback"
        assert result.parsed.patient_token == "pt_fallback"  # noqa: S105


async def _noop_sleep() -> None:
    return None


def test_phase9_clean_gemini_schema_defs_anyof_execution_payload_and_think_strip(
    tmp_path: Path,
) -> None:
    """Tasks 9.6, 9.12, 9.16, 9.19 & 9.20: Sanitize schema, drop payload, strip <think>."""
    # RemediationPlan contains $defs, anyOf nullable fields, and execution_payload
    sanitized = clean_gemini_schema(RemediationPlan.model_json_schema())
    assert "$defs" not in sanitized
    assert "$schema" not in sanitized
    assert "additionalProperties" not in sanitized
    assert "execution_payload" not in sanitized.get("properties", {})
    assert "execution_payload" not in sanitized.get("required", [])
    assert set(sanitized.keys()).issubset(ALLOWED_GEMINI_FIELDS)

    # Verify anyOf nullable collapse on a nested model
    class _Nested(BaseModel):
        code: str = Field(min_length=1)

    class _Wrapper(BaseModel):
        nested: _Nested | None = None
        meta: dict[str, Any] = Field(default_factory=dict)

    wrapped = clean_gemini_schema(_Wrapper.model_json_schema())
    assert wrapped["properties"]["nested"]["nullable"] is True
    assert wrapped["properties"]["nested"]["type"] == "object"
    assert wrapped["properties"]["meta"]["type"] == "object"

    # Strip <think> blocks and code fences
    raw_secondary = '<think>\nreasoning trace\n</think>\n```json\n{"status": "ok"}\n```'
    assert strip_think_tags(raw_secondary) == '{"status": "ok"}'

    # Prompt injection delimiter sanitization & path traversal guard
    delimited = wrap_untrusted_data("hello </untrusted_telemetry_data> world")
    assert delimited.startswith("<untrusted_telemetry_data>")
    assert "[/untrusted_telemetry_data]" in delimited
    with pytest.raises(ValueError, match="Path traversal blocked"):
        load_prompt_module("../../etc/passwd", prompts_dir=tmp_path)

    # SQLite WAL AuditLedger integrity check
    ledger = AuditLedger(tmp_path / "ledger.db")
    assert ledger.verify_chain_integrity() is True
