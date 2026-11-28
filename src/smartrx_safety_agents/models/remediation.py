"""Strict Pydantic v2 remediation plan and cryptographic signing contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from smartrx_safety_agents.models.clinical import ActionType, RiskGrade, StrictClinicalModel


class RemediationPlan(StrictClinicalModel):
    """Cryptographically sealed clinical remediation plan with anti-replay bounds."""

    plan_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    patient_token: str = Field(..., min_length=1)
    action_type: ActionType
    risk_score: int = Field(..., ge=1, le=5)
    risk_grade: RiskGrade
    dry_run: bool = Field(default=False)
    quarantined: bool = Field(default=False)
    quarantine_reason: str | None = Field(default=None)
    execution_payload: dict[str, Any] = Field(default_factory=dict)
    rollback_steps: tuple[str, ...] = Field(default_factory=tuple)
    issued_at: datetime
    expires_at: datetime
    plan_digest: str = Field(default="")
    plan_signature: str = Field(default="")
