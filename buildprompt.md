# Master Build Playbook (`buildprompt.md`)

**Project:** `smartrx-safety-agents` (`v1.0.0`)  
**Purpose:** Reusable, end-to-end phase-by-phase build playbook for engineers and autonomous AI coding agents to reproduce or adapt `smartrx-safety-agents` from scratch in compliance with [`GEMINI.md`](GEMINI.md) and [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md).

---

## 1. Architectural Overview & Prerequisites

`smartrx-safety-agents` is a **hexagonal, deterministic-first clinical pharmacy medication reconciliation platform**:
- **6-Agent Clinical Squad:** `IntakeAgent`, `ClinicalHistoryAgent`, `SafetyAuditorAgent` (deterministic-first), `InsuranceAgent`, `PharmacistLiaisonAgent`, and `AdversarialCriticAgent` (3-turn `HALT_FOR_HUMAN` circuit breaker).
- **Zero-Hallucination Guardrails:** `GuardrailEngine` unconditionally discards LLM-synthesized payloads, overwrites `execution_payload` with deterministic HL7 FHIR R4 (`MedicationRequest`, `DetectedIssue`, `Task`), enforces `ActionType` allowlists, and seals plans with canonical JSON HMAC-SHA256 + `expires_at` ($\le 300\text{s}$) anti-replay nonces.
- **3-Tier Resilience:** Primary Gemini (`gemini-3.8-flash-high`, `thinkingBudget=2048`, `maxOutputTokens=8192`) $\to$ Secondary OpenRouter (`<think>` stripping) $\to$ Tertiary `DeterministicClinicalEngine`.

### Prerequisites
- **Python 3.13+**
- **Docker Desktop** (for `smartrx-dev` isolated Linux verification and non-root `python:3.13-slim` builds)
- **Git**

---

## 2. Copy-Pasteable Phase-by-Phase Build Prompts

### Phase 0–1: Governance Specs, Packaging & Security Hygiene
```text
@GEMINI.md @Enterprise_Blueprint.md @PROJECT_MAP.md @AUDIT_REMEDIATION_LOG.md
Execute Phases 0–1:
1. Author/harmonize docs/URD.md, docs/PRD.md, docs/TRD.md, and docs/ARCHITECTURE.md.
2. Create pyproject.toml (PEP 517/621, Python 3.13+, pydantic v2, fastapi, uvicorn, httpx, filelock, opentelemetry-api/sdk, ruff, mypy, pytest-timeout=15, pytest-cov >=90%), .env.example (zero secrets), and .gitignore (excluding .env, .venv/, *.db*).
3. Implement src/smartrx_safety_agents/config.py (Settings with fail-closed production secret checks for PLAN_SIGNING_SECRET, SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET, MCP_API_KEY) and generate requirements.lock.
4. Verify git check-ignore -v .env and run ruff/mypy/pytest inside smartrx-dev.
```

### Phase 2–3: Pydantic v2 Contracts, 6-Agent Orchestrator & 3-Tier Cascade
```text
@GEMINI.md @Enterprise_Blueprint.md @PROJECT_MAP.md @AUDIT_REMEDIATION_LOG.md
Execute Phases 2–3:
1. Implement src/smartrx_safety_agents/models/ (clinical.py, remediation.py, audit.py) using ConfigDict(extra="forbid", frozen=True) and canonical ActionType Literal Enum.
2. Author version-stamped clinical prompts (<80 lines each) under prompts/modules/.
3. Implement src/smartrx_safety_agents/agents/llm_client.py (MultiTierLLMClient: Primary Gemini -> Secondary OpenRouter with strip_think_tags() -> Tertiary Deterministic Fallback; clean_gemini_schema() with $defs resolution, anyOf nullable collapse, ALLOWED_GEMINI_FIELDS, and execution_payload exclusion; pre-LLM PHIRedactor; 8192 output token cap).
4. Implement specialists.py (6 agents) and orchestrator.py (SmartRxOrchestrator with 3-turn HALT_FOR_HUMAN circuit breaker).
5. Add unit tests in tests/test_models_clinical.py and tests/test_agents_orchestrator.py; verify inside smartrx-dev.
```

