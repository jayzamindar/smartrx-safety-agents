# User Requirements Document (URD): SmartRx Safety Agents (`smartrx-safety-agents`)

**Project Title:** SmartRx Guard — Automated Medication Reconciliation & Safety Verification System  
**Repository / Package:** `smartrx-safety-agents` (`smartrx_safety_agents`)  
**Document Status:** Baseline v1.0 (Consolidated & Reconciled Specification)  
**Compliance & Regulatory Alignment:** HIPAA (Admin/Physical/Technical Safeguards), GxP Immutable Auditability, FDA Class II SaMD Guidance, ISO 14971 (Risk Management), IEC 62366-1 (Usability Engineering), AAMI TIR57 (Cybersecurity)

---

## 1. Executive Summary & Clinical Context
**SmartRx Safety Agents** is a production-grade, deterministic-first multi-agent clinical decision support system designed to eliminate preventable medication errors during care transitions (hospital admission, transfer, and discharge).

The system automates Best Possible Medication History (**BPMH**) reconciliation by cross-referencing incoming prescriptions against a patient's longitudinal Electronic Health Record (**EHR**) history, active medication list, documented allergies, and renal/hepatic lab values—enforcing deterministic clinical guardrails and mandatory Pharmacist Human-in-the-Loop (**HITL**) attestation before any order is committed to the EHR.

### Core Objectives
1. **Zero-Defect Patient Safety:** Deterministically detect severe Drug-Drug Interactions (DDIs), allergy cross-reactivity, therapeutic duplication, Narrow Therapeutic Index (NTI) risks, and organ-function dosing violations prior to pharmacist sign-off.
2. **Reduced Clinical Burden & Alert Fatigue:** Automate routine cross-referencing while tiering alerts by clinical severity and confidence so pharmacists focus on high-risk interventions.
3. **Universal Healthcare Interoperability:** Ingest and emit standard **HL7 FHIR R4** resources (`Patient`, `MedicationRequest`, `MedicationStatement`, `AllergyIntolerance`, `Observation`, `DetectedIssue`, `Task`) normalized to **RxNorm (`RxCUI`)**, **SNOMED CT**, and **NDC**.
4. **Zero-Trust Privacy & Auditability:** Scrub/tokenize Protected Health Information (**PHI**) prior to any LLM call and record every agent decision, prompt version, and human override in a tamper-evident, hash-chained SQLite WAL audit ledger.

---

## 2. Multi-Agent System Architecture (6-Agent Hierarchical-Parallel Squad)

All inter-agent messages, tool outputs, and state transitions MUST enforce **Pydantic v2** data contracts (`extra="forbid"`, `frozen=True`) over a shared session **Blackboard State**.

| Agent | Role & Execution Mode | Core Responsibilities | Output Contract |
| :--- | :--- | :--- | :--- |
| **1. Chief Medical Orchestrator** | Hierarchical Lead & State Manager | Delegates tasks, validates every agent output against Pydantic v2 schemas, executes **Arbitration Logic** on agent conflicts, and enforces the **3-Turn Circuit Breaker** (`HALT_FOR_HUMAN`). | `OrchestratorState` |
| **2. Intake & Terminology Agent** | Parallel Data Normalization | Parses structured/unstructured prescriptions, evaluates **OCR confidence** (flagging NTI drugs or low OCR clarity for HITL), and normalizes drug strings to **RxNorm (`RxCUI`)**, Semantic Clinical Drug (**SCD**), **SNOMED CT**, and **NDC**. | `IntakeOutput` |
| **3. Clinical History Agent** | Parallel Context Collector | Fetches 12-month longitudinal patient history via **HL7 FHIR R4** (active meds, allergies, renal `eGFR`/creatinine, hepatic labs) with graceful handling for partial EHR records. | `ClinicalOutput` |
| **4. Safety & Contraindication Agent** | Deterministic Clinical Auditor | Runs **deterministic Python rule engines BEFORE any LLM synthesis**: DDI severity matrix, allergy cross-sensitivity, duplicate therapy classes, **Beer's Criteria** (geriatric ≥65), renal/hepatic dose ceilings, and **de-prescribing** candidates with **PubMed/RxNorm citations**. | `SafetyOutput` |
| **5. Insurance & Formulary Agent** | Coverage & Prior Auth Specialist | Checks payer formulary tier, copay estimate, and Prior Authorization (`requires_pa`, `pa_deadline`), falling back to **CMS standard formulary tier rules** when plan data is unavailable. | `InsuranceOutput` |
| **6. Pharmacist Liaison & Adversarial Hallucination Auditor** | Reflection Critic & HITL Compiler | **Adversarial Critic** verifies all safety alerts against raw `RxCUI`/FHIR source facts and scans for PHI leaks; **Liaison** compiles the 3-tier HITL report and deterministic HL7 FHIR R4 payloads (`MedicationRequest`, `DetectedIssue`, `Task`). | `AuditorOutput` & `LiaisonOutput` |

---

## 3. Functional Requirements

