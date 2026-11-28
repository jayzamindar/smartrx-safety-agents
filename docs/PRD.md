# Product Requirements Document (PRD): SmartRx Safety Agents (`smartrx-safety-agents`)

**Project Title:** SmartRx Guard — Automated Medication Reconciliation & Safety Verification System  
**Package:** `smartrx_safety_agents` (`src/smartrx_safety_agents/`)  
**Status:** Baseline v1.0  
**Traceability:** [docs/URD.md](URD.md) | [docs/TRD.md](TRD.md) | [GEMINI.md](../GEMINI.md)

---

## 1. Product Vision & Problem Statement

Care transitions (hospital admission, transfer, and discharge) are the single highest-risk point for preventable adverse drug events (ADEs). **SmartRx Safety Agents** eliminates manual Best Possible Medication History (**BPMH**) reconciliation bottlenecks by pairing deterministic clinical pharmacy rule engines with a 6-agent hierarchical-parallel AI squad and a 3-Tier Human-in-the-Loop (**HITL**) Pharmacist Workbench.

Unlike unconstrained LLM chatbots, SmartRx enforces **zero LLM command synthesis**: LLMs may assist with terminology normalization and narrative summaries, while all contraindication holds, dosing bounds, HL7 FHIR R4 payloads, and audit seals are generated deterministically in Python.

---

## 2. Target User Personas

| Persona | Primary Goals | Key Pain Points Addressed |
|---|---|---|
| **Inpatient Clinical Pharmacist** | Verify BPMH accuracy, resolve severe DDIs/allergies, and sign off reconciled orders rapidly. | Alert fatigue from low-value popups; manual cross-checking of labs, allergies, and formularies across disconnected EHR tabs. |
| **Prescribing Physician / Hospitalist** | Receive clear, evidence-backed therapeutic alternatives and lab requests without workflow stalls. | Delayed pharmacy callbacks and vague rejection messages lacking PubMed/RxNorm citations or formulary tier alternatives. |
| **Pharmacy Safety & QA Officer** | Audit 100% of overrides, detect AI hallucinations, and verify HIPAA PHI redaction compliance. | Non-reproducible LLM decisions, missing override justifications, and unindexed free-text logs containing raw PHI. |

---

## 3. Functional Capabilities (FS-1 to FS-8)

- **FS-1: RxNorm / SNOMED / NDC Normalization & BPMH 3-Way Diff:** Normalize incoming prescriptions, EHR `MedicationStatement` history, and patient-reported/OTC meds to `RxCUI` and Semantic Clinical Drug (`SCD`), classifying discrepancies as *Intentional* or *Unintentional*.
- **FS-2: OCR & Narrow Therapeutic Index (NTI) Safety Gate:** Evaluate prescription OCR confidence; any low-confidence parse (`< 0.70`) or OCR ambiguity involving NTI drugs (Warfarin, Digoxin, Lithium, Phenytoin) deterministically triggers a **Tier 1 RED** workflow lock (`HOLD_PRESCRIPTION`).
- **FS-3: Deterministic Contraindication & Cross-Reactivity Engine:** Execute Python DDI severity matrix checks, therapeutic class duplication detection, and `AllergyIntolerance` pharmacological cross-reactivity validation before any LLM call (`HOLD_PRESCRIPTION` + `ESCALATE_TO_CLINICAL_PHARMACIST` on severe/major findings).
- **FS-4: Organ-Function Dosing & AGS Beer's Criteria:** Validate doses against renal (`eGFR`/`CrCl`) and hepatic lab bounds—triggering `REQUEST_RENAL_HEPATIC_LABS` when required labs are missing for NTI/organ-cleared drugs—and flag geriatric ($\ge 65$) potentially inappropriate medications per AGS Beer's Criteria (`PROPOSE_THERAPEUTIC_ALTERNATIVE`).
- **FS-5: Insurance Formulary & Prior Auth Resolution:** Evaluate payer formulary tier, copay estimate, and Prior Authorization (`requires_pa`, `pa_deadline`), with deterministic fallback to **CMS standard formulary tier rules** when plan data is unavailable.
- **FS-6: Three-Tier HITL Pharmacist Workbench:**
  - **Tier 1 RED (`< 0.70`):** Mandatory hard lock; requires structured **Clinical Justification Code** + digital NPI attestation to override.
  - **Tier 2 YELLOW (`0.70–0.89`):** Affirmative pharmacist **Review & Accept** or **Modify** (with reason text).
  - **Tier 3 GREEN (`≥ 0.90`):** Non-blocking passive observation logged to the immutable audit trail.
  - Supports 3-column workbench layout (Input Evidence | Reconciliation Diff & "What-If" Sandbox | Safety Rail & Agent Breadcrumbs) and 3-Turn Circuit Breaker (`HALT_FOR_HUMAN`).
- **FS-7: Deterministic HL7 FHIR R4 Payload Synthesis & Evidence Citations:** Emit validated `MedicationRequest`, `DetectedIssue`, and `Task` JSON resources; attach verifiable RxNorm interaction ID, NLM/Lexicomp section, or PubMed ID citations to every warning.
- **FS-8: Dual-Transport MCP & Tamper-Evident Audit Ledger:** Expose `smartrx://catalog/interactions`, `smartrx://reconcile/verify`, `smartrx://audit/escalations`, and `clinical_reconciliation_review` over `stdio` and authenticated SSE with HIPAA PHI tokenization and HMAC-SHA256 signed plans.

---

## 4. Edge Cases & Fail-Closed Behavior

- **Missing/Corrupted Static Catalog:** Raises `CatalogNotFoundError` and fails closed to deterministic escalation rather than silently returning zero interactions.
- **Partial EHR History / Missing Labs:** Gracefully degrades with explicit `REQUEST_RENAL_HEPATIC_LABS` for NTI drugs rather than assuming normal organ function.
- **LLM Outage / RAM Ceiling / Cost Cap:** Cascades Primary Gemini 3.8 Flash High $\to$ Secondary OpenRouter $\to$ Tertiary Deterministic Heuristics with 100% offline availability.
- **Oversized or Replayed Requests:** Rejects $> 10\text{ MB}$ payloads with HTTP 413 and rejects expired/replayed plans (`expires_at <= current_time`) fail-closed.

---

## 5. KPI Acceptance Metrics

| KPI Metric | Target Threshold | Verification Method |
|---|---|---|
| **End-to-End Reconciliation Latency** | $< 10\text{s}$ (p99 AI $< 3500\text{ms}$, Rules $< 500\text{ms}$) | OpenTelemetry span timing & benchmark suite |
| **Severe DDI & Allergy Recall** | $100\%$ deterministic detection (0 false negatives) | `TC-001`–`TC-008` & `pytest` clinical suite |
| **Unredacted PHI Leakage** | $0\%$ across logs, LLM prompts, and SQLite ledger | `phi_redactor.py` & `AuditorOutput` assertions |
| **Automated Test Coverage** | $\ge 90\%$ line/branch coverage (`pytest-cov`) | Local & CI verification gate |
