# Project Map — Universal Enterprise AI Agent Blueprint

> Compact repository index for targeted reads (< 60 lines).
> Runtime: Python 3.13+ | Architecture: Clean Modular Hexagonal

## Master Governance & Specification Documents
- `GEMINI.md` - Master constitution, security invariants, operational rules, and Phase-Batched protocol.
- `Enterprise_Blueprint.md` - 12-phase master engineering plan, Definition of Done, and active checklist.
- `Blueprint_Repo_Baseline_AuditReport.md` - Phase 0.1 forensic baseline audit across 10 enterprise dimensions.
- `Blueprint_Debug_Log.md` - Incident debugging ledger and forensic loophole registry (`GEM-LH-*`, `EBP-LH-*`).
- `AUDIT_REMEDIATION_LOG.md` - Standardized chronological ledger of feature additions and security remediations.
- `docs/URD.md` - User Requirements Document: 6-agent squad, BPMH, 3-tier HITL, and SmartRx MCP specs.
- `docs/PRD.md` - Product Requirements Document: personas, FS-1 to FS-8, edge cases, and KPIs.
- `docs/TRD.md` - Technical Requirements Document: pipeline architecture, Pydantic schemas, HMAC, WAL & `TC-001`–`TC-008`.
- `pyproject.toml` - PEP 517/621 packaging, Python 3.13+ deps, `pytest-timeout`, `ruff`, `mypy`.
- `.env.example` - Environment configuration template (no secrets).
- `README.md` - Root navigation hub, architecture overview, token matrix, and operational quick-start.
- `PROJECT_MAP.md` - Compact repository symbol and component index for targeted agent reads.
- `init_project.py` - Zero-dependency project bootstrapper supporting universal frameworks and MCP server templates.

## Scaffold Target Layout (`src/smartrx_safety_agents/`)
- `config.py` - Pydantic settings, model identifiers, memory/token thresholds, secrets.
- `models/` - Pydantic v2 contracts (`clinical.py` with 6 agent outputs, `ActionType` Enum, `remediation.py`, `audit.py`).
- `guardrails/` - Safety scoring, quarantine patterns, deterministic HL7 FHIR R4 (`fhir_generator.py`) & rollback synthesis.
- `heuristics/` - Offline deterministic clinical engines (`ddi_engine.py`, `allergy_checker.py`, `dosing_validator.py`, `formulary_checker.py`, `phi_redactor.py`).
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
