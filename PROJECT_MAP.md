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
- `docs/ARCHITECTURE.md` - Hexagonal system architecture, 6-agent pipeline & module matrix.
- `pyproject.toml` - PEP 517/621 packaging, Python 3.13+ deps, `pytest-timeout`, `ruff`, `mypy`.
- `.env.example` - Environment configuration template (no secrets).
- `README.md` - Root navigation hub, architecture overview, token matrix, and operational quick-start.
- `PROJECT_MAP.md` - Compact repository symbol and component index for targeted agent reads.
- `init_project.py` - Zero-dependency project bootstrapper supporting universal frameworks and MCP server templates.

## Scaffold Target Layout (`src/smartrx_safety_agents/`)
- `config.py` - Pydantic settings, model identifiers, memory/token thresholds, secrets.
- `models/` - Pydantic v2 contracts (`clinical.py` with 6 agent outputs, `ActionType` Enum, `remediation.py`, `audit.py`).
- `guardrails/` - `GuardrailEngine`, quarantine, deterministic HL7 FHIR R4 (`fhir_generator.py`), `rollback.py`, HMAC-SHA256 signing.
- `heuristics/` - Offline deterministic clinical engines (`ddi_engine.py`, `allergy_checker.py`, `dosing_validator.py`, `formulary_checker.py`, `phi_redactor.py`, `engine.py`).
- `config/drug_interactions.json` - Schema-validated static DDI, allergy cross-reactivity, NTI, renal/hepatic, Beer's Criteria & CMS catalog.
- `prompts/modules/` - Version-stamped (<80-line) clinical prompts for all 6 specialist agents.
- `agents/` - `MultiTierLLMClient` (`llm_client.py`), 6 specialists (`specialists.py`), `SmartRxOrchestrator` (`orchestrator.py`).
- `persistence/` - `AuditLedger` & `JsonlAuditExporter` (`ledger.py`): SQLite WAL hash-chained store, FileLock writes, MVCC reads & daily JSONL rotation/pruning.
- `api/` - `server.py` (FastAPI REST/SSE, 10MB guard, auth, `/api/v1/*`) & `mcp_server.py` (`smartrx://` stdio/SSE).
- `observability.py` - OpenTelemetry `trace_span`, `TelemetryManager` (`.shutdown()`), and thread-safe `InMemoryMetricsLedger`.
- `seed_data.py` - Synthetic HL7 FHIR R4 bundle seeder & `TC-001`–`TC-008` benchmark runner (zero PHI).
- `ui/` - `dashboard.py`: Three-Column Pharmacist HITL Workbench, BPMH diff, What-If Sandbox & 3-Tier traffic light.
- `cli.py` - Click CLI (`status`, `reconcile --dry-run`, `benchmark`, `verify-audit`, `serve`, `mcp`).

## Test Suite Layout (`tests/`)
- `test_models_clinical.py` - Contract validation, ActionType enum allowlist, NFKC normalization tests.
- `test_clinical_heuristics.py` - Benchmark `TC-001`–`TC-008`, `CatalogNotFoundError`, OCR NTI & PHI redaction tests.
- `test_guardrails_ledger.py` - FHIR overwrite, HMAC-SHA256, TTL/replay, idempotency & SQLite WAL hash-chain tests.
- `test_agents_orchestrator.py` - 6-agent pipeline, pre-LLM PHI scrubbing, 3-tier cascade, 3-turn circuit breaker, ledger chain.
- `test_api_mcp_cli.py` - FastAPI `/health`, `/api/v1/*`, 413/401/422 guards, MCP `smartrx://`, Click CLI tests.
- `test_mcp.py` - stdio and SSE transport protocols, 10MB limits, auth verification.
- `test_ledger.py` - SQLite WAL concurrency, MVCC read-bypass, migration tests.
- `test_phase9_hardening.py` - Cryptographic HMAC, anti-replay, Unicode normalization.
- `test_adversarial_regression.py` - Phase 12 zero-width bypass, boundary eGFR, WAL contention & MCP size tests.
- `test_ui_and_seeder.py` - Pharmacist HITL Workbench, BPMH diff, What-If swap, circuit breaker & `TC-001`–`TC-008` seeder tests.
- `test_observability_and_retention.py` - OpenTelemetry `trace_span`, `.shutdown()`, `InMemoryMetricsLedger`, and JSONL rotation/pruning tests.
- `.github/workflows/ci.yml` - Python 3.13/3.14 CI matrix, `ruff`, `mypy`, `pytest` (>=90% cov), `pip-audit`, license & secret scan.
- `Dockerfile` & `docker-compose.yml` - Multi-stage non-root (`smartrx` UID 10001) runtime image, `mem_limit: 2048m`, `/health` probe.
- `docker-compose.prod.yml` & `deploy/` - Prod compose, `aws-ecs-task-definition.json`, `azure-container-app.yaml`, `serverless-container.yaml`, deploy script.
- `docs/Ephemeral_Ledger_Architecture.md` - SQLite WAL POSIX volume requirements and JSONL object-storage sync architecture.
- `docs/SECURITY_HARDENING.md` - Phase 9 security controls matrix, `?apiKey` access-log advisory & `.env` hygiene.
- `docs/Cloud_Deployment_Guide.md` - AWS ECS/Fargate, Azure Container Apps, K8s, IAM, OIDC & blue/green rollback.
- `docs/MONITORING_AND_OBSERVABILITY.md` - Infra/RAM/WAL thresholds, API/MCP SLAs, AI governance & security alerts.
- `Blueprint_Production_Readiness_Report.md` - 8-pillar SRE Production Readiness Review (100/100 PASS).
- `buildprompt.md` - Reusable end-to-end master build playbook (Phases 0–12).