### FR-1: Terminology Normalization & BPMH 3-Way Reconciliation
* **FR-1.1:** Map all incoming medication names and local hospital aliases to standardized **RxNorm `RxCUI`** identifiers and Semantic Clinical Drug (**SCD**) strings.
* **FR-1.2:** Execute 3-way **BPMH** reconciliation comparing (a) active EHR `MedicationStatement` history, (b) patient-reported/OTC medications, and (c) new `MedicationRequest` orders.
* **FR-1.3:** Classify every medication discrepancy as **Intentional** (documented clinical dose/regimen change) or **Unintentional** (omission, duplication, or transcription conflict).
* **FR-1.4:** Flag low-confidence drug parses or OCR extractions—especially involving **Narrow Therapeutic Index (NTI)** medications (e.g., Warfarin, Digoxin, Lithium, Phenytoin)—for mandatory manual clarification.

### FR-2: Deterministic Clinical Safety Guardrails (Zero LLM Command Synthesis)
* **FR-2.1 (Fail-Closed Contraindication Rule):** Any contraindicated/major DDI, therapeutic class duplication, or documented patient allergy cross-reactivity (e.g., Penicillin allergy → Amoxicillin/Cephalosporin beta-lactam cross-reactivity) MUST deterministically trigger `HOLD_PRESCRIPTION` + `ESCALATE_TO_CLINICAL_PHARMACIST`.
* **FR-2.2 (Organ-Function Dosing Bounds):** Validate dosage and frequency against patient renal (`eGFR` / Serum Creatinine) and hepatic lab observations. Missing required labs for renally/hepatically cleared or NTI drugs MUST deterministically trigger `REQUEST_RENAL_HEPATIC_LABS`.
* **FR-2.3 (Geriatric Beer's Criteria & De-Prescribing):** Flag potentially inappropriate medications in patients aged ≥65 per AGS Beer's Criteria and surface evidence-backed de-prescribing recommendations (`PROPOSE_THERAPEUTIC_ALTERNATIVE`).
* **FR-2.4 (Fail-Closed Catalog Integrity):** Load interaction and formulary matrices from schema-validated local catalogs (`config/drug_interactions.json`); missing or corrupted catalog files MUST raise `CatalogNotFoundError` and fail closed to human escalation.
* **FR-2.5 (Evidence Citations):** Every clinical warning or recommendation MUST attach a verifiable source reference (RxNorm interaction ID, NLM/Lexicomp section, or **PubMed ID**).

### FR-3: Three-Tier Human-in-the-Loop (HITL) Governance & Pharmacist Workflow
Every reconciled item is assigned a unified **Risk & Confidence Grade**:

| Tier & Grade | Trigger Conditions | System Action & Pharmacist Requirement |
| :--- | :--- | :--- |
| **Tier 1: 🔴 RED (Mandatory Lock)** | Contraindicated/Major DDI, allergy cross-reactivity, OCR failure on NTI drug, or AI confidence **`< 0.70`** (`70%`). | Hard workflow lock (`HOLD_PRESCRIPTION`). Pharmacist MUST enter a structured **Clinical Justification Code** to override/dismiss and apply digital NPI attestation. |
| **Tier 2: 🟡 YELLOW (Affirmative Review)** | Moderate DDI, duplicate therapy warning, renal/hepatic dose adjustment, Prior Auth required, or AI confidence **`0.70 – 0.89`** (`70%–89%`). | Requires explicit pharmacist **Review & Accept** or **Modify** (with reason text) before advancing. |
| **Tier 3: 🟢 GREEN (Passive Observation)** | Verified medication match with zero clinical conflicts and AI confidence **`≥ 0.90`** (`90%`). | Logged automatically to the immutable audit trail; visible in UI without blocking workflow. |

* **FR-3.1 (Adjudication Actions):** For every line item, the pharmacist can **Accept**, **Modify** (opens dose/frequency editor + mandatory reason), **Dismiss** (mandatory clinical justification code), **Flag for Physician** (generates FHIR `Task` note), or run an interactive **"What-If" Sandbox** dry-run.
* **FR-3.2 (Final Attestation):** No FHIR `POST` commit to the EHR (`APPROVE_RECONCILED_LIST`) is permitted without explicit pharmacist checkbox verification and digital NPI/user signature.
* **FR-3.3 (Active Learning Feedback Loop):** Track repeated dismissals of Tier 3 informational alerts (alert-fatigue telemetry) and provide a **"Report Hallucination/Error"** button that quarantines the session for QA review.

### FR-4: Three-Column Pharmacist Workbench UI (Streamlit / FastAPI)
* **Left Column (Input Evidence):** Displays raw prescription scan/text, OCR confidence badges, and 12-month EHR medication/allergy/lab history.
* **Center Column (Reconciliation Workbench):** Displays the BPMH diff view (Added, Modified, Continued, Discontinued) with Traffic-Light badges (`RED`/`YELLOW`/`GREEN`) and the "What-If" simulation toggle.
* **Right Column (Safety Rail & Breadcrumbs):** Displays prioritized safety/hallucination alerts with expandable evidence pop-overs, agent execution breadcrumbs (`Intake → History → Safety → Insurance → Auditor`), and an orange **Circuit Breaker Banner** if the 3-turn agent consensus limit is reached.

### FR-5: MCP & API Interoperability
Expose deterministic clinical tools and resources over FastAPI and Model Context Protocol (`smartrx://`):
* **Resources:** `smartrx://catalog/interactions`, `smartrx://audit/escalations`
* **Tools:** `smartrx://reconcile/verify` (executes full deterministic + multi-agent safety verification)
* **Prompts:** `clinical_reconciliation_review` (structured pharmacist handoff summary)

---

## 4. Non-Functional, Security & Compliance Requirements

### NFR-1: HIPAA Privacy & Zero-Trust PHI Protection
