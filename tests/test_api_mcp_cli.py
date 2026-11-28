"""Comprehensive verification suite for FastAPI gateway, MCP server, and Click CLI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from pydantic import SecretStr

from smartrx_safety_agents.api.server import SensitiveQueryParamFilter, create_app
from smartrx_safety_agents.cli import main as cli_main
from smartrx_safety_agents.config import Settings
from smartrx_safety_agents.persistence.ledger import AuditLedger

_TEST_API_KEY = "test-mcp-api-key-at-least-24-chars!"


def _make_settings(tmp_path: Path, *, max_bytes: int = 10_485_760) -> Settings:
    return Settings(
        smartrx_db_path=tmp_path / "api_ledger.db",
        require_auth=True,
        mcp_api_key=SecretStr(_TEST_API_KEY),
        plan_signing_secret=SecretStr("test-signing-secret-at-least-32-chars!"),
        max_payload_size_bytes=max_bytes,
    )


def test_health_auth_and_sensitive_log_filter(tmp_path: Path) -> None:
    app = create_app(settings=_make_settings(tmp_path))
    with TestClient(app) as client:
        h1 = client.get("/health")
        assert h1.status_code == 200
        assert h1.json()["status"] == "ok"
        assert h1.json()["wal_mode"] is True

        h2 = client.get("/v1/health")
        assert h2.status_code == 200

        # Unauthorized without key -> 401
        unauth = client.get("/api/v1/audit/verify")
        assert unauth.status_code == 401

        # Wrong key -> 401
        wrong = client.get("/api/v1/audit/verify", headers={"X-API-Key": "wrong-key"})
        assert wrong.status_code == 401

        # Authorized via query param -> 200
        ok = client.get(f"/api/v1/audit/verify?apiKey={_TEST_API_KEY}")
        assert ok.status_code == 200
        assert ok.json()["chain_valid"] is True

    # Verify SensitiveQueryParamFilter masks apiKey in uvicorn access logs
    log_filter = SensitiveQueryParamFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='GET /v1/sse?apiKey=%s HTTP/1.1" 200',
        args=(_TEST_API_KEY,),
        exc_info=None,
    )
    assert log_filter.filter(record) is True
    assert _TEST_API_KEY not in record.getMessage()
    assert "apiKey=***" in record.getMessage()


def test_reconcile_stream_and_adjudicate_hitl_enforcement(tmp_path: Path) -> None:
    app = create_app(settings=_make_settings(tmp_path))
    headers = {"Authorization": f"Bearer {_TEST_API_KEY}"}
    with TestClient(app) as client:
        rec_resp = client.post(
            "/api/v1/reconcile",
            headers=headers,
            json={
                "plan_id": "api-plan-1",
                "idempotency_key": "api-idem-1",
                "raw_patient_id": "MRN-API-1",
                "raw_intake_text": "Prescribed warfarin 5mg daily",
                "raw_ehr_summary": "Active amiodarone 200mg daily",
                "medications": [
                    {
                        "rxcui": "11289",
                        "scd_name": "warfarin sodium 5 mg",
                        "raw_name": "warfarin 5mg",
                        "dose_mg": 5.0,
                        "frequency": "once daily",
                        "route": "oral",
                        "is_nti": True,
                        "ocr_confidence": 0.99,
                    }
                ],
                "clinical": {
                    "patient_token": "pt_api",
                    "active_medications": [
                        {
                            "rxcui": "703",
                            "scd_name": "amiodarone 200 mg",
                            "raw_name": "amiodarone 200mg",
                            "dose_mg": 200.0,
                            "frequency": "once daily",
                            "route": "oral",
                        }
                    ],
                    "egfr_ml_min": 70.0,
                },
            },
        )
        assert rec_resp.status_code == 200
        body = rec_resp.json()
        assert body["safety"]["overall_risk_grade"] == "RED"
        assert body["remediation_plan"]["execution_payload"]["resourceType"] == "Bundle"

        # SSE stream progress
        stream_resp = client.get(
            "/api/v1/reconcile/stream?plan_id=api-plan-1&patient_id=pt_api",
            headers=headers,
        )
        assert stream_resp.status_code == 200
        assert "event: intake_history" in stream_resp.text
        assert "event: sealed" in stream_resp.text

        # Tier 1 RED adjudication missing justification/NPI -> 422
        bad_adj = client.post(
            "/api/v1/adjudicate",
            headers=headers,
            json={
                "plan_id": "api-plan-1",
                "idempotency_key": "adj-idem-1",
                "patient_token": body["patient_token"],
                "decision": "Accept",
                "risk_grade": "RED",
            },
        )
        assert bad_adj.status_code == 422

        # Valid Tier 1 RED adjudication -> 200 & persisted in AuditLedger
        good_adj = client.post(
            "/api/v1/adjudicate",
            headers=headers,
            json={
                "plan_id": "api-plan-1",
                "idempotency_key": "adj-idem-2",
                "patient_token": body["patient_token"],
                "decision": "Accept",
                "risk_grade": "RED",
                "clinical_justification_code": "CJC-INR-MONITOR",
                "npi_attestation": "1234567890",
            },
        )
        assert good_adj.status_code == 200
        assert good_adj.json()["status"] == "recorded"

        audit_resp = client.get("/api/v1/audit/verify", headers=headers)
        assert audit_resp.status_code == 200
        assert audit_resp.json()["chain_valid"] is True
        assert audit_resp.json()["event_count"] == 7


def test_payload_size_limit_rejects_oversized_requests_413(tmp_path: Path) -> None:
    app = create_app(settings=_make_settings(tmp_path, max_bytes=1024))
    headers = {"X-API-Key": _TEST_API_KEY}
    with TestClient(app) as client:
        # Streaming/body > 1024 bytes -> 413
        oversized = {"raw_intake_text": "x" * 2048}
        resp = client.post("/api/v1/reconcile", headers=headers, json=oversized)
        assert resp.status_code == 413

        # Explicit Content-Length > 1024 -> 413 fast-path
        resp_hdr = client.post(
            "/api/v1/reconcile",
            headers={**headers, "Content-Length": "20480"},
            content=b"{}",
        )
        assert resp_hdr.status_code == 413


@pytest.mark.asyncio
async def test_mcp_server_resources_tools_prompts_and_stdio_limit(tmp_path: Path) -> None:
    app = create_app(settings=_make_settings(tmp_path))
    headers = {"X-API-Key": _TEST_API_KEY}
    with TestClient(app) as client:
        init_resp = client.post(
            "/v1/messages",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            },
        )
        assert init_resp.status_code == 200
        assert init_resp.json()["result"]["protocolVersion"] == "2024-11-05"

        res_list = client.post(
            "/v1/messages",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
        )
        uris = [r["uri"] for r in res_list.json()["result"]["resources"]]
        assert "smartrx://catalog/interactions" in uris
        assert "smartrx://audit/escalations" in uris

        res_cat = client.post(
            "/v1/messages",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/read",
                "params": {"uri": "smartrx://catalog/interactions"},
            },
        )
        assert "ddi_pairs" in res_cat.json()["result"]["contents"][0]["text"]

        res_esc = client.post(
            "/v1/messages",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 31,
                "method": "resources/read",
                "params": {"uri": "smartrx://audit/escalations"},
            },
        )
        assert res_esc.status_code == 200

        tools_list = client.post(
            "/v1/messages",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 32, "method": "tools/list", "params": {}},
        )
        assert tools_list.json()["result"]["tools"][0]["name"] == "smartrx://reconcile/verify"

        prompts_list = client.post(
            "/v1/messages",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 33, "method": "prompts/list", "params": {}},
        )
        assert (
            prompts_list.json()["result"]["prompts"][0]["name"] == "clinical_reconciliation_review"
        )

        bad_proto = client.post(
            "/v1/messages",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 34,
                "method": "initialize",
                "params": {"protocolVersion": "1999-01-01"},
            },
        )
        assert bad_proto.json()["error"]["code"] == -32602

        unknown_method = client.post(
            "/v1/messages",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 35, "method": "unknown/method", "params": {}},
        )
        assert unknown_method.json()["error"]["code"] == -32601

        tool_call = client.post(
            "/v1/messages",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "smartrx://reconcile/verify",
                    "arguments": {
                        "plan_id": "mcp-p1",
                        "idempotency_key": "mcp-i1",
                        "raw_patient_id": "MRN-MCP-1",
                        "raw_intake_text": "Lisinopril 10mg",
                        "dry_run": True,
                    },
                },
            },
        )
        assert tool_call.status_code == 200
        tool_text = tool_call.json()["result"]["content"][0]["text"]
        assert "remediation_plan" in tool_text

        prompt_get = client.post(
            "/v1/messages",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "prompts/get",
                "params": {
                    "name": "clinical_reconciliation_review",
                    "arguments": {"patient_token": "pt_1", "risk_grade": "RED"},
                },
            },
        )
        assert "RiskGrade=RED" in prompt_get.json()["result"]["messages"][0]["content"]["text"]

    # Verify stdio raw-line 10MB ceiling enforcement
    mcp_srv = app.state.mcp_server
    mcp_srv._max_payload_bytes = 128
    err_bytes = await mcp_srv.handle_raw_line(b"{" + b"a" * 200 + b"}")
    err_obj = json.loads(err_bytes.decode("utf-8"))
    assert err_obj["error"]["code"] == -32600


def test_cli_subcommands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "cli_ledger.db"
    monkeypatch.setenv("SMARTRX_DB_PATH", str(db_path))
    runner = CliRunner()

    st = runner.invoke(cli_main, ["status"])
    assert st.exit_code == 0
    assert "smartrx-safety-agents" in st.output

    bm = runner.invoke(cli_main, ["benchmark"])
    assert bm.exit_code == 0
    for tc in ("TC-001", "TC-002", "TC-003", "TC-004", "TC-005", "TC-006", "TC-007", "TC-008"):
        assert tc in bm.output

    rec = runner.invoke(cli_main, ["reconcile", "--dry-run"])
    assert rec.exit_code == 0
    rec_json: dict[str, Any] = json.loads(rec.output)
    assert rec_json["dry_run"] is True

    va = runner.invoke(cli_main, ["verify-audit", "--db-path", str(db_path)])
    assert va.exit_code == 0
    assert json.loads(va.output)["chain_valid"] is True
    assert AuditLedger(db_path).verify_chain_integrity() is True
