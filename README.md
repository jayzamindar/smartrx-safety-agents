# SmartRx Safety Agents (`smartrx-safety-agents`)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.13+" />
  <img src="https://img.shields.io/badge/Pydantic-v2%20Frozen-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic v2" />
  <img src="https://img.shields.io/badge/Standard-HL7%20FHIR%20R4-0078D4?style=for-the-badge" alt="HL7 FHIR R4" />
  <img src="https://img.shields.io/badge/Protocol-MCP%20stdio%20%2B%20SSE-blueviolet?style=for-the-badge" alt="MCP Protocol" />
  <img src="https://img.shields.io/badge/Docker-Non--Root%20Read--Only-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Non-Root" />
  <img src="https://img.shields.io/badge/Test%20Coverage-92.84%25-brightgreen?style=for-the-badge" alt="92.84% Test Coverage" />
  <img src="https://img.shields.io/badge/Release-v1.0.0-success?style=for-the-badge" alt="Release v1.0.0" />
</p>

---

## Why This Project Was Created & What It Does

When patients move between hospitals, clinics, and pharmacies, medication lists often get out of sync—causing dangerous drug-drug interactions, missed allergies, or wrong doses for kidney and liver function. While modern LLMs are great at reading messy clinical notes and intake text, **LLMs cannot be trusted to write clinical orders directly** because even a rare hallucination in a prescription or HL7 FHIR payload can harm a patient.

**`smartrx-safety-agents` solves this by acting as a zero-trust clinical safety gatekeeper.** It uses AI only for structured intake and reasoning—while every drug-drug interaction check, allergy cross-reactivity check, renal/hepatic dosing bound, and final HL7 FHIR R4 order payload is **deterministically verified and overwritten** by hard-coded clinical rules, sealed with cryptographic HMAC-SHA256 signatures, and logged to a tamper-evident audit ledger before any pharmacist approves or rejects it.

---

## Architecture at a Glance

- **6-Agent Clinical Squad (`SmartRxOrchestrator`):** `IntakeAgent` & `ClinicalHistoryAgent` (parallel extraction after pre-LLM HIPAA PHI scrubbing) $\to$ `SafetyAuditorAgent` (**deterministic-first** gate) $\to$ `InsuranceAgent` $\to$ `PharmacistLiaisonAgent` $\leftrightarrow$ `AdversarialCriticAgent` (3-turn `HALT_FOR_HUMAN` circuit breaker).
- **3-Tier Resilience Cascade (`MultiTierLLMClient`):** Primary **Gemini 3.8 Flash High** (`thinkingBudget=2048`, `maxOutputTokens=8192`, OpenAPI 3.0 `clean_gemini_schema`) $\to$ Secondary **OpenRouter** (`<think>` tag stripping) $\to$ Tertiary **Offline Deterministic Heuristics** (`100%` uptime during API outages, `CatalogNotFoundError` fail-closed).
- **Zero-Hallucination Guardrails (`GuardrailEngine`):** Unconditionally discards LLM-synthesized payloads and overwrites `execution_payload` with deterministic HL7 FHIR R4 JSON (`MedicationRequest`, `DetectedIssue`, `Task`), quarantines invalid `ActionType`s or unmitigated Risk $\ge 3$ actions, and seals every plan with canonical JSON HMAC-SHA256 + `expires_at` ($\le 300\text{s}$) anti-replay nonces.
- **SQLite WAL MVCC & Non-Root Container:** Per-operation `FileLock` on writes with lock-free MVCC reads, SHA-256 hash-chained audit rows, daily JSONL rotation/pruning, dual-layer 10MB body guards (`413`), timing-safe `MCP_API_KEY` auth (`401`), and a `python:3.13-slim` non-root (`UID 10001`), `read_only: true` Docker image.

---

## Quick Start (Local & Docker)

