# 🏛️ Universal Enterprise AI Agent Blueprint & Governance Framework

<p align="center">
  <a href="#-architecture--the-7-core-governance-files"><strong>Architecture</strong></a> •
  <a href="#-universal-placeholder-token-specification"><strong>Token Matrix</strong></a> •
  <a href="#-quick-start-automated-bootstrapper-init_projectpy"><strong>Quick Start</strong></a> •
  <a href="#-the-first-5-minutes-after-cloning-quick-start-guide"><strong>First 5 Minutes</strong></a> •
  <a href="#-post-bootstrap-domain-customization-protocol"><strong>Domain Customization</strong></a> •
  <a href="#-verification--integrity-checklist"><strong>Integrity Checklist</strong></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.13+" />
  <img src="https://img.shields.io/badge/Architecture-Hexagonal%20Clean-orange?style=for-the-badge" alt="Hexagonal Architecture" />
  <img src="https://img.shields.io/badge/Pydantic-v2.0+-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic v2" />
  <img src="https://img.shields.io/badge/Protocol-MCP%20Dual--Transport-blueviolet?style=for-the-badge" alt="MCP Dual-Transport" />
  <img src="https://img.shields.io/badge/Security-Cryptographic%20HMAC-success?style=for-the-badge" alt="Cryptographic HMAC" />
  <img src="https://img.shields.io/badge/Governance-v1.1%20Enterprise-blue?style=for-the-badge" alt="v1.1 Enterprise Standard" />
  <img src="https://img.shields.io/badge/Coverage-≥90%25-brightgreen?style=for-the-badge" alt="Coverage ≥90%" />
</p>

> **Universal Template Standard:** Tier-1 Enterprise Autonomous Agent Governance Framework.  
> **Status:** Turnkey Standalone Template Repository with `{{...}}` Universal Parameter Tokens.  
> **Runtime:** Python 3.13+ Standard Library (Zero External Dependencies for Bootstrapping).  
> **Forensic Memory:** 64 Battle-Tested Historical Loophole Defenses (`GEM-LH-001`–`031` & `EBP-LH-001`–`033`).

---

## 1. Overview & Architecture of the Governance Suite

The **Universal Enterprise AI Agent Blueprint** solves the defining dilemma of autonomous software engineering: **how to maintain institutional-grade code quality, deterministic security invariants, and complete operational transparency across multi-turn autonomous coding agent sessions.**

Autonomous coding agents frequently suffer from context drift, hallucinated APIs, silent error suppression, premature checklist sign-offs, and architectural regression. To prevent these failure modes, this template establishes a battle-tested tripartite governance architecture across **7 synchronized core files**:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SUPREME SOURCE OF TRUTH                                   │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                      GEMINI.md                                      │   │
│   │                         (The Supreme Law & Security Invariants)                     │   │
│   └──────────────────────────────────────────┬──────────────────────────────────────────┘   │
│                                              │ Governs Invariants & Bounds                  │
│                                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                               Enterprise_Blueprint.md                               │   │
│   │                         (The 12-Phase Master Engineering Roadmap)                   │   │
│   └────────────────────┬─────────────────────────────────────────────────┬──────────────┘   │
│                        │ Gates Delivery & Verification                   │ Maps Symbols     │
│                        ▼                                                 ▼                  │
│   ┌──────────────────────────────────────────┐      ┌───────────────────────────────────┐   │
│   │          Blueprint_Debug_Log.md          │      │          PROJECT_MAP.md           │   │
│   │   (Incidents & 66 Forensic Loopholes)    │      │  (Compact < 60-Line Target Index) │   │
│   └────────────────────┬─────────────────────┘      └───────────────────────────────────┘   │
│                        │ Tracks Feature & Remediation Milestones                            │
│                        ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                               AUDIT_REMEDIATION_LOG.md                              │   │
│   │               (Chronological Feature Additions & Security Remediations)             │   │
│   └─────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### The 7 Core Governance Files & How They Work Together

