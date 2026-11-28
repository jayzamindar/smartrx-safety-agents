# Technical Requirements Document (TRD): SmartRx Safety Agents (`smartrx-safety-agents`)

**Project Title:** SmartRx Guard — Automated Medication Reconciliation & Safety Verification System  
**Package Name:** `smartrx_safety_agents` (`src/smartrx_safety_agents/`)  
**Target Runtime:** Python 3.13+ (PEP 517/621, Pydantic v2 `extra="forbid"`, `frozen=True`, FastAPI, SQLite WAL)  
**Governance Authority:** `GEMINI.md` & `Enterprise_Blueprint.md`  
**Requirements Traceability:** `docs/URD.md` (v1.0 Baseline) | `docs/PRD.md`

---

## 1. System Architecture & Execution Pipeline

### 1.1 Hybrid Hierarchical-Parallel Multi-Agent Topology
To guarantee `< 10s` end-to-end latency while preventing LLM hallucinations and infinite loops, execution follows a deterministic-first 5-stage pipeline over an immutable Blackboard State:

1. **Stage 1 (Parallel Intake & History):** `IntakeAgent` (`IntakeOutput`) and `ClinicalHistoryAgent` (`ClinicalOutput`) normalize incoming prescriptions/OCR text to RxNorm `RxCUI` and retrieve 12-month longitudinal EHR medications, allergies, and renal/hepatic labs.
2. **Stage 2 (Deterministic Safety Gate):** `SafetyAgent` (`SafetyOutput`) runs Python rule engines (`ddi_engine.py`, `allergy_checker.py`, `dosing_validator.py`) BEFORE any LLM synthesis.
3. **Stage 3 (Formulary & Coverage):** `InsuranceAgent` (`InsuranceOutput`) resolves payer tier, copay, and Prior Authorization (`formulary_checker.py`) with CMS standard formulary tier fallback.
4. **Stage 4 (Adversarial Critic & FHIR Synthesis):** `AuditorAgent` (`AuditorOutput`) verifies citations/PHI redaction; `LiaisonAgent` (`LiaisonOutput`) compiles the 3-Tier HITL report and deterministic HL7 FHIR R4 payloads (`MedicationRequest`, `DetectedIssue`, `Task`).
5. **Stage 5 (Cryptographic Seal & Audit Persistence):** Canonical JSON HMAC-SHA256 signing and append-only SQLite WAL hash-chained ledger persistence (`smartrx_ledger.db`).

### 1.2 Target Module Tree (`src/smartrx_safety_agents/`)

```text
src/smartrx_safety_agents/
├── __init__.py
├── config.py                     # pydantic-settings configuration & fail-closed secret checks
├── cli.py                        # Click CLI entrypoint (smartrx-safety-agents)
├── models/
│   ├── __init__.py
│   ├── clinical.py               # StrictClinicalModel, ActionType, RiskGrade, 6 agent outputs
│   ├── remediation.py            # Signed plans, execution_payload, anti-replay nonces
│   └── audit.py                  # Ledger event & hash-chain schemas
├── heuristics/
│   ├── __init__.py
│   ├── ddi_engine.py             # Deterministic DDI severity & therapeutic duplication checker
│   ├── allergy_checker.py        # Deterministic allergy & pharmacological cross-reactivity
│   ├── dosing_validator.py       # Renal eGFR/CrCl, hepatic ceilings, NTI & Beer's Criteria
│   ├── formulary_checker.py      # Payer formulary, PA & CMS default tier fallback
│   ├── phi_redactor.py           # Deterministic HIPAA PHI tokenization & log redactor
│   └── engine.py                 # Unified offline heuristic orchestrator
├── guardrails/
│   ├── __init__.py
│   ├── risk_scorer.py            # 1-5 Safety Risk & 3-Tier HITL grader
│   ├── quarantine.py             # Fail-closed Enum & missing-mitigation quarantine
│   ├── fhir_generator.py         # Deterministic HL7 FHIR R4 JSON generators
│   └── rollback.py               # Deterministic clinical rollback synthesis
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py           # Chief Medical Orchestrator & 3-turn circuit breaker
│   └── reasoner.py               # Gemini 3.8 Flash High -> OpenRouter -> Tertiary cascade
├── persistence/
│   ├── __init__.py
│   └── ledger_store.py           # SQLite WAL hash-chained ledger + write-only FileLock
├── api/
│   ├── __init__.py
│   ├── server_sse.py             # FastAPI + SSE (/v1/sse, /v1/messages, 10MB middleware)
│   └── server_stdio.py           # Line-delimited JSON-RPC 2.0 stdio transport
└── ui/
    ├── __init__.py
    └── workbench.py              # 3-Column Pharmacist HITL Workbench (Streamlit)
```

