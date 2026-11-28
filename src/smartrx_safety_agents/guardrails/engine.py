"""Guardrail enforcement, deterministic payload overwriting, and HMAC-SHA256 signing."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from smartrx_safety_agents.guardrails.fhir_generator import generate_fhir_payload
from smartrx_safety_agents.guardrails.rollback import synthesize_rollback
from smartrx_safety_agents.models.clinical import (
    ALLOWED_ACTION_TYPES,
    ActionType,
    ClinicalAlert,
    NormalizedMedication,
    RiskGrade,
)
from smartrx_safety_agents.models.remediation import RemediationPlan

_INSECURE_SECRETS: frozenset[str] = frozenset(
    {"", "changeme", "default", "secret", "test", "placeholder", "none"}
)
_MAX_TTL_SECONDS = 300


class PlanVerificationError(ValueError):
    """Raised when a remediation plan fails signature, TTL, or anti-replay checks."""


def canonical_plan_json(plan: RemediationPlan) -> str:
    """Serialize RemediationPlan to deterministic canonical JSON excluding signature fields."""
    payload = plan.model_dump(mode="json", exclude={"plan_digest", "plan_signature"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_plan_signatures(plan: RemediationPlan, secret: str) -> tuple[str, str]:
    """Compute SHA-256 digest and HMAC-SHA256 signature over canonical plan JSON."""
    canonical = canonical_plan_json(plan).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    signature = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return digest, signature


def verify_plan_signature(plan: RemediationPlan, secret: str) -> bool:
    """Verify plan_digest and plan_signature using constant-time hmac.compare_digest."""
    expected_digest, expected_sig = compute_plan_signatures(plan, secret)
    digest_ok = hmac.compare_digest(plan.plan_digest, expected_digest)
    sig_ok = hmac.compare_digest(plan.plan_signature, expected_sig)
    return digest_ok and sig_ok


class GuardrailEngine:
    """Enforces ActionType allowlists, deterministic FHIR R4 overwriting, and HMAC sealing."""

    def __init__(
        self,
        *,
        signing_secret: str,
        environment: str = "development",
    ) -> None:
        cleaned = signing_secret.strip()
        if environment == "production" and (
            len(cleaned) < 16 or cleaned.casefold() in _INSECURE_SECRETS
        ):
            raise RuntimeError(
                "SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET must be >=16 chars "
                "and non-default in production."
            )
        if not cleaned:
            raise ValueError("Signing secret must not be empty.")
        self._secret = cleaned
        self._idempotency_cache: dict[str, RemediationPlan] = {}
        self._verified_plan_ids: set[str] = set()

    def enforce(
        self,
        *,
        plan_id: str,
        idempotency_key: str,
        patient_token: str,
        action_type: str,
        risk_score: int,
        risk_grade: RiskGrade,
        medications: tuple[NormalizedMedication, ...] = (),
        alerts: tuple[ClinicalAlert, ...] = (),
        draft_execution_payload: dict[str, Any] | None = None,
        ttl_seconds: int = _MAX_TTL_SECONDS,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> RemediationPlan:
        """Validate, overwrite draft payloads, quarantine unsafe actions, and HMAC-seal."""
        _ = draft_execution_payload  # Explicitly discarded: zero LLM command synthesis.
        current_time = now if now is not None else datetime.now(UTC)

        cached = self._idempotency_cache.get(idempotency_key)
        if cached is not None and current_time < cached.expires_at:
            return cached

        if ttl_seconds <= 0 or ttl_seconds > _MAX_TTL_SECONDS:
            raise ValueError(f"Plan TTL must be between 1 and {_MAX_TTL_SECONDS} seconds.")

        quarantined = False
        quarantine_reason: str | None = None
        safe_action: ActionType

        if action_type not in ALLOWED_ACTION_TYPES:
            quarantined = True
            quarantine_reason = "INVALID_ACTION_ENUM_TYPE"
            safe_action = "ESCALATE_TO_CLINICAL_PHARMACIST"
        else:
            safe_action = action_type  # type: ignore[assignment]

        affected_rxcuis = tuple(med.rxcui for med in medications)
        rollback_steps = synthesize_rollback(
            safe_action, affected_rxcuis=affected_rxcuis, dry_run=dry_run
        )

        if risk_score >= 3 and not rollback_steps:
            quarantined = True
            quarantine_reason = "MISSING_MANDATORY_ROLLBACK"

        try:
            execution_payload = generate_fhir_payload(
                safe_action,
                patient_token=patient_token,
                medications=medications,
                alerts=alerts,
                dry_run=dry_run,
            )
        except ValueError:
            quarantined = True
            quarantine_reason = "INVALID_FHIR_IDENTIFIER"
            execution_payload = {
                "resourceType": "Bundle",
                "type": "collection",
                "dryRun": True,
                "entry": [],
            }

        unsealed = RemediationPlan(
            plan_id=plan_id,
            idempotency_key=idempotency_key,
            patient_token=patient_token,
            action_type=safe_action,
            risk_score=risk_score,
            risk_grade=risk_grade,
            dry_run=dry_run,
            quarantined=quarantined,
            quarantine_reason=quarantine_reason,
            execution_payload=execution_payload,
            rollback_steps=rollback_steps,
            issued_at=current_time,
            expires_at=current_time + timedelta(seconds=ttl_seconds),
        )
        digest, signature = compute_plan_signatures(unsealed, self._secret)
        sealed = unsealed.model_copy(update={"plan_digest": digest, "plan_signature": signature})
        self._idempotency_cache[idempotency_key] = sealed
        return sealed

    def verify_plan(
        self,
        plan: RemediationPlan,
        *,
        now: datetime | None = None,
        check_replay: bool = True,
    ) -> None:
        """Verify HMAC signature, TTL expiration, and anti-replay nonce."""
        current_time = now if now is not None else datetime.now(UTC)
        if (plan.expires_at - plan.issued_at).total_seconds() > _MAX_TTL_SECONDS:
            raise PlanVerificationError("Plan TTL exceeds 300-second maximum.")
        if current_time >= plan.expires_at:
            raise PlanVerificationError("Plan has expired.")
        if check_replay and plan.plan_id in self._verified_plan_ids:
            raise PlanVerificationError(f"Replayed plan_id detected: {plan.plan_id}")
        if not verify_plan_signature(plan, self._secret):
            raise PlanVerificationError("Plan HMAC-SHA256 signature verification failed.")
        if check_replay:
            self._verified_plan_ids.add(plan.plan_id)
