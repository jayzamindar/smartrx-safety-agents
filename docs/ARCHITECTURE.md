# System Architecture (`docs/ARCHITECTURE.md`)

**Project:** `smartrx-safety-agents`  
**Pattern:** Clean Modular Hexagonal Architecture + Deterministic-First Clinical Guardrails  
**Runtime:** Python 3.13+ | FastAPI + Starlette SSE + MCP (`smartrx://`) | SQLite WAL

---

## 1. High-Level Container & Pipeline Architecture

```mermaid
flowchart LR
    Client["Clinician / EHR / MCP Client"] -->|"REST / SSE / stdio (<=10MB, Auth)"| Gateway["api/server.py & api/mcp_server.py"]
    Gateway -->|"Orchestrates"| Orch["agents/orchestrator.py (SmartRxOrchestrator)"]
    Orch -->|"Pre-LLM PHI Scrub"| PHI["heuristics/phi_redactor.py"]
    Orch -->|"Stage 1 (Parallel)"| Intake["IntakeAgent & ClinicalHistoryAgent"]
    Orch -->|"Stage 2 (Deterministic First)"| Safety["SafetyAuditorAgent -> DeterministicClinicalEngine"]
    Safety -->|"DDI / Allergy / Dosing / Formulary"| Catalog["config/drug_interactions.json"]
    Orch -->|"Stage 3-4 (<=3 Turns)"| Critic["PharmacistLiaisonAgent <-> AdversarialCritic"]
    Critic -->|"Stage 5 (Zero-Hallucination)"| Guard["guardrails/engine.py (GuardrailEngine + FHIR R4 + HMAC)"]
    Guard -->|"FileLock Writes / MVCC Reads"| Ledger["persistence/ledger.py (SQLite WAL + JSONL)"]
```

---

## 2. Module Responsibilities

