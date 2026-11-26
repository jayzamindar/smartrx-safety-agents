# Project Map — Universal Enterprise AI Agent Blueprint

> Compact repository index for targeted reads (< 60 lines).
> Runtime: Python 3.13+ | Architecture: Clean Modular Hexagonal

## Master Governance Documents
- `GEMINI.md` - Master constitution, security invariants, operational rules, and Phase-Batched protocol.
- `Enterprise_Blueprint.md` - 12-phase master engineering plan, Definition of Done, and active checklist.
- `Blueprint_Debug_Log.md` - Incident debugging ledger and forensic loophole registry (`GEM-LH-*`, `EBP-LH-*`).
- `AUDIT_REMEDIATION_LOG.md` - Standardized chronological ledger of feature additions and security remediations.
- `README.md` - Root navigation hub, architecture overview, token matrix, and operational quick-start.
- `PROJECT_MAP.md` - Compact repository symbol and component index for targeted agent reads.
- `init_project.py` - Zero-dependency project bootstrapper supporting universal frameworks (LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, direct SDKs), RAG, and MCP server templates.

## Scaffold Target Layout (`src/smartrx_safety_agents/`)
- `config.py` - Pydantic settings, model identifiers, memory/token thresholds, secrets.
- `models/` - Pydantic v2 data contracts, ActionType Enum, telemetry, plans.
- `guardrails/` - Safety scoring, quarantine patterns, deterministic IAM/rollback synthesis.
- `heuristics/` - Offline deterministic rule engines, pricing catalog lookups.
- `reasoner/` - Gemini client (thinkingBudget, responseSchema), OpenRouter fallback.
- `ledger/` - SQLite WAL persistent audit store with per-operation FileLock.
- `mcp/` - Dual-transport MCP server (stdio JSON-RPC & Starlette SSE).
- `observability.py` - OpenTelemetry spans, metrics, and structured logging.
- `cli.py` - Click console entrypoint commands (`smartrx-safety-agents`).

## Test Suite Layout (`tests/`)
- `test_schemas.py` - Contract validation, ActionType enum allowlist tests.
- `test_heuristics.py` - Heuristic rule coverage, catalog fallback verification.
- `test_reasoner.py` - LLM reasoning, responseSchema sanitization, cascade tests.
- `test_mcp.py` - stdio and SSE transport protocols, 10MB limits, auth verification.
- `test_ledger.py` - SQLite WAL concurrency, MVCC read-bypass, migration tests.
- `test_phase9_hardening.py` - Cryptographic HMAC, anti-replay, Unicode normalization.
