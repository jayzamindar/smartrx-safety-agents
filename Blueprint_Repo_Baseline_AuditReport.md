# Forensic Repository Baseline Audit Report (`Blueprint_Repo_Baseline_AuditReport.md`)

**Project:** SmartRx Safety Agents (`smartrx-safety-agents`)  
**Package:** `smartrx_safety_agents` (`src/smartrx_safety_agents/`)  
**Audit Phase:** Phase 0.1 — Forensic Baseline Audit  
**Audit Date:** 2026-11-26  
**Baseline Scope:** `GEMINI.md`, `Enterprise_Blueprint.md`, `docs/URD.md`, `docs/TRD.md`, `PROJECT_MAP.md`, `AUDIT_REMEDIATION_LOG.md`, repository layout (`src/`, `tests/`, `docs/`, `prompts/`)

---

## 1. Executive Summary

The `smartrx-safety-agents` repository is at the **Phase 0 governance & specification baseline**. Core clinical domain requirements are established in `docs/URD.md` (v1.0 Baseline), and the primary clinical safety invariants (`ActionType` enum, HL7 FHIR R4 deterministic generators, 3-Tier HITL confidence thresholds, OCR NTI triggers, AGS Beer's Criteria, PubMed/RxNorm citations, and `smartrx://` MCP endpoints) have been aligned in `GEMINI.md` (Sections 3.1, 3.2, 3.8, 4) and `Enterprise_Blueprint.md` (Phases 2.1, 4, 5.5–5.7, and Tasks 9.3, 9.4, 9.7, 9.8, 9.17).

However, **no Python implementation, packaging (`pyproject.toml`), or test suite exists yet** (`src/smartrx_safety_agents/__init__.py` and `tests/__init__.py` are empty), `docs/TRD.md` is a 15-line stub, and several residual FinOps/template strings remain in non-domain sections of `GEMINI.md`, `Enterprise_Blueprint.md`, and `PROJECT_MAP.md`.

**Overall Baseline Grade:** **C- (Pre-Implementation Governance Baseline)**

---

## 2. Ten-Dimension Enterprise Governance Evaluation

| # | Enterprise Governance Dimension | Grade | Current Baseline Status & Verified Findings |
|---|---|---|---|
| **1** | **AI Framework Architecture & Data Contracts** | **B-** | `GEMINI.md` (§2) and `docs/URD.md` (§2) mandate Pydantic v2 (`extra="forbid"`, `frozen=True`), 6-agent hierarchical-parallel squad (`IntakeOutput`, `ClinicalOutput`, `SafetyOutput`, `InsuranceOutput`, `LiaisonOutput`, `AuditorOutput`), and 10MB payload ceiling. No `src/` code implemented yet. |
| **2** | **Deterministic Schema Compliance & Zero Hallucination** | **B** | `GEMINI.md` (§3.1–3.2) and `Enterprise_Blueprint.md` (Phase 2.1, 4.5–4.6, 9.8, 9.17) enforce the 6-value `ActionType` enum and deterministic HL7 FHIR R4 JSON generation (`MedicationRequest`, `DetectedIssue`, `Task`). Residual `config/instance_mappings.json` references remain in `GEMINI.md` line 111 and `Enterprise_Blueprint.md` lines 20 & 186. |
| **3** | **Calibrated Safety Enforcement & Quarantine** | **B** | 1–5 Safety Risk scale, `quarantined=True` fail-closed rules, and 3-Tier HITL confidence thresholds (`< 0.70` RED, `0.70–0.89` YELLOW, `≥ 0.90` GREEN) are specified in `docs/URD.md`, `GEMINI.md` (§3.8), and `Enterprise_Blueprint.md` (Phase 4). Implementation pending Phase 2 & 4. |
| **4** | **Resilient Multi-Path Uptime & Catalog Fallback** | **C+** | 3-tier cascade (Gemini 3.8 Flash High → OpenRouter → Deterministic Heuristics), RAM watchdog (1750MB/2048MB), and `CatalogNotFoundError` are specified. Residual FinOps catalog (`config/instance_mappings.json`, `$0.0 savings`) remains in `GEMINI.md` line 111 and `Enterprise_Blueprint.md` lines 20 & 186. |
| **5** | **Cryptographic Payload Integrity & Anti-Replay** | **B** | Full-payload HMAC-SHA256 signing, canonical JSON serialization, `hmac.compare_digest()`, `issued_at`/`expires_at` ($\le 300\text{s}$ TTL), and `plan_id` idempotency are fully specified in `GEMINI.md` (§3.3–3.4) and `Enterprise_Blueprint.md` (Phase 4.8, 9.18). |
| **6** | **Cloud-Native Portability & Memory Ceiling** | **C** | 2048MB RAM ceiling, non-root `sentinel:sentinel` (UID 10001), and `audit_logs/` rotation quotas are specified in `GEMINI.md` (§3.10). `Dockerfile`, `pyproject.toml`, and `.env.example` are not yet created (Phase 1 & 7). |
| **7** | **Observability & SQLite WAL Lock Isolation** | **C** | OpenTelemetry spans, Four Golden Signals, SQLite WAL mode, write-only `filelock.FileLock`, MVCC read bypass, and `PRAGMA user_version` migrations are specified in `GEMINI.md` (§3.6, §5). Implementation pending Phase 6. |
| **8** | **Documentation Alignment & Link Integrity** | **C-** | `docs/URD.md` (81 lines) is complete. `docs/TRD.md` is a 15-line stub (missing JSON-RPC schemas, FHIR contracts, and NFRs). `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/Cloud_Deployment_Guide.md`, and `docs/MONITORING_AND_OBSERVABILITY.md` do not exist yet (Phase 0.2–0.5). |
| **9** | **Test-Driven Verification & Anti-Tampering** | **D** | `pytest-timeout` and $\ge 90\%$ coverage gate are mandated in `GEMINI.md` (§1–2), but `tests/` contains only `__init__.py` and no `pyproject.toml` or test suite exists yet. |
| **10** | **UTF-8 I/O, HIPAA PHI & Cost Circuit Breakers** | **B-** | Explicit `encoding="utf-8"`, `MAX_SESSION_TOKEN_BUDGET=500_000`, `DAILY_API_COST_LIMIT_USD=10.00`, and deterministic HIPAA PHI redaction/tokenization (`phi_redactor.py`) are specified in `GEMINI.md` (§1, §3.8, §3.12) and `docs/URD.md` (§1, §4). |

---

## 3. Cross-Document Alignment & Residual FinOps/Template Findings

1. **`docs/URD.md` (v1.0 Baseline):** 100% aligned with SmartRx clinical pharmacy domain; 0 FinOps/AWS strings.
2. **`docs/TRD.md`:** Currently only 15 lines (header + Section 1.1 intro). Requires full authoring in Phase 0.3.
3. **`GEMINI.md`:** Domain sections (§3.1, §3.2, §3.8, §4) are aligned with `docs/URD.md`. Residual template/FinOps strings remain at:
   - Line 37: Template Cloning Note referencing Cloud Infrastructure & FinOps.
   - Line 111 (§3.5): `config/instance_mappings.json` and `$0.0 savings` (should reference `config/drug_interactions.json` in a future cleanup).
   - Line 212 (§6): `FinOps pricing traps` in the cross-model red-team prompt.
4. **`Enterprise_Blueprint.md`:** Phases 2.1, 4, 5.5–5.7, and Tasks 9.3, 9.4, 9.7, 9.8, 9.17 are aligned with `docs/URD.md`. Residual FinOps/template strings remain at:
   - Line 20 (DoD #4) & Line 186 (Task 9.9): `config/instance_mappings.json` / AWS pricing lookup.
   - Line 72: `### Phase 2: [DOMAIN REFERENCE: FINOPS]` heading.
   - Line 147 (Task 6.1): `In-Memory FinOps Ledger`.
   - Line 208 (Task 10.2) & Line 251 (Task 12.2): `FinOps guardrails` / `FinOps pricing or commitment traps`.

---

## 4. Prioritized Technical Debt & Remediation Backlog

1. **P0 (Phase 0.2–0.7):** Author `docs/PRD.md`, complete `docs/TRD.md`, author `docs/ARCHITECTURE.md`, and overhaul `README.md` navigation links.
2. **P0 (Phase 1.1–1.6):** Create `pyproject.toml` (Python 3.13+, `pytest-timeout`, `ruff`, `mypy`), `.env.example`, `.gitignore` verification, and deterministic lockfile.
3. **P1 (Cleanup):** Replace remaining `config/instance_mappings.json` and `FinOps` references in `GEMINI.md` (lines 111, 212) and `Enterprise_Blueprint.md` (lines 20, 72, 147, 186, 208, 251) with SmartRx clinical equivalents.
4. **P1 (Phase 2–6):** Implement `src/smartrx_safety_agents/` modules (`models/clinical.py`, `guardrails/fhir_generator.py`, `heuristics/`, `reasoner/`, `ledger/`, `mcp/`) and achieve $\ge 90\%$ `pytest` coverage.