| Layer | Package / File | Responsibility |
|---|---|---|
| **Configuration** | `src/smartrx_safety_agents/config.py` | Pydantic `BaseSettings`, model IDs, RAM/token/cost ceilings, fail-closed production secret checks. |
| **Data Contracts** | `src/smartrx_safety_agents/models/` | Immutable Pydantic v2 schemas (`extra="forbid"`, `frozen=True`), `ActionType` Literal Enum, NFKC + zero-width identifier normalization. |
| **Deterministic Heuristics** | `src/smartrx_safety_agents/heuristics/` | Offline `DDIEngine` (`CatalogNotFoundError`), `AllergyChecker`, `DosingValidator` (eGFR/hepatic/OCR NTI/Beer's Criteria), `FormularyChecker`, `PHIRedactor`. |
| **Guardrails & Signing** | `src/smartrx_safety_agents/guardrails/` | `GuardrailEngine` (quarantine, idempotency, HMAC-SHA256 canonical signing, `<=300s` TTL/replay), deterministic HL7 FHIR R4 (`MedicationRequest`, `DetectedIssue`, `Task`), rollback synthesis. |
| **AI Agents & Resilience** | `src/smartrx_safety_agents/agents/` | `MultiTierLLMClient` (Primary Gemini $\to$ Secondary OpenRouter `<think>` strip $\to$ Tertiary Heuristics), `clean_gemini_schema()`, 6 specialists, 3-turn `HALT_FOR_HUMAN` circuit breaker. |
| **Persistence** | `src/smartrx_safety_agents/persistence/ledger.py` | `AuditLedger` (SQLite WAL, `PRAGMA user_version` migrations, per-op `FileLock` writes, MVCC reads, SHA-256 hash chain) & `JsonlAuditExporter` (50MB rotation, 30d/500MB pruning). |
| **Transport & CLI** | `src/smartrx_safety_agents/api/`, `cli.py`, `ui/` | FastAPI REST/SSE (10MB guard, timing-safe auth, `SensitiveQueryParamFilter`), MCP `smartrx://` server, Click CLI, Streamlit HITL Workbench. |
| **Observability** | `src/smartrx_safety_agents/observability.py` | OpenTelemetry `TelemetryManager` (`.shutdown()`), `trace_span`, thread-safe `InMemoryMetricsLedger`. |

---

## 3. Request Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> INITIALIZED: "MCP / REST Request Validated (<=10MB, Auth OK)"
    INITIALIZED --> PROCESSING: "T001 Create plan_id & PHI Redaction"
    PROCESSING --> QUARANTINED: "Invalid ActionType OR Risk >= 3 Missing Rollback"
    PROCESSING --> FAILED: "CatalogNotFoundError OR Unrecoverable Schema Fault"
    PROCESSING --> UNDER_REVIEW: "Tier 1 RED (< 0.70 / Major DDI) OR Tier 2 YELLOW (0.70-0.89)"
    PROCESSING --> APPROVED: "Tier 3 GREEN (>= 0.90 & Zero Conflicts)"
    UNDER_REVIEW --> APPROVED: "Pharmacist NPI Attestation (RED) OR Accept/Modify (YELLOW)"
    UNDER_REVIEW --> QUARANTINED: "Pharmacist Rejects / TTL Expired (>= 300s)"
    APPROVED --> [*]: "HMAC-SHA256 Signed FHIR R4 + SQLite WAL Commit"
    QUARANTINED --> [*]: "ESCALATE_TO_CLINICAL_PHARMACIST + Audit Log"
    FAILED --> [*]: "Fail-Closed HTTP 400/503 + Telemetry Alert"
```

---

## 4. `T001`: Process Prescription (Main Orchestration) Deep-Dive

```mermaid
flowchart TD
    Start(["START: T001 Process Prescription"]) --> InGuard["1. Input Guardrails (10MB Limit, Auth, Pydantic extra=forbid)"]
    InGuard --> ReqID["2. Create Request & Generate Monotonic plan_id / idempotency_key"]
    ReqID --> PHI["3. T002 PHI Redaction & NFKC / Zero-Width Normalization"]
    PHI --> Squad["4. 6-Agent Squad Execution (Parallel T002+T003 -> T004 -> T005 -> T006 <=3 Turns)"]
    Squad --> Guard["5. T007 Deterministic GuardrailEngine & HL7 FHIR R4 Overwrite"]
    Guard --> HITL{"6. T008 3-Tier HITL Gate"}
    HITL -->|"RED (<0.70) / YELLOW (0.70-0.89)"| Review["Pharmacist Workbench Adjudication / NPI Attestation"]
    HITL -->|"GREEN (>=0.90)"| Sign["7. Canonical JSON HMAC-SHA256 Signer (expires_at <= 300s)"]
    Review --> Sign
    Sign --> Commit["8. SQLite WAL Commit (FileLock Write via asyncio.to_thread) + JSONL Export"]
    Commit --> EndNode(["END: Signed FHIR R4 Bundle & Audit Trail"])
```

### Task Orchestration Registry (`T001`–`T008`)

| Task ID | Task Name | Mapped Module / Agent | Execution & Safety Responsibility |
|---|---|---|---|
| `T001` | Process Prescription | `agents/orchestrator.py` (`SmartRxOrchestrator`) | Main 5-stage orchestration, `BlackboardState`, 3-turn circuit breaker, and WAL commit. |
| `T002` | Intake Prescription | `agents/specialists.py` (`IntakeAgent`), `heuristics/phi_redactor.py` | Pre-LLM PHI scrubbing, Unicode NFKC normalization, and RxNorm RxCUI / OCR extraction. |
| `T003` | Retrieve Patient History | `agents/specialists.py` (`ClinicalHistoryAgent`) | Parallel longitudinal EHR medication, allergy, and eGFR/CrCl/hepatic lab consolidation. |
| `T004` | Safety Audit | `agents/specialists.py` (`SafetyAuditorAgent`), `heuristics/engine.py` | Deterministic-first DDI, allergy cross-reactivity, Beer's Criteria, and NTI dosing bounds. |
| `T005` | Insurance Check | `agents/specialists.py` (`InsuranceAgent`), `heuristics/formulary_checker.py` | Formulary coverage check, Prior Authorization detection, and CMS therapeutic fallback. |
| `T006` | Generate Summary | `agents/specialists.py` (`PharmacistLiaisonAgent`, `AdversarialAuditorAgent`) | Structured clinical summary synthesis and `<= 3`-turn adversarial safety verification. |
| `T007` | Validate Output | `guardrails/engine.py` (`GuardrailEngine`), `guardrails/fhir_generator.py` | `ActionType` allowlist, Risk 1–5 scoring, FHIR R4 overwrite, quarantine & HMAC-SHA256 signing. |
| `T008` | Human Review | `ui/dashboard.py`, `api/server.py` (`/api/v1/adjudicate`) | 3-Tier HITL Pharmacist Workbench (RED NPI attestation, YELLOW review/modify, GREEN auto-log). |