---

## 2. Canonical Pydantic v2 Data Contracts (`models/clinical.py`)

All clinical schemas inherit from `StrictClinicalModel` configured with:
```python
model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
```
Inbound medication identifiers, clinical codes, and tags MUST pass through Unicode NFKC normalization (`unicodedata.normalize("NFKC", val).strip().casefold()`) via `@field_validator` prior to allowlist or catalog comparisons.

### 2.1 Core Enums & Base Models
- **`RiskGrade(StrEnum)`:** `RED`, `YELLOW`, `GREEN`
- **`AgentStatus(StrEnum)`:** `SUCCESS`, `PARTIAL`, `HALT_FOR_HUMAN`, `FAILED`
- **`ActionType` (`Literal`):**
  - `"APPROVE_RECONCILED_LIST"`
  - `"FLAG_DRUG_INTERACTION"`
  - `"HOLD_PRESCRIPTION"`
  - `"PROPOSE_THERAPEUTIC_ALTERNATIVE"`
  - `"REQUEST_RENAL_HEPATIC_LABS"`
  - `"ESCALATE_TO_CLINICAL_PHARMACIST"`
- **`StrictClinicalModel(BaseModel)`:** Shared base enforcing `ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)`.

### 2.2 Six-Agent Output Schemas
1. **`NormalizedMedication` & `IntakeOutput`:**
   - `NormalizedMedication`: `rxcui`, `scd_name`, `raw_name`, `snomed_code` (optional), `ndc` (optional), `dose_mg` (optional `float >= 0`), `frequency`, `route`, `is_nti` (`bool`), `ocr_confidence` (`float` in `[0.0, 1.0]`).
   - `IntakeOutput`: `patient_token`, `medications` (`tuple[NormalizedMedication, ...]`), `low_confidence_nti_detected` (`bool`), `discrepancies` (`tuple[str, ...]`), `confidence` (`float` in `[0.0, 1.0]`).
2. **`PatientLabObservation` & `ClinicalOutput`:**
   - `PatientLabObservation`: `loinc_code`, `name`, `value` (`float | None`), `unit`, `observed_at` (`datetime`).
   - `ClinicalOutput`: `patient_token`, `active_medications` (`tuple[NormalizedMedication, ...]`), `allergies` (`tuple[str, ...]`), `labs` (`tuple[PatientLabObservation, ...]`), `egfr_ml_min` (`float | None`), `hepatic_impaired` (`bool`), `partial_ehr_record` (`bool`).
3. **`ClinicalAlert` & `SafetyOutput`:**
   - `ClinicalAlert`: `alert_id`, `rule_category` (`Literal["DDI", "ALLERGY", "DUPLICATION", "DOSING", "BEERS_CRITERIA", "OCR_NTI"]`), `severity` (`Literal["contraindicated", "major", "moderate", "minor"]`), `risk_score` (`int` in `[1, 5]`), `risk_grade` (`RiskGrade`), `recommended_action` (`ActionType`), `affected_rxcuis` (`tuple[str, ...]`), `rationale`, `citation` (non-empty RxNorm/NLM/PubMed reference), `requires_npi_attestation` (`bool`).
   - `SafetyOutput`: `alerts` (`tuple[ClinicalAlert, ...]`), `overall_risk_grade` (`RiskGrade`), `recommended_action` (`ActionType`), `missing_nti_labs` (`bool`), `quarantined` (`bool`), `quarantine_reason` (`str | None`).
4. **`FormularyAlternative` & `InsuranceOutput`:**
   - `FormularyAlternative`: `rxcui`, `drug_name`, `formulary_tier` (`int` in `[1, 5]`), `estimated_copay_usd` (`float >= 0.0`), `requires_pa` (`bool`).
   - `InsuranceOutput`: `covered` (`bool`), `formulary_tier` (`int` in `[1, 5]`), `estimated_copay_usd` (`float >= 0.0`), `requires_pa` (`bool`), `pa_deadline` (`datetime | None`), `used_cms_fallback` (`bool`), `alternatives` (`tuple[FormularyAlternative, ...]`).