1. **[`README.md`](README.md) (Central Hub & Template Specification):**
   - Serves as the executive navigation root and operational manual for engineers and autonomous agents.
   - Defines the universal `{{...}}` placeholder token matrix and provides turnkey CLI runbooks for cloning new projects.

2. **[`GEMINI.md`](GEMINI.md) (The Supreme Law / Non-Negotiable Invariants):**
   - Acts as the unyielding system constitution for both human engineers and AI coding agents.
   - Defines runtime constraints, type safety requirements (`typing`, Pydantic v2 `extra="forbid", frozen=True`), strict `ActionType` Enum permit matrices, deterministic execution overwriting (zero LLM command synthesis), full-payload HMAC-SHA256 signing with anti-replay TTLs ($\le 300\text{s}$ rejecting `current_time >= expires_at`), request idempotency deduplication (`idempotency_key`), dual-layer 10MB payload size defense, multi-tier resilience cascades (Gemini $\to$ OpenRouter $\to$ Deterministic Heuristics), dynamically instantiated per-operation SQLite WAL `filelock.FileLock` with MVCC read-bypass, startup schema versioning (`PRAGMA user_version`), graceful `SIGTERM`/`SIGINT` SSE stream drainage with WAL truncate checkpoints, Unicode NFKC normalization (`unicodedata.normalize("NFKC", val).strip().casefold()`), and OpenAPI 3.0 Protobuf sanitization.
   - Enforces **Cohesive Phase-Batched Execution (3–5 tightly coupled tasks/turn)**, targeted line-range reads via `PROJECT_MAP.md`, **quiet `pytest -q --tb=short` verification**, **Anti-Test-Cheating & Verifiable Proof Invariant** (zero test tampering, no self-mocking of internal functions/guardrails, mandatory verbatim pytest terminal proof), **Session Context Circuit Breaker & Fresh-Session Handoff Protocol** (preventing context rot), and the **3-Strike Anti-Looping Circuit Breaker** (halting and logging to `Blueprint_Debug_Log.md` upon 3 consecutive command failures).

3. **[`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) (The Master Backlog & 12-Phase Execution Roadmap):**
   - Serves as the living engineering roadmap and task checklist across Phases 0–12.
   - Defines the strict architectural Definition of Done (DoD) for every milestone.
   - Enforces cohesive phase-batched execution with mandatory local (`ruff`, `mypy`, `pytest >= 90%`) and CI/CD supply-chain verification gates (PEP 639 license audits, scoped secret scans, pinned lockfiles, live GitHub Actions proof) before any task checkbox (`[ ]`) can be marked complete (`[x]`).

4. **[`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md) (Living Operational Ledger & Forensic Memory):**
   - Centralizes real-time incident tracking across all build phases using a strict 5-step operational protocol (quarantine, forensic RCA, fix implementation, regression test, ledger recording).
   - **Historical Loophole Registry:** Permanently preserves **66 battle-tested architectural loophole entries** (`GEM-LH-001` through `GEM-LH-032` and `EBP-LH-001` through `EBP-LH-034`) documenting edge cases (e.g. SQLite WAL starvation, chunked transfer memory exhaustion, HMAC serialization desynchronization, test assertion tampering, infinite looping, cross-platform UTF-8 encoding gaps, boundary replay windows, session context rot, and cross-platform command syntax traps) so new projects never repeat identical design flaws.

