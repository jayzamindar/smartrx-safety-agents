# SmartRx Safety Agents (`smartrx-safety-agents`)

**Enterprise Clinical Pharmacy Medication Reconciliation & Zero-Hallucination Safety Guardrails**

> **Status:** `v1.0.0` Production Release (`59` automated tests passing, `92.84%` coverage, `100/100` SRE PRR)  
> **Runtime:** Python 3.13+ | FastAPI + SSE + MCP (`smartrx://`) | SQLite WAL + HL7 FHIR R4

---

## 1. Master Navigation Hub

### Governance & Engineering Ledgers
| Document | Role |
|---|---|
| [`GEMINI.md`](GEMINI.md) | Master engineering constitution, security invariants, and non-negotiable operational rules. |
| [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) | 12-phase master engineering roadmap, Definition of Done, and completion checklist. |
| [`PROJECT_MAP.md`](PROJECT_MAP.md) | Compact (`< 60` lines) repository symbol and component index for targeted reads. |
| [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md) | Chronological ledger of feature additions, security remediations, and verification proofs. |
| [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md) | Incident debugging ledger and historical forensic loophole registry. |
| [`Blueprint_Repo_Baseline_AuditReport.md`](Blueprint_Repo_Baseline_AuditReport.md) | Phase 0.1 10-dimension forensic baseline audit report. |
| [`Blueprint_Production_Readiness_Report.md`](Blueprint_Production_Readiness_Report.md) | Phase 10.2 8-pillar SRE Production Readiness Review (`100/100 PASS`). |

### Technical, Security & Operational Documentation (`docs/`)
| Document | Role |
|---|---|
| [`docs/URD.md`](docs/URD.md) | User Requirements Document: 6-agent clinical squad, BPMH reconciliation, 3-tier HITL, and MCP specs. |
| [`docs/PRD.md`](docs/PRD.md) | Product Requirements Document: clinical personas, functional specs `FS-1`–`FS-8`, edge cases, and KPIs. |
| [`docs/TRD.md`](docs/TRD.md) | Technical Requirements Document: pipeline architecture, Pydantic contracts, HMAC, WAL, and `TC-001`–`TC-008`. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Hexagonal system architecture, 6-agent data flow, and module responsibility matrix. |
| [`docs/SECURITY_HARDENING.md`](docs/SECURITY_HARDENING.md) | Phase 9 22-control security matrix, `?apiKey=` access-log advisory, and `.env` hygiene. |
| [`docs/Cloud_Deployment_Guide.md`](docs/Cloud_Deployment_Guide.md) | AWS ECS/Fargate, Azure Container Apps, Kubernetes, least-privilege IAM, OIDC CI/CD, and rollback runbooks. |
| [`docs/MONITORING_AND_OBSERVABILITY.md`](docs/MONITORING_AND_OBSERVABILITY.md) | Infrastructure/RAM/WAL thresholds, API/MCP SLAs, AI governance, and security alert routing. |
| [`docs/Ephemeral_Ledger_Architecture.md`](docs/Ephemeral_Ledger_Architecture.md) | SQLite WAL POSIX volume requirements and JSONL object-storage sync architecture. |

---

## 2. Quick-Start & Verification

```bash
# 1. Copy environment template (never commit .env)
cp .env.example .env

# 2. Run static analysis, strict typing, and test suite inside smartrx-dev
docker run --rm -v "${PWD}:/app" smartrx-dev sh -c \
  "ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && pytest -q --tb=short --cov=src/smartrx_safety_agents --cov-report=term:skip-covered --cov-fail-under=90"

# 3. Run production container locally
docker compose -f docker-compose.prod.yml up -d
curl http://127.0.0.1:8080/health
```

### CLI Entrypoints (`smartrx-safety-agents`)
- `smartrx-safety-agents status` — Check configuration and ledger health.
- `smartrx-safety-agents reconcile --dry-run` — Execute dry-run medication reconciliation.
- `smartrx-safety-agents benchmark` — Run deterministic `TC-001`–`TC-008` clinical safety suite.
- `smartrx-safety-agents verify-audit` — Verify SQLite WAL SHA-256 hash-chain integrity.
- `smartrx-safety-agents serve` — Start FastAPI REST/SSE gateway on port `8080`.
- `smartrx-safety-agents mcp` — Start `smartrx://` Model Context Protocol server (`stdio` / SSE).