5. **`AuditorOutput`:**
   - `hallucination_detected` (`bool`), `phi_leak_detected` (`bool`), `unverified_claims` (`tuple[str, ...]`), `verified_citations` (`tuple[str, ...]`), `audit_passed` (`bool`).
6. **`LiaisonOutput`:**
   - `plan_id`, `patient_token`, `status` (`AgentStatus`), `overall_risk_grade` (`RiskGrade`), `recommended_action` (`ActionType`), `fhir_resources` (`tuple[dict[str, Any], ...]`), `rollback_steps` (`tuple[str, ...]`), `pharmacist_summary`, `requires_hitl_attestation` (`bool`), `confidence` (`float` in `[0.0, 1.0]`).

---

## 3. Cryptographic Signing, SQLite WAL Ledger & Static Catalog

### 3.1 HMAC-SHA256 Canonical JSON Envelope
Every reconciliation plan is sealed before persistence or transport:
- **Anti-Replay:** `issued_at` (ISO-8601 UTC), `expires_at` (`expires_at - issued_at <= 300s`), and monotonic `plan_id` / `idempotency_key`. Expired (`current_time >= expires_at`) or replayed keys are rejected fail-closed.
- **Canonical Digest & Signature:**
  `canonical = json.dumps(plan.model_dump(mode="json", exclude={"plan_digest", "plan_signature"}), sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
  `plan_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()`
  `plan_signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()`
- Verification MUST use `hmac.compare_digest()`.

### 3.2 SQLite WAL Hash-Chained Audit Schema (`data/smartrx_ledger.db`)
- Connections enable `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=5000;`, and track `PRAGMA user_version = 1`.
- Writes acquire a per-operation `filelock.FileLock(..., timeout=FILELOCK_TIMEOUT_SEC)` offloaded via `asyncio.to_thread()`; reads bypass `filelock` using SQLite MVCC.
- `audit_events` table:
  `id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT UNIQUE NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, patient_token TEXT NOT NULL, action_type TEXT NOT NULL, risk_grade TEXT NOT NULL, quarantined INTEGER NOT NULL, payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL, created_at TEXT NOT NULL`

### 3.3 Static Drug & Interaction Catalog (`config/drug_interactions.json`)
Missing or corrupted catalog files raise `CatalogNotFoundError` and route to the Tertiary engine. The catalog covers benchmark verification cases `TC-001` through `TC-008`:
- **TC-001:** Major/Contraindicated DDI (e.g., Warfarin + Amiodarone / NSAID) $\to$ `HOLD_PRESCRIPTION` + `ESCALATE_TO_CLINICAL_PHARMACIST` (`RED`).
- **TC-002:** Allergy cross-reactivity (Penicillin allergy + Amoxicillin) $\to$ `HOLD_PRESCRIPTION` + `ESCALATE_TO_CLINICAL_PHARMACIST` (`RED`).
- **TC-003:** Missing renal/hepatic labs for NTI drug (Digoxin/Lithium without eGFR) $\to$ `REQUEST_RENAL_HEPATIC_LABS` (`RED`/`YELLOW`).
- **TC-004:** Low OCR confidence (`< 0.70`) on NTI drug (Warfarin/Phenytoin) $\to$ Tier 1 `RED` mandatory lock (`HOLD_PRESCRIPTION`).
- **TC-005:** Therapeutic class duplication (Lisinopril + Enalapril) $\to$ `FLAG_DRUG_INTERACTION` (`YELLOW`).
- **TC-006:** Geriatric ($\ge 65$) AGS Beer's Criteria (Diphenhydramine/Diazepam) $\to$ `PROPOSE_THERAPEUTIC_ALTERNATIVE` (`YELLOW`).
- **TC-007:** Payer plan unavailable / Prior Auth $\to$ `InsuranceOutput(used_cms_fallback=True)` (`YELLOW`).
- **TC-008:** Clean reconciliation, zero conflicts, confidence $\ge 0.90$ $\to$ `APPROVE_RECONCILED_LIST` (`GREEN`).
