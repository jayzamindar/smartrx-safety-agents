"""Dual-transport Model Context Protocol (MCP) server for SmartRx (`smartrx://`)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any, Final

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from smartrx_safety_agents.agents.orchestrator import SmartRxOrchestrator
from smartrx_safety_agents.heuristics.ddi_engine import load_catalog
from smartrx_safety_agents.models.clinical import (
    ClinicalOutput,
    NormalizedMedication,
    RiskGrade,
)
from smartrx_safety_agents.persistence.ledger import AuditLedger

PROTOCOL_VERSION: Final[str] = "2024-11-05"


def _jsonrpc_ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class SmartRxMCPServer:
    """JSON-RPC 2.0 MCP server supporting stdio and HTTP/SSE transports."""

    def __init__(
        self,
        *,
        orchestrator: SmartRxOrchestrator,
        ledger: AuditLedger,
        max_payload_bytes: int = 10_485_760,
    ) -> None:
        self._orchestrator = orchestrator
        self._ledger = ledger
        self._max_payload_bytes = max_payload_bytes

    async def handle_jsonrpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a JSON-RPC 2.0 MCP request."""
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") or {}
        if not isinstance(method, str) or not isinstance(params, dict):
            return _jsonrpc_err(req_id, -32600, "Invalid JSON-RPC request.")

        if method == "initialize":
            client_proto = str(params.get("protocolVersion", PROTOCOL_VERSION))
            if not client_proto.startswith("2024-"):
                return _jsonrpc_err(
                    req_id, -32602, f"Unsupported protocolVersion: {client_proto}"
                )
            return _jsonrpc_ok(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": "smartrx-safety-agents", "version": "0.1.0"},
                    "capabilities": {
                        "resources": {"listChanged": False},
                        "tools": {"listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                },
            )

        if method == "resources/list":
            return _jsonrpc_ok(
                req_id,
                {
                    "resources": [
                        {
                            "uri": "smartrx://catalog/interactions",
                            "name": "Clinical Drug Interaction & NTI Catalog",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "smartrx://audit/escalations",
                            "name": "Clinical Safety Escalation Ledger",
                            "mimeType": "application/json",
                        },
                    ]
                },
            )

        if method == "resources/read":
            uri = str(params.get("uri", ""))
            if uri == "smartrx://catalog/interactions":
                catalog = load_catalog()
                return _jsonrpc_ok(
                    req_id,
                    {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": catalog.model_dump_json(),
                            }
                        ]
                    },
                )
            if uri == "smartrx://audit/escalations":
                events = await asyncio.to_thread(self._ledger.get_events, limit=100)
                escalations = [
                    ev.model_dump(mode="json")
                    for ev in events
                    if ev.risk_grade == RiskGrade.RED or ev.quarantined
                ]
                return _jsonrpc_ok(
                    req_id,
                    {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(escalations, ensure_ascii=False),
                            }
                        ]
                    },
                )
            return _jsonrpc_err(req_id, -32602, f"Unknown resource URI: {uri}")

        if method == "tools/list":
            return _jsonrpc_ok(
                req_id,
                {
                    "tools": [
                        {
                            "name": "smartrx://reconcile/verify",
                            "description": (
                                "Run deterministic DDI, allergy, dosing, and 6-agent clinical "
                                "reconciliation returning signed HL7 FHIR R4 payloads."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "plan_id": {"type": "string"},
                                    "idempotency_key": {"type": "string"},
                                    "raw_patient_id": {"type": "string"},
                                    "raw_intake_text": {"type": "string"},
                                    "medications": {"type": "array"},
                                    "dry_run": {"type": "boolean"},
                                },
                                "required": [
                                    "plan_id",
                                    "idempotency_key",
                                    "raw_patient_id",
                                    "raw_intake_text",
                                ],
                            },
                        }
                    ]
                },
            )

        if method == "tools/call":
            tool_name = str(params.get("name", ""))
            if tool_name != "smartrx://reconcile/verify":
                return _jsonrpc_err(req_id, -32601, f"Unknown tool: {tool_name}")
            args = params.get("arguments") or {}
            meds = tuple(
                NormalizedMedication.model_validate(m) for m in args.get("medications", ())
            )
            clinical_raw = args.get("clinical")
            clinical = (
                ClinicalOutput.model_validate(clinical_raw) if clinical_raw is not None else None
            )
            state = await self._orchestrator.run_reconciliation(
                plan_id=str(args.get("plan_id", "mcp-plan-1")),
                idempotency_key=str(args.get("idempotency_key", "mcp-idem-1")),
                raw_patient_id=str(args.get("raw_patient_id", "MRN-MCP-0")),
                raw_intake_text=str(args.get("raw_intake_text", "")),
                raw_ehr_summary=str(args.get("raw_ehr_summary", "")),
                fallback_medications=meds,
                fallback_clinical=clinical,
                dry_run=bool(args.get("dry_run", False)),
            )
            result_payload = {
                "patient_token": state.patient_token,
                "liaison": state.liaison.model_dump(mode="json") if state.liaison else None,
                "remediation_plan": (
                    state.remediation_plan.model_dump(mode="json")
                    if state.remediation_plan
                    else None
                ),
            }
            return _jsonrpc_ok(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result_payload, ensure_ascii=False),
                        }
                    ]
                },
            )

        if method == "prompts/list":
            return _jsonrpc_ok(
                req_id,
                {
                    "prompts": [
                        {
                            "name": "clinical_reconciliation_review",
                            "description": (
                                "Structured pharmacist handoff prompt summarizing flagged DDIs, "
                                "allergy cross-reactivities, organ-function lab gaps, and FHIR R4."
                            ),
                            "arguments": [
                                {"name": "patient_token", "required": True},
                                {"name": "risk_grade", "required": True},
                            ],
                        }
                    ]
                },
            )

        if method == "prompts/get":
            prompt_name = str(params.get("name", ""))
            if prompt_name != "clinical_reconciliation_review":
                return _jsonrpc_err(req_id, -32602, f"Unknown prompt: {prompt_name}")
            p_args = params.get("arguments") or {}
            pt = str(p_args.get("patient_token", "pt_unknown"))
            grade = str(p_args.get("risk_grade", "YELLOW"))
            return _jsonrpc_ok(
                req_id,
                {
                    "description": "Pharmacist HITL reconciliation review handoff.",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": (
                                    f"Review medication reconciliation for {pt} "
                                    f"(RiskGrade={grade}). Verify deterministic DDI/allergy "
                                    "alerts, organ-function lab gaps, and HL7 FHIR R4 Bundle."
                                ),
                            },
                        }
                    ],
                },
            )

        return _jsonrpc_err(req_id, -32601, f"Method not found: {method}")

    async def handle_raw_line(self, raw_bytes: bytes) -> bytes:
        """Process a single raw byte frame enforcing the 10MB ceiling before UTF-8 decode."""
        if len(raw_bytes) > self._max_payload_bytes:
            err = _jsonrpc_err(None, -32600, "Payload exceeds 10MB ceiling.")
            return (json.dumps(err) + "\n").encode("utf-8")
        try:
            text = raw_bytes.decode("utf-8").strip()
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("JSON-RPC payload must be an object.")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            err = _jsonrpc_err(None, -32700, f"Parse error: {exc}")
            return (json.dumps(err) + "\n").encode("utf-8")

        resp = await self.handle_jsonrpc(payload)
        return (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")

    async def serve_stdio(self) -> None:
        """Run line-delimited JSON-RPC 2.0 loop over stdin/stdout with stderr logging."""
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
        buffer = bytearray()
        read_fn = getattr(sys.stdin.buffer, "read1", sys.stdin.buffer.read)
        try:
            while True:
                chunk = await asyncio.to_thread(read_fn, 4096)
                if not chunk:
                    if buffer:
                        out = await self.handle_raw_line(bytes(buffer))
                        sys.stdout.buffer.write(out)
                        sys.stdout.buffer.flush()
                    break
                buffer.extend(chunk)
                if len(buffer) > self._max_payload_bytes:
                    out = await self.handle_raw_line(bytes(buffer))
                    sys.stdout.buffer.write(out)
                    sys.stdout.buffer.flush()
                    buffer.clear()
                    continue
                while b"\n" in buffer:
                    nl_idx = buffer.index(b"\n")
                    line = bytes(buffer[:nl_idx])
                    del buffer[: nl_idx + 1]
                    if line.strip():
                        out = await self.handle_raw_line(line)
                        sys.stdout.buffer.write(out)
                        sys.stdout.buffer.flush()
        except (EOFError, BrokenPipeError):
            return


def attach_mcp_routes(
    app: FastAPI,
    mcp_server: SmartRxMCPServer,
    auth_dep: Callable[..., Coroutine[Any, Any, None]],
) -> None:
    """Mount authenticated /sse, /messages, /v1/sse, and /v1/messages MCP endpoints."""

    async def _mcp_sse() -> StreamingResponse:
        async def _events() -> AsyncIterator[str]:
            yield "event: endpoint\ndata: /v1/messages\n\n"

        return StreamingResponse(_events(), media_type="text/event-stream")

    async def _mcp_messages(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(
                _jsonrpc_err(None, -32600, "Invalid JSON-RPC request."),
                status_code=400,
            )
        resp = await mcp_server.handle_jsonrpc(body)
        return JSONResponse(resp, status_code=200)

    for path in ("/sse", "/v1/sse"):
        app.add_api_route(path, _mcp_sse, methods=["GET"], dependencies=[Depends(auth_dep)])
    for path in ("/messages", "/v1/messages"):
        app.add_api_route(path, _mcp_messages, methods=["POST"], dependencies=[Depends(auth_dep)])