5. **[`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md) (Chronological Feature & Remediation Ledger):**
   - Standardized, permanent chronological ledger of all proactive feature additions, architectural enhancements, and red-team security remediations across all versions and build phases (complementing `Blueprint_Debug_Log.md`).

6. **[`PROJECT_MAP.md`](PROJECT_MAP.md) (Compact Repository Index):**
   - Compact (< 60-line) architectural index mapping all repository paths to primary classes/functions.
   - Enables targeted line-range reads and eliminates prompt context rot from re-reading whole repository trees.

7. **[`init_project.py`](init_project.py) (The Zero-Dependency Project Bootstrapper):**
   - Standalone Python 3.13+ standard library automation script.
   - Automates cloning, input validation, atomic `{{...}}` token substitutions, checkbox re-initialization, directory scaffolding (including starter `PROJECT_MAP.md`), Git repository initialization, and post-run residual audits.

---

## 2. Universal Placeholder Token Specification

This template repository is 100% parameter-driven using universal double-brace `{{...}}` tokens. When initializing a new project via [`init_project.py`](init_project.py), every token is atomically replaced with project-specific values:

| Placeholder Token | Description / Semantic Role | Example Value | Target Files Reconfigured |
|---|---|---|---|
| `smartrx-safety-agents` | Kebab-case unique project identifier and CLI console entrypoint command name | `demo-ai-platform`, `secops-sentinel` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md), [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md), [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md), [`PROJECT_MAP.md`](PROJECT_MAP.md), [`README.md`](README.md) |
| `smartrx_safety_agents` | PEP 8 snake_case Python package identifier and root import directory (`src/<pkg>/`) | `demo_ai_platform`, `secops_sentinel` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md), [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md), [`PROJECT_MAP.md`](PROJECT_MAP.md), [`README.md`](README.md) |
| `Smartrx Safety Agents` | Human-readable title of the project | `Demo AI Platform`, `Secops Sentinel` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md), [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md), [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md), [`PROJECT_MAP.md`](PROJECT_MAP.md), [`README.md`](README.md) |
| `smartrx` | Scheme prefix for Model Context Protocol resource URIs (`<prefix>://...`) | `demo`, `secops` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `smartrx` | Prefix for the SQLite WAL persistence ledger (`<prefix>_ledger.db`) | `demo`, `secops` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `SMARTRX_SAFETY_AGENTS` | Uppercase prefix for webhook, callback, and signing secret environment variables (`<PREFIX>_WEBHOOK_SECRET`) | `DEMO_AI_PLATFORM`, `SECOPS_SENTINEL` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `Standard Enterprise Cloud (AWS / Azure / Kubernetes)` | Human-readable cloud deployment compute target and instance/service profile | `AWS Free Tier (t3.micro / t4g.small)`, `Azure Free Tier (App Service F1 / Container Apps)`, `Standard Enterprise Cloud (AWS / Azure / Kubernetes)` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `2048` | Hard upper memory ceiling in megabytes (`512`, `1024`, `2048`) | `512`, `1024`, `2048` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `1750` | Active reasoning RAM watchdog threshold in megabytes (`450`, `850`, `1750`) triggering fallback cascades | `450`, `850`, `1750` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `8192` | Hard output token cap for LLM responses (`4000` for Free Tier, `8192` for Standard Cloud) | `4000`, `8192` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `Permits any multi-agent, RAG, or MCP orchestration framework (including LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, or direct typed SDKs) provided that all inter-agent messages, retrieval chunks, state schemas, and data contracts strictly enforce Pydantic v2 validation (extra='forbid', frozen=True) and all external actions/tools are encapsulated inside deterministic GuardrailEngine wrappers.` | AI framework governance clause (`orchestrated` multi-agent/RAG/MCP vs. `rag-mcp` vs. `zero-bloat` direct SDK) | Governed universal framework allowance (LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, direct SDKs) or zero-bloat standard | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |
| `Cloud_Deployment_Guide.md` | Target cloud deployment runbook filename (`AWS_Deployment_Guide.md`, `Azure_Deployment_Guide.md`, `Cloud_Deployment_Guide.md`) | `AWS_Deployment_Guide.md`, `Cloud_Deployment_Guide.md` | [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) |

---

## 3. Quick-Start: Automated Bootstrapper (`init_project.py`)

A zero-dependency, production-grade Python 3.13+ standard library bootstrapper is built directly into [`init_project.py`](init_project.py) to automate the entire cloning and customization lifecycle.

### 1. Turnkey Production Bootstrapping (Recommended)
Clone, reconfigure, scaffold starter directories, initialize Git repository, and verify zero residual strings in a single command:

**Standard Enterprise Cloud (Universal Multi-Agent / RAG / MCP Orchestrated - Default):**
```bash
python init_project.py \
  --project-id secops-sentinel \
  --target-dir ../secops-sentinel \
  --deploy-target standard-cloud \
  --orchestrator orchestrated \
  --mcp-prefix secops \
  --port 8080 \
  --primary-model gemini-3.8-flash-high \
  --scaffold-dirs \
  --git-init
```

**Retrieval-Augmented Generation (RAG) + Model Context Protocol (MCP) Server:**
```bash
python init_project.py \
  --project-id rag-mcp-demo \
  --target-dir ../rag-mcp-demo \
  --deploy-target standard-cloud \
  --orchestrator rag-mcp \
  --mcp-prefix demo \
  --scaffold-dirs \
  --git-init
```

**AWS Free Tier Compute (t3.micro / t4g.small, 512MB RAM, Zero-Bloat Direct SDK):**
```bash
python init_project.py \
  --project-id finops-worker \
  --target-dir ../finops-worker \
  --deploy-target aws-free-tier \
  --orchestrator zero-bloat \
  --scaffold-dirs \
  --git-init
```

### 2. Dry-Run Preview Mode
Inspect all planned file copies, directory scaffolding, regex substitutions, and residual audits without writing anything to disk:
```bash
python init_project.py \
  --dry-run \
  --project-id secops-sentinel \
  --target-dir ../secops-sentinel \
  --scaffold-dirs \
  --git-init
```

### 3. Interactive Guided Mode
Run the script with zero arguments to be prompted with smart, auto-derived defaults for every parameter:
```bash
python init_project.py
```

### Complete CLI Flags Reference (`init_project.py`)

| CLI Flag | Type / Choices | Default | Semantic Description |
|---|---|---|---|
| `--project-id` | `str` (kebab-case) | *Interactive prompt* | Unique project identifier (e.g. `secops-sentinel`) |
| `--package-name` | `str` (snake_case) | Auto-derived | Python package identifier (`src/<pkg>/`) |
| `--cli-entrypoint` | `str` (kebab-case) | Auto-derived | CLI console script entrypoint command |
| `--mcp-prefix` | `str` (alphanumeric) | Auto-derived | MCP protocol scheme prefix (`<prefix>://...`) |
| `--port` | `int` (1024–65535) | `8080` | Default HTTP / SSE gateway service port |
| `--primary-model` | `str` | `gemini-3.8-flash-high` | Primary frontier LLM engine identifier |
| `--deploy-target` | `standard-cloud`, `aws-free-tier`, `azure-free-tier` | `standard-cloud` | Cloud deployment compute profile & memory cap |
| `--orchestrator` | `orchestrated`, `rag-mcp`, `zero-bloat` | `orchestrated` | AI framework standard (universal multi-agent/RAG/MCP frameworks vs. RAG-MCP vs. zero-bloat direct SDK) |
| `--target-dir` | `path` | `.` | Destination root directory for cloned project |
| `--dry-run` | Flag | `False` | Preview transformations without touching disk |
| `--force` | Flag | `False` | Allow in-place modification of current repository |
| `--git-init` | Flag | `False` | Initialize Git repository on branch `main` with `.gitignore` and stage files |
| `--scaffold-dirs` | Flag | `False` | Generate starter directory skeleton (`src/`, `tests/`, `docs/`, `prompts/`) |

### What `init_project.py` Automates:
1. **Input Validation:** Enforces kebab-case project IDs (`^[a-z][a-z0-9-]*[a-z0-9]$`), PEP 8 package identifiers (`^[a-z][a-z0-9_]*$`), and valid port numbers (`1024`–`65535`).
2. **Safe Isolated Cloning:** Copies [`GEMINI.md`](GEMINI.md), [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md), [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md), [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md), [`README.md`](README.md), [`PROJECT_MAP.md`](PROJECT_MAP.md), and [`init_project.py`](init_project.py) into `--target-dir`, leaving the original template repository pristine (or requires explicit `--force` for in-place modifications).
3. **Universal Placeholder Reconfiguration:** Replaces `smartrx-safety-agents`, `smartrx_safety_agents`, `Smartrx Safety Agents`, `smartrx`, `smartrx`, `SMARTRX_SAFETY_AGENTS`, `Standard Enterprise Cloud (AWS / Azure / Kubernetes)`, `2048`, `1750`, `8192`, `Permits any multi-agent, RAG, or MCP orchestration framework (including LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, or direct typed SDKs) provided that all inter-agent messages, retrieval chunks, state schemas, and data contracts strictly enforce Pydantic v2 validation (extra='forbid', frozen=True) and all external actions/tools are encapsulated inside deterministic GuardrailEngine wrappers.`, and `Cloud_Deployment_Guide.md` across all files.
4. **Task & Checkbox Reset:** Re-initializes all completed tasks (`- [x]`) in [`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) back to open status (`- [ ]`).
5. **State & Incident Ledger Reset:** Resets Section 2 of [`Blueprint_Debug_Log.md`](Blueprint_Debug_Log.md) to a single clean baseline initialization entry while **100% preserving Section 3 historical architectural loopholes** (`GEM-LH-001` through `GEM-LH-031` and `EBP-LH-001` through `EBP-LH-033`), and resets Section 2 of [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md) to a clean baseline initialization entry.
6. **Starter Skeleton Scaffolding (`--scaffold-dirs`):** Generates package and test skeletons (`src/<package>/__init__.py`, `tests/__init__.py`, `docs/`, `prompts/modules/`) with valid package metadata.
7. **Git Repository Initialization (`--git-init`):** Initializes a fresh Git repository on branch `main`, generates a comprehensive production `.gitignore`, and stages initial governance files (`git add .`).
8. **Automated Post-Run Residual & Token Audit:** Scans all generated files to guarantee **zero unreplaced `{{...}}` tokens** and **zero legacy template tokens** remain, printing `[PASS]` confirmations.

---

## 4. The First 5 Minutes After Cloning (Quick-Start Guide)

Whether you are a human engineer or an autonomous AI coding agent, follow this exact sequence immediately after running `init_project.py`:

1. **Inspect Configuration & Repository Map:**
   - Copy `.env.example` to `.env` (`cp .env.example .env` on Linux/macOS, or `Copy-Item .env.example .env` on Windows PowerShell).
   - Configure secrets: `GEMINI_API_KEY`, `PLAN_SIGNING_SECRET`, `MCP_API_KEY`, and optional `OPENROUTER_API_KEY`.
   - Review [`PROJECT_MAP.md`](PROJECT_MAP.md) to familiarize with the module layout and target file responsibilities without running full directory scans.
2. **Review Domain Action Permits in `GEMINI.md`:**
   - Locate `[DOMAIN REFERENCE]` in Section 3.1: Replace reference cloud infrastructure verbs (`TERMINATE_INSTANCE`, `STOP_INSTANCE`, etc.) with your domain's canonical state mutations (e.g., `REVOKE_ACCESS`, `ISOLATE_HOST`, `EXECUTE_TRADE`, `FLAG_TRANSACTION`).
   - In Section 3.2: Bind those canonical action verbs to deterministic Python templates (IAM policies, CLI strings, rollback routines) ensuring zero LLM command synthesis.
3. **Align Living Roadmap in `Enterprise_Blueprint.md` & Initialize Ledgers:**
   - In Phase 2.1: Adjust domain model filenames under `src/smartrx_safety_agents/models/` and heuristics under `src/smartrx_safety_agents/heuristics/`.
   - In Phase 5: Adjust registered MCP tools and prompts under `smartrx://...`.
   - Maintain [`AUDIT_REMEDIATION_LOG.md`](AUDIT_REMEDIATION_LOG.md) to log all completed features, architectural changes, and security remediations throughout the build lifecycle.
4. **Execute Phase 0.1 Forensic Baseline Audit:**
   - Run the Phase 0.1 audit evaluating your repository across the 10 enterprise dimensions and generate `Blueprint_Repo_Baseline_AuditReport.md`.
   - Mark `[x]` on Phase 0.1 in `Enterprise_Blueprint.md` only after verifying all hyperlinks and document contracts.
5. **Begin Phase 1 Modular Build:**
   - Author `pyproject.toml` (Task 1.1) and verify editable installation (`pip install -e ".[dev]"`).

---

## 5. Post-Bootstrap Domain Customization Protocol

After running [`init_project.py`](init_project.py), engineers must manually customize **five domain-specific sections** to align the governance suite with their project's domain requirements (e.g., healthcare informatics, cybersecurity, financial trading):

1. **[`GEMINI.md`](GEMINI.md) Section 3.1 (`ActionType` Enum Allowlist):**
   - Replace the reference FinOps cloud infrastructure actions (`TERMINATE_INSTANCE`, `STOP_INSTANCE`, `MODIFY_S3_LIFECYCLE`, etc.) with your domain's canonical state mutations (e.g., `BLOCK_IP`, `REVOKE_CREDENTIAL`, `ISOLATE_NODE`, `FLAG_TRANSACTION`).
2. **[`GEMINI.md`](GEMINI.md) Section 3.2 (`Deterministic Execution Overwriting`):**
   - Bind each canonical action verb to deterministic Python template functions (IAM policies, API execution payloads, rollback commands), ensuring the LLM never synthesizes executable commands directly.
3. **[`GEMINI.md`](GEMINI.md) Section 3.8 (`[Reference Domain Implementation: Cloud FinOps & SRE]`):**
   - Replace reference FinOps heuristics (EC2 CPU/memory floors, S3 object size thresholds) with your domain's specific safety bounds (e.g., maximum transaction velocity, blast-radius container caps, patient data redaction rules).
4. **[`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) Phases 2–4 (`Domain Heuristics & Guardrails`):**
   - Replace the reference FinOps heuristics (EC2, RDS, S3, EBS, EIP rules) with your domain's deterministic rule engines, automated rollback generators, and catalog lookup structures.
5. **[`Enterprise_Blueprint.md`](Enterprise_Blueprint.md) Phase 5 (Tasks 5.5–5.7: `MCP Tools, Prompts & Resources`):**
   - Register your domain-specific tools, prompts, and resources under `smartrx://...`.

---

## 6. Verification & Integrity Checklist

Whenever you modify any document within this governance suite, run the following verification checks:
* [x] **Zero Broken Links:** Ensure all relative markdown hyperlinks point to valid, existing repository paths.
* [x] **Strict Invariant Parity:** Ensure every security invariant in `GEMINI.md` is mapped to an explicit verification task in `Enterprise_Blueprint.md`.
* [x] **Non-Destructive Debug Logging:** Never renumber or remove historical loophole entries (`GEM-LH-*` or `EBP-LH-*`) in `Blueprint_Debug_Log.md`.
* [x] **Zero-Hallucination Gate:** Never claim tests pass or modules exist until physical code files are written, executed, and verified on disk.
* [x] **Anti-Test-Cheating Compliance:** Include verbatim pytest terminal output lines showing passed counts and code coverage ($\ge 90\%$); never mock internal logic or weaken assertions.
* [x] **3-Strike Circuit Breaker:** Immediately halt, record forensic RCA in `Blueprint_Debug_Log.md`, and escalate if 3 consecutive failures occur on the same command.