### Phase 4–5: Clinical Heuristics, FHIR R4 Guardrails, HMAC Signing & MCP Gateway
```text
@GEMINI.md @Enterprise_Blueprint.md @PROJECT_MAP.md @AUDIT_REMEDIATION_LOG.md
Execute Phases 4–5:
1. Author config/drug_interactions.json and implement src/smartrx_safety_agents/heuristics/ (ddi_engine.py with CatalogNotFoundError, allergy_checker.py, dosing_validator.py, formulary_checker.py, phi_redactor.py, engine.py) enforcing Unicode NFKC + zero-width normalization (normalize_clinical_identifier) and TC-001–TC-008.
2. Implement src/smartrx_safety_agents/guardrails/ (fhir_generator.py, rollback.py, engine.py) with deterministic HL7 FHIR R4 overwriting, ActionType/missing-rollback quarantine, canonical JSON HMAC-SHA256 signing, <=300s expires_at anti-replay, and idempotency_key deduplication.
3. Implement src/smartrx_safety_agents/api/server.py (FastAPI REST/SSE, dual-layer 10MB PayloadSizeLimitMiddleware with BaseException streaming 413, timing-safe hmac.compare_digest() auth, SensitiveQueryParamFilter) and mcp_server.py (smartrx:// stdio + SSE JSON-RPC 2.0), plus cli.py.
4. Add tests in tests/test_clinical_heuristics.py, tests/test_guardrails_ledger.py, and tests/test_api_mcp_cli.py; verify inside smartrx-dev.
```

### Phase 6–7: SQLite WAL Ledger, OpenTelemetry, CI/CD & Non-Root Docker
```text
@GEMINI.md @Enterprise_Blueprint.md @PROJECT_MAP.md @AUDIT_REMEDIATION_LOG.md
Execute Phases 6–7:
1. Implement src/smartrx_safety_agents/persistence/ledger.py (AuditLedger with PRAGMA journal_mode=WAL, PRAGMA busy_timeout=5000, PRAGMA user_version migrations, per-op FileLock writes, MVCC reads, SHA-256 hash chain; JsonlAuditExporter with 50MB daily rotation and 30d/500MB pruning).
2. Implement src/smartrx_safety_agents/observability.py (TelemetryManager with .shutdown(), trace_span, InMemoryMetricsLedger), seed_data.py, and ui/dashboard.py (HITL Workbench).
3. Author .github/workflows/ci.yml (Python 3.13/3.14 matrix, ruff, mypy, pytest >=90% cov, pip-audit, license & secret scan), multi-stage non-root Dockerfile (UID 10001 smartrx, /health), and docker-compose.yml (mem_limit: 2048m).
4. Add tests in tests/test_observability_and_retention.py and tests/test_ui_and_seeder.py; verify live container /health and smartrx-dev gate.
```

### Phase 8–12: Cloud Deployment, Security Regression Suite, SRE Runbooks & v1.0.0 Release
```text
@GEMINI.md @Enterprise_Blueprint.md @PROJECT_MAP.md @AUDIT_REMEDIATION_LOG.md
Execute Phases 8–12:
1. Author docker-compose.prod.yml (read_only: true), Dockerfile.serverless, deploy/serverless-container.yaml, deploy/smartrx-safety-agents-deploy.sh, and docs/Ephemeral_Ledger_Architecture.md.
2. Author docs/SECURITY_HARDENING.md and tests/test_phase9_hardening.py covering all 22 Phase 9 security controls.
3. Author docs/Cloud_Deployment_Guide.md, Blueprint_Production_Readiness_Report.md (8-pillar 100/100 PASS), and docs/MONITORING_AND_OBSERVABILITY.md.
4. Run adversarial edge-case audit, add tests/test_adversarial_regression.py, synchronize README.md and all docs/*.md relative links, check off Enterprise_Blueprint.md, verify in smartrx-dev, and tag v1.0.0.
```

---

## 3. Verification Command (`smartrx-dev`)

Run the full lint, formatting, static typing, and test coverage gate before any commit or release tag:

```bash
docker run --rm -v "${PWD}:/app" smartrx-dev sh -c \
  "ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && pytest -q --tb=short --cov=src/smartrx_safety_agents --cov-report=term:skip-covered --cov-fail-under=90"
```