```bash
# 1. Configure environment (never commit .env)
cp .env.example .env

# 2. Run the full verification suite inside smartrx-dev (59 tests, 92.84% coverage)
docker run --rm -v "${PWD}:/app" smartrx-dev sh -c \
  "ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && pytest -q --tb=short --cov=src/smartrx_safety_agents --cov-report=term:skip-covered --cov-fail-under=90"

# 3. Launch the hardened production container and probe /health
docker compose -f docker-compose.prod.yml up -d
curl http://127.0.0.1:8080/health
```

### CLI Entrypoints (`smartrx-safety-agents`)
| Command | Purpose |
|---|---|
| `smartrx-safety-agents status` | Inspect active configuration and SQLite WAL ledger health. |
| `smartrx-safety-agents reconcile --dry-run` | Run dry-run medication reconciliation without mutating EHR state. |
| `smartrx-safety-agents benchmark` | Execute deterministic `TC-001`–`TC-008` clinical safety benchmarks. |
| `smartrx-safety-agents verify-audit` | Verify SHA-256 hash-chain integrity across the SQLite WAL audit ledger. |
| `smartrx-safety-agents serve` | Start the FastAPI REST & SSE gateway on port `8080`. |
| `smartrx-safety-agents mcp` | Start the `smartrx://` Model Context Protocol server (`stdio` or SSE). |

---

## Documentation & Governance Navigation Hub

### Technical, Security & Operational Specifications (`docs/` & Playbooks)
| Document | What It Does |
|---|---|
| [`docs/URD.md`](docs/URD.md) | Defines user personas, 6-agent BPMH workflows, 3-tier HITL thresholds, and `smartrx://` MCP requirements. |
| [`docs/PRD.md`](docs/PRD.md) | Specifies product vision, functional specifications (`FS-1`–`FS-8`), clinical edge cases, and release KPIs. |
| [`docs/TRD.md`](docs/TRD.md) | Details pipeline architecture, Pydantic v2 contracts, HMAC/WAL specs, and `TC-001`–`TC-008` test cases. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Presents the hexagonal system architecture, Mermaid data flow, and module responsibility matrix. |
| [`docs/SECURITY_HARDENING.md`](docs/SECURITY_HARDENING.md) | Maps all 22 Phase 9 security controls, `?apiKey=` access-log guidance, and `.env` hygiene rules. |
| [`docs/Cloud_Deployment_Guide.md`](docs/Cloud_Deployment_Guide.md) | Provides AWS ECS/Fargate, Azure Container Apps, Kubernetes, IAM, OIDC CI/CD, and rollback runbooks. |
| [`docs/MONITORING_AND_OBSERVABILITY.md`](docs/MONITORING_AND_OBSERVABILITY.md) | Establishes CPU/RAM/WAL/`audit_logs/` thresholds, API/MCP SLAs, AI governance, and alert routing. |
| [`docs/Ephemeral_Ledger_Architecture.md`](docs/Ephemeral_Ledger_Architecture.md) | Documents POSIX persistent volume requirements for SQLite WAL and JSONL object-storage sync. |
| [`buildprompt.md`](buildprompt.md) | Provides copy-pasteable phase-by-phase build prompts (Phases 0–12) to reproduce or adapt `v1.0.0`. |

### Governance & Audit Ledgers
| Document | What It Does |
|---|---|
| [`GEMINI.md`](GEMINI.md) | Master engineering constitution defining non-negotiable security, typing, testing, and I/O invariants. |
| [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) | 12-phase master engineering roadmap, Definition of Done, and 100% completed task checklist. |
| [`PROJECT_MAP.md`](PROJECT_MAP.md) | Compact (`< 60` lines) repository symbol index enabling targeted reads without context rot. |
| [`Blueprint_Repo_Baseline_AuditReport.md`](Blueprint_Repo_Baseline_AuditReport.md) | Phase 0.1 10-dimension forensic baseline audit and technical debt evaluation. |
| [`Blueprint_Production_Readiness_Report.md`](Blueprint_Production_Readiness_Report.md) | Phase 10.2 8-pillar SRE Production Readiness Review (`100/100 PASS`). |
| [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md) | Forensic incident debugging ledger and historical loophole defense registry. |
| [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md) | Chronological ledger of all feature additions, security remediations, and verbatim test proofs. |
