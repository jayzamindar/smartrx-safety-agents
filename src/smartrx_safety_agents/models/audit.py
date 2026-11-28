"""Strict Pydantic v2 audit ledger event contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from smartrx_safety_agents.models.clinical import ActionType, RiskGrade, StrictClinicalModel


class AuditEventRecord(StrictClinicalModel):
    """Immutable append-only hash-chained audit ledger row."""

    event_id: int | None = Field(default=None)
    plan_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    patient_token: str = Field(..., min_length=1)
    agent_name: str = Field(..., min_length=1)
    model_version: str = Field(..., min_length=1)
    action_type: ActionType
    risk_grade: RiskGrade
    quarantined: bool = Field(default=False)
    hitl_override_reason: str | None = Field(default=None)
    payload_json: str = Field(..., min_length=2)
    prev_row_hash: str = Field(..., min_length=64, max_length=64)
    row_hash: str = Field(..., min_length=64, max_length=64)
    created_at: datetime
