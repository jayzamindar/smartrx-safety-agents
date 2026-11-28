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
