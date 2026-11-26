# Master Production Elevation Blueprint & Engineering Plan (`Enterprise_Blueprint.md`)

> **Consolidated Architecture & Backlog Notice:** This document serves as the unified **Master Production Elevation Blueprint**, **Living Engineering Plan**, and **Active Build Backlog** for `smartrx-safety-agents` (consolidating and replacing `PLAN.md`). All architectural milestones, task checklists, security invariants, and verification runbooks are maintained solely within this blueprint.

**Project:** Smartrx Safety Agents (`smartrx-safety-agents`)  
**Lead Architect:** Principal Senior AI Systems Architect, Lead SRE & Staff Security Engineer  
**Status:** Living Engineering Plan & Active Build Backlog (Unified Roadmap)  
**Target Standard:** Tier-1 Enterprise Production Grade  
**Runtime:** Python 3.13+ (PEP 517/621, Pydantic v2, FastAPI, SQLite WAL, Click CLI)  

---

## 1. Architectural Tenets & Definition of Done (DoD)

Every phase in this blueprint must satisfy the following **Definition of Done (DoD)** before its tasks can be marked complete:

1. **AI Framework Architecture & Governance Standard:** Permits any multi-agent, RAG, or MCP orchestration framework (including LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, or direct typed SDKs) provided that all inter-agent messages, retrieval chunks, state schemas, and data contracts strictly enforce Pydantic v2 validation (extra='forbid', frozen=True) and all external actions/tools are encapsulated inside deterministic GuardrailEngine wrappers. Supports multi-agent graphs (LangGraph, CrewAI, AutoGen), RAG pipelines (LangChain, LlamaIndex, pgvector, FAISS, Chroma), and Model Context Protocol (MCP) servers alongside direct SDKs. Core reasoning, routing, retrieval, and tool dispatch must use typed data contracts (`pydantic` v2 `extra="forbid", frozen=True`) with native JSON Schema constrained decoding (`responseSchema` with OpenAPI 3.0 sanitization). Enforce a strict **10MB incoming body-size ceiling** returning HTTP 413 Payload Too Large / JSON-RPC error on breach to protect container heap memory within 2048MB.
2. **Deterministic Schema Compliance, Action Enums & Zero Hallucination (Code & Documentation):** 100% of inter-module data structures, telemetry inputs, execution payloads, and documentation references (`docs/*.md`, `README.md`) must be governed by strict zero-hallucination standards and Pydantic v2 models (`ConfigDict(extra="forbid", frozen=True)`). Proposed remediation actions must strictly map to the `ActionType` Enum (`TERMINATE_INSTANCE`, `STOP_INSTANCE`, `MODIFY_INSTANCE_TYPE`, `MODIFY_S3_LIFECYCLE`, `DELETE_EBS_VOLUME`, `RELEASE_EIP`, `ENABLE_INTELLIGENT_TIERING`). Unconditionally reject and quarantine (`quarantined=True`, `quarantine_reason="INVALID_ACTION_ENUM_TYPE"`) any action outside this allowlist. Deterministically overwrite any LLM-synthesized AWS IAM policies and CLI execution strings using Python templates.
3. **Calibrated Safety Enforcement & Quarantine Pattern:** Every action proposed by the system must be scored on a 1–5 Safety Risk scale. Any action with Safety Risk Score $\ge 3$ lacking explicit, validated automated mitigations and deterministic rollback procedures must be quarantined (`quarantined=True`, `quarantine_reason="MISSING_MANDATORY_ROLLBACK"`) rather than executed or silently backfilled with generic templates.
4. **Resilient Multi-Path Uptime, RAM Safeguards & Catalog Fallback:** Achieve 100% evaluation availability via a three-tier cascade: Primary Gemini 3.8 Flash High (with dynamic `thinkingBudget`, capped at 8192 output tokens per request) $\to$ Secondary OpenRouter/OpenAI-compatible fallback (with `<think>` tag stripping) $\to$ Tertiary Deterministic SRE Heuristic Engine (100% offline availability). If active reasoning buffers approach the 2048MB RAM ceiling, proactively drop the active reasoning round and fall back to Secondary or Tertiary engines. If `config/instance_mappings.json` is missing or corrupted, immediately raise `CatalogNotFoundError` and route execution to the Tertiary engine—forbidding silent zero-cost defaults.
5. **Cryptographic Payload Integrity & Strict Canonical Serialization:** All remediation plans must be cryptographically sealed with a full-payload HMAC-SHA256 signature (`plan_signature`) over canonical JSON generated strictly via `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`. Generic, un-sorted, or non-deterministic serialization methods are strictly prohibited. Authentication endpoints must use constant-time matching (`hmac.compare_digest()`) and fail closed in production when secrets are unconfigured.
6. **Cloud-Native Deployment Portability & Memory Ceiling:** The system must run within a single non-root Docker container consuming $< 75\text{ MB}$ disk footprint and $< 2048\text{ MB}$ RAM, fully deployable on Standard Enterprise Cloud (AWS / Azure / Kubernetes). Payloads $> 10\text{ MB}$ are rejected before body buffering.
7. **Continuous Observability & SQLite WAL Lock Isolation:** All operations must be traceable via OpenTelemetry spans, recorded in an append-only, thread-safe SQLite WAL ledger, and monitored across the Four Golden Signals. Cross-platform `filelock.FileLock` operations must strictly wrap WRITE mutations only; all READ queries must completely bypass `filelock` and rely on SQLite native MVCC to eliminate writer starvation and WAL bloat.
8. **Cohesive Phase-Batched Execution, Targeted Reads & Fresh-Session Handoff Protocol:** Build and execute in cohesive batches of 1 coherent phase or 3–5 tightly coupled tasks per turn following SOLID industry best practices. Maintain a compact (< 60-line) `PROJECT_MAP.md` at repository root, performing targeted line-range reads of active specs and only the 2–4 target files per turn rather than re-reading thousands of lines. Execute single quiet verification sweeps (`ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && pytest -q --tb=short --cov=src/smartrx_safety_agents --cov-report=term:skip-covered --cov-fail-under=90`). AI agent sessions must not exceed 1–2 cohesive phases (~60% context window); upon completion or bloat, update `PROJECT_MAP.md`, ensure clean `git status --short`, and emit a Mandatory Fresh-Session Handoff Block before opening a fresh chat session. During Phase 0 and Phase 1 (before application source code is generated under `src/`), static validation syntax analysis runs exclusively on Markdown hyperlinked integrity, schema validation files, and configuration syntax, preventing empty directory tool errors. All modular prompts must be saved in `modular_prompt.md`.
9. **Anti-Test-Cheating, Verifiable Proof & Anti-Looping Circuit Breaker:** Zero test tampering permitted (no test deletions, weakened assertions, skipped tests, lowered coverage gates, or self-mocking of internal guardrails). Every task completion must provide verbatim terminal output from `pytest` showing pass counts and $\ge 90\%$ coverage. If any verification or build command fails 3 consecutive times on the same module/error, the agent must immediately halt, log the incident in `Blueprint_Debug_Log.md`, and escalate to the human engineer.
10. **Cross-Platform UTF-8 I/O & LLM Cost Circuit Breakers:** All file read/write operations must explicitly declare `encoding="utf-8"` across all platforms. Ingestion file reads must be bounded by byte/line caps (max 800 lines / 46KB). Active LLM usage is constrained by session token (`MAX_SESSION_TOKEN_BUDGET=500_000`) and cost (`DAILY_API_COST_LIMIT_USD=10.00`) circuit breakers that fail-safe route to Tertiary heuristics upon breach.

---

## 2. Phase-by-Phase Production Checklist

### Phase 0: [UNIVERSAL CORE] Requirements, Architecture & Navigation Hub
*Goal: Establish institutional-grade specifications, hyperlinked documentation navigation, and audit baselines before executing codebase changes.*

- [ ] **0.1 Forensic Baseline Audit:** Author `Blueprint_Repo_Baseline_AuditReport.md` evaluating the repository across 10 enterprise dimensions with letter grades and technical debt backlog.
- [ ] **0.2 Product Requirements Document:** Author `docs/PRD.md` detailing product vision, personas, functional capabilities (FS-1 to FS-8), edge cases, and KPIs.
- [ ] **0.3 Technical Requirements Document:** Author `docs/TRD.md` specifying JSON-RPC 2.0 contracts, mathematical waste formulas, Gemini thinking budget payload specs, 10MB payload ceiling, 8192 output token cap, and NFRs.
- [ ] **0.4 Harmonize User Requirements:** Author/update `docs/URD.md` aligning multi-model fallback, dual MCP transports, and persona workflows.
- [ ] **0.5 Harmonize System Architecture:** Author/update `docs/ARCHITECTURE.md` with revised C4 container diagrams, sequence flows, SQLite MVCC read-bypass architecture, and decoupled subsystem boundaries.
- [ ] **0.6 Master Production Backlog:** Maintain `Enterprise_Blueprint.md` as the living engineering roadmap and task checklist.
- [ ] **0.7 Centralized README Navigation Hub:** Overhaul root `README.md` to serve as the master navigation index containing working relative Markdown hyperlinks (`[Title](path/to/file.md)`) separating core architectural specifications from blueprint audit logs:
  - **Core Specifications (`docs/`):**
    - `docs/URD.md`
    - `docs/PRD.md`
    - `docs/TRD.md`
    - `docs/ARCHITECTURE.md`
    - `docs/Cloud_Deployment_Guide.md`
    - `docs/MONITORING_AND_OBSERVABILITY.md`
  - **Blueprint Audits & Logs:**
    - `README.md`
    - `Blueprint_Repo_Baseline_AuditReport.md`
    - `Blueprint_Production_Readiness_Report.md`
    - `Blueprint_Debug_Log.md`
    - `AUDIT_REMEDIATION_LOG.md`
- [ ] **0.8 Architectural Delta & Loophole Registry:** Maintain `Blueprint_Debug_Log.md` establishing a forensic registry of all architectural edge cases, vulnerability traps, incident resolutions, explicit technical fixes, and CI/CD verification gate impacts.
- [ ] **0.9 Project Map Index & Fresh-Session Handoff Protocol:** Create and maintain a compact (< 60-line) `PROJECT_MAP.md` at repository root mapping all files to primary classes/functions for targeted line-range reads, and establish the session context circuit breaker and fresh-session handoff protocol across agent workflows.

---

### Phase 1: [UNIVERSAL CORE] Foundation, Packaging & Environment Security
*Goal: Standardize packaging for Python 3.13+, establish security hygiene, and install CLI console entrypoints.*

- [ ] **1.1 PEP 517/621 Packaging:** Create/update `pyproject.toml` declaring dependencies, metadata, `pytest-timeout` (`timeout = 15`, `timeout_method = "thread"`), and the `smartrx-safety-agents` console script entrypoint targeting Python 3.13+.
- [ ] **1.2 Clean Environment Template:** Create `.env.example` documenting all configuration keys (`GEMINI_API_KEY`, `GEMINI_MODEL_NAME`, `GEMINI_THINKING_BUDGET`, `MAX_OUTPUT_TOKENS`, `MAX_PAYLOAD_SIZE_BYTES`, `MAX_SESSION_TOKEN_BUDGET`, `DAILY_API_COST_LIMIT_USD`, `OPENROUTER_API_KEY`, `MCP_API_KEY`, `PLAN_SIGNING_SECRET`, `SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET`, `ENVIRONMENT`, `REQUIRE_AUTH`, `DB_PATH`, `AUDIT_LOG_DIR`, `FILELOCK_TIMEOUT_SEC`, `PORT`) without exposing secrets, and document cross-platform setup commands (`cp .env.example .env` / `Copy-Item .env.example .env`).
- [ ] **1.3 Git Security Hygiene:** Overhaul `.gitignore` to prevent committing `.env`, virtual environments, SQLite databases (`*.db`, `*.db-wal`, `*.db-shm`), egg-info, or test caches. Verify via `git check-ignore -v .env`.
- [ ] **1.4 Remove Stray Scaffolding:** Purge legacy or foreign configs (`.continue/`, stale draft directories) referencing unrelated models or obsolete frameworks.
- [ ] **1.5 Master Agent Handbook:** Deploy `GEMINI.md` in repository root as the Universal Enterprise Master Handbook featuring the `[PROJECT_CONFIGURATION]` block and Template Cloning Note.
- [ ] **1.6 Editable Installation & Deterministic Lockfile:** Verify clean installation in a fresh virtual environment (`pip install -e ".[dev]"`), and generate and commit a deterministic lockfile (`uv.lock` or `requirements.lock`) to anchor supply-chain dependencies.

---

### Phase 2: [DOMAIN REFERENCE: FINOPS] Modular Core Architecture & Contract Isolation
*Goal: Structure the core package into clean, single-responsibility modules under `src/smartrx_safety_agents/` supporting any multi-agent graph, RAG pipeline, MCP server, or direct typed SDK architecture.*

- [ ] **2.1 Package Decomposition:** Author `src/smartrx_safety_agents/` with submodules:
  - [ ] `config.py`: Centralized `pydantic-settings` configuration loading `GEMINI_MODEL_NAME` (default: `gemini-3.8-flash-high`), `MAX_OUTPUT_TOKENS=8192`, `MAX_PAYLOAD_SIZE_BYTES=10485760` (10MB), and `FILELOCK_TIMEOUT_SEC=10.0` dynamically with fail-closed production checks.
  - [ ] `models/`: Strictly typed Pydantic v2 schemas: `ActionType` Enum mapping, `telemetry.py` (EC2, RDS, S3, EBS, EIP metrics), `remediation.py` (actions, plans, execution payloads with mandatory ISO-8601 UTC `issued_at`, `expires_at` [TTL $\le 300\text{s}$], and unique `plan_id` nonce for replay defense), `audit.py` (ledger events).
  - [ ] `guardrails/`: `risk_scorer.py` (1–5 safety scoring), `quarantine.py` (mitigation verification and Enum validation fail-closed sequence), `iam_policy.py` (least-privilege IAM policy generator), and `rollback.py` (deterministic rollback synthesis).
  - [ ] `heuristics/`: Deterministic rule engines: `ec2_rules.py`, `rds_rules.py`, `s3_rules.py`, `ebs_rules.py`, `eip_rules.py`, and `engine.py`.
  - [ ] `reasoner/`: `client.py` (Gemini 3.8 Flash High client with 8192 output token ceiling), `openrouter.py` (secondary fallback client), and `prompt_compiler.py` (anti-injection sanitization).
  - [ ] `ledger/`: `store.py` thread-safe audit ledger with SQLite WAL persistence and write-only file locking preserving MVCC for reads.
  - [ ] `mcp/`: Protocol servers: `server_stdio.py` (standard I/O JSON-RPC 2.0 with 10MB ceiling) and `server_sse.py` (FastAPI + Starlette SSE with 10MB body middleware).
  - [ ] `cli.py`: Click CLI runner with audit, dry-run, and server execution subcommands.
- [ ] **2.2 Backward Compatibility Shims:** Maintain necessary compatibility aliases to guarantee zero breaking changes across existing callers.
- [ ] **2.3 Baseline Test Suite Validation:** Verify that all initial module imports and basic contract unit tests pass cleanly.

---

### Phase 3: [UNIVERSAL CORE] Gemini 3.8 Flash High Reasoner & Multi-Model Resilience
*Goal: Maximize AI cognitive reasoning density, eliminate hallucinations, and provide seamless multi-model fallback across direct SDKs, multi-agent frameworks, and RAG pipelines.*

- [ ] **3.1 Dynamic Thinking Budget, Model Configuration, Cost Circuit Breaker & Total Exception Cascade:** Load primary model dynamically from `config.gemini_model_name` (default: `gemini-3.8-flash-high`, never hardcoded) and inject `thinkingConfig.thinkingBudget` (default: 2048 tokens, configurable via `GEMINI_THINKING_BUDGET`) into the Gemini `generationConfig` payload. Hard-cap `maxOutputTokens` at **8192 tokens**. Enforce session token budget (`MAX_SESSION_TOKEN_BUDGET=500_000`) and cost ceiling (`DAILY_API_COST_LIMIT_USD=10.00`) circuit breakers that halt frontier model execution upon breach and fail-safe route to Tertiary heuristics. Wrap primary execution in an exhaustive exception handler: any failure (including `httpx.TimeoutException`, `httpx.HTTPStatusError`, `json.JSONDecodeError`, `pydantic.ValidationError`, Protobuf parsing errors, or RAM watchdog breach) cascades cleanly to Secondary client with zero unhandled crashes.
- [ ] **3.2 Context Optimization, Bounded Reads & RAM Safeguards:** Ensure compacted JSON telemetry context consumes $< 4,000$ tokens for 50-resource batches ($< 100\text{k}$ total token budget). Enforce bounded file reading (max 800 lines / 46KB per tool invocation) to eliminate raw context dumping. Implement memory watch: if active reasoning graphs risk breaching the 2048MB RAM ceiling, proactively drop the active round and route to Secondary or Tertiary engines.
- [ ] **3.3 Secondary Multi-Model Fallback & Tertiary Relay:** Implement `OpenRouterFallbackClient` targeting OpenAI-compatible endpoints (e.g. Qwen 2.5 Coder 32B) triggered automatically on Gemini HTTP 429/503 errors, timeouts, validation errors, or RAM safeguard triggers. Ensure any failure in Secondary cascades cleanly to the Tertiary Deterministic SRE Heuristics engine.
- [ ] **3.4 Structured Output Enforcement (`responseSchema`):** Bind `generationConfig.responseSchema` directly into Gemini API calls. Sanitize schema using `clean_gemini_schema()` to resolve `$defs`, strip `$schema`/`additionalProperties`, collapse `anyOf` nullables to OpenAPI 3.0 `{"type": "...", "nullable": True}`, and restrict properties to `ALLOWED_GEMINI_FIELDS`.
- [ ] **3.5 Exponential Backoff & Jitter:** Implement automated retry policies (3 attempts, base 1.0s, max 8.0s with full jitter) for transient HTTP 429 and 503 errors before activating fallback engines.
- [ ] **3.6 Anti-Prompt Injection Defenses:** Wrap all untrusted telemetry data and ingested metrics inside `<untrusted_telemetry_data>` XML-style tags and sanitize all freeform strings against prompt-injection delimiters.
- [ ] **3.7 Strip `<think>` Reasoning Blocks:** In `openrouter.py`, strip any `<think>...</think>` internal reasoning blocks and markdown code fences before attempting JSON decoding.
- [ ] **3.8 Reasoner Unit Verification:** Add comprehensive unit tests in `tests/test_reasoner.py` covering thinking budget injection, 8192 token ceiling, fallback cascades, schema sanitization, and `<think>` block stripping.
- [ ] **3.9 Hierarchical PromptOps & `modular_prompt.md` Registry:** Save and maintain all modular prompts, master system instructions, and domain prompt templates inside `modular_prompt.md` at the repository root, synchronized with runtime prompt modules under `prompts/modules/` (EC2, RDS, S3, EBS/EIP, Guardrails/IAM, and MCP Runbooks).

---

### Phase 4: [DOMAIN REFERENCE: FINOPS] Deterministic SRE Heuristics & Guardrail Expansion
*Goal: Broaden rule coverage and enrich execution payloads with automated rollbacks and least-privilege IAM policies.*

- [ ] **4.1 Core Heuristic Rule Sets:** Implement deterministic heuristics with Unicode NFKC normalization (`unicodedata.normalize("NFKC", val).strip().casefold()`):
  - EC2 underutilization: average CPU $< 10\%$, with memory safety floor check (abort rightsizing if `memory_utilization_avg_pct > 65.0\%` to prevent OOM).
  - RDS idle instances: zero active connections over evaluation window.
  - S3 storage optimization: transition cold standard storage ($> 50\%$ infrequent access) to `INTELLIGENT_TIERING` only when average object size $\ge 128\text{ KB}$ (avoiding small-object monitoring fee traps).
- [ ] **4.2 Automated Rollback Synthesis:** Generate deterministic rollback commands (`rollback` payload) for every proposed action (e.g., restore previous instance type, revert S3 lifecycle configuration).
- [ ] **4.3 Real AWS Pricing Catalog Lookup & CatalogNotFoundError:** Integrate standard AWS On-Demand hourly pricing catalog (`config/instance_mappings.json`) and calculate exact dollar savings using `(curr_rate - tgt_rate) * 730.0` hours/month. If `config/instance_mappings.json` is missing, unreadable, or corrupted, raise `CatalogNotFoundError` and route to the Tertiary engine—forbidding silent $0.0 savings defaults. Zero out projected savings if resource is covered by `reserved` or `savings_plan` commitments.
- [ ] **4.4 Extended FinOps Heuristics:**
  - Unattached EBS volume detection (`ebs_rules.py`): unattached $\ge 30$ days with snapshot creation prior to termination.
  - Idle Elastic IP address reclamation (`eip_rules.py`): unassociated $\ge 7$ days.
- [ ] **4.5 Strict Action Enum & Least-Privilege IAM Generation:** Validate actions against `ActionType` Enum. Synthesize exact, minimal AWS IAM statements with strict ARN patterns (`arn:aws:ec2:*:*:instance/{res_id}`, `arn:aws:ec2:*:*:volume/{res_id}`, `arn:aws:rds:*:*:db:{res_id}`, `arn:aws:s3:::{res_id}`) and strictly scoped action verbs. Disallow wildcards (`*`).
- [ ] **4.6 Unconditional LLM Output Overwriting:** In `GuardrailEngine`, unconditionally overwrite `execution_payload["iam_policy"]`, `execution_payload["aws_cli"]`, and `execution_payload["rollback"]` using deterministic Python functions, stripping and discarding any LLM-hallucinated strings.
- [ ] **4.7 Quarantine Pattern for High-Risk & Invalid Actions:** Refactor `GuardrailEngine` to mark `quarantined=True` and assign `quarantine_reason` for any Risk $\ge 3$ action missing explicit rollback steps OR any action with an invalid action Enum.
- [ ] **4.8 Strict Canonical JSON HMAC Signing, Anti-Replay Verification & Request Idempotency:** Compute SHA-256 `plan_digest` and HMAC-SHA256 `plan_signature` over canonical JSON serialized explicitly via `json.dumps(plan.model_dump(mode="json", exclude={"plan_digest", "plan_signature"}), sort_keys=True, separators=(',', ':'), ensure_ascii=False)`. Enforce `verify_plan_signature()` with constant-time `hmac.compare_digest()` and verify `current_time < expires_at` (rejecting expired plans via `current_time >= expires_at` or replayed IDs). Enforce monotonic `plan_id` / `idempotency_key` deduplication so retried requests return cached signed plans without executing duplicate state mutations or duplicate ledger events. Enforce fail-closed `RuntimeError` if secret is unset in production.
- [ ] **4.9 Dry-Run Simulation Mode:** Support `--dry-run` flag across CLI and MCP tool calls to validate execution payloads in simulation mode without mutating infrastructure.

---

### Phase 5: [UNIVERSAL CORE] Dual-Transport Model Context Protocol (MCP) Expansion
*Goal: Provide full protocol compliance across both local desktop agents and remote agent gateways.*

- [ ] **5.1 Standard I/O Transport with UTF-8 Line Buffering & 10MB Ceiling:** Implement line-delimited JSON-RPC 2.0 loop over `sys.stdin`/`sys.stdout` with application logging redirected strictly to `sys.stderr`. Accumulate raw bytes to newline boundaries before decoding to avoid UTF-8 multibyte boundary splitting (`UnicodeDecodeError`), enforce 10MB ceiling on raw bytes (rejecting oversized frames with JSON-RPC error code `-32600`), and gracefully handle `BrokenPipeError` and `EOFError` without noisy stack traces.
- [ ] **5.2 Authenticated Server-Sent Events (SSE) Transport, Async Offloading, Streaming 10MB Guard, API Versioning & Graceful Drainage:** Implement FastAPI + Starlette SSE transport exposing `/health`, `/sse`, and `/messages` with `/v1/` versioned routes (`/v1/sse`, `/v1/messages`, `/v1/health`) alongside legacy root backward-compatibility aliases. Enforce dual-layer 10MB body size limit middleware (fast-path `Content-Length` check + streaming chunk byte counter for `Transfer-Encoding: chunked` returning HTTP 413 on breach). Offload all synchronous filelock acquisitions and SQLite writes to worker threads via `asyncio.to_thread()` to keep the Uvicorn event loop non-blocking. Enforce asynchronous `SIGTERM`/`SIGINT` graceful shutdown handlers that drain active `/sse` connection streams cleanly and execute `PRAGMA wal_checkpoint(TRUNCATE);` before container process termination. Enforce authentication across `Authorization: Bearer <key>`, `X-API-Key: <key>`, and query parameter `?apiKey=<key>`.
- [ ] **5.3 Constant-Time Timing-Safe Authentication:** Enforce `hmac.compare_digest()` for all API key validation. Enforce fail-closed behavior (HTTP 401 Unauthorized) in production mode (`ENVIRONMENT=production` or `REQUIRE_AUTH=true`) when `MCP_API_KEY` is unset.
- [ ] **5.4 Query Parameter API Key Redaction:** Attach `SensitiveQueryParamFilter` to `uvicorn.access` logger to redact `apiKey=[^&\s"]+` to `apiKey=***`, preventing secrets from leaking into server access logs.
- [ ] **5.5 Core MCP Tools Catalog & Protocol Version Negotiation:** Register core tools under JSON-RPC and implement protocol version negotiation during initialization (`protocolVersion: "2024-11-05"` in `initialize` response):
  - `analyze_infrastructure_waste`: Analyzes telemetry batches and flags waste.
  - `generate_remediation_plan`: Produces signed remediation plans.
  - `get_finops_audit_summary`: Returns cumulative ledger metrics.
- [ ] **5.6 MCP Prompts Support:** Register `prompts/list` and `prompts/get` exposing standard operational prompts:
  - `sentinel_waste_audit_runbook`: Step-by-step infrastructure audit runbook for agents.
  - `remediation_rollback_procedure`: Emergency rollback execution prompt.
- [ ] **5.7 MCP Resources Support:** Register `resources/list` and `resources/read` exposing live read-only URIs:
  - `smartrx://audit/ledger`: Real-time cumulative audit metrics in JSON format.
  - `smartrx://policies/risk-matrix`: Safety scoring rules and mandatory mitigation criteria.
  - `smartrx://config/instance-mappings`: Active AWS EC2 rightsizing catalog with pricing.
  - `smartrx://runbooks/waste-audit`: Markdown-formatted operational runbook.
- [ ] **5.8 Transport Unit Verification:** Add comprehensive transport tests in `tests/test_mcp.py` verifying `stdio` and `SSE` transports, 10MB payload size limits, and authentication.

---

### Phase 6: [UNIVERSAL CORE] Enterprise Observability & Persistent Ledger
*Goal: Provide production-grade telemetry tracing, metrics, and audit ledger persistence.*

- [ ] **6.1 In-Memory FinOps Ledger:** Implement thread-safe accumulation of total batches processed, resources audited, cumulative waste identified, and net savings realized.
- [ ] **6.2 JSONL Ledger Export & Storage Retention Pruning:** Implement structured JSONL export for long-term file-based audit reporting and SIEM ingestion with daily log rotation (`audit-YYYY-MM-DD.jsonl`), 50MB per-file ceiling, and automated retention pruning (`AUDIT_LOG_MAX_RETENTION_DAYS=30`, cumulative 500MB cap via `AUDIT_LOG_MAX_SIZE_MB=500`) to prevent disk exhaustion.
- [ ] **6.3 SQLite Persistent Ledger with MVCC Read-Bypass, Async Offloading, Schema Versioning & Checkpoints:** Implement SQLite persistence backend (`smartrx_ledger.db`) configured in WAL mode (`PRAGMA journal_mode=WAL;`) with `PRAGMA busy_timeout = 5000;` and explicit deterministic `try...finally` connection closing. Track `PRAGMA user_version` on startup and execute idempotent schema migrations in dedicated write transactions to prevent ledger corruption. Wrap WRITE mutations only with dynamically instantiated per-operation cross-platform `filelock.FileLock(..., timeout=FILELOCK_TIMEOUT_SEC)` (10.0s timeout via `FILELOCK_TIMEOUT_SEC`) offloaded to worker threads via `asyncio.to_thread()`, avoiding shared lock instances across threads. Bypasses `filelock` completely for all READ queries to preserve SQLite MVCC and eliminate writer starvation. Implement periodic passive checkpoints (`PRAGMA wal_checkpoint(PASSIVE);`) and truncate checkpoints (`PRAGMA wal_checkpoint(TRUNCATE);`) on shutdown or when `*.db-wal` exceeds 50MB.
- [ ] **6.4 OpenTelemetry Instrumentation:** Implement `src/smartrx_safety_agents/observability.py` providing `trace_span` context managers, latency tracking, and metric counters for all critical operations. Ensure OpenTelemetry `TracerProvider` and `MeterProvider` instances execute explicit `.shutdown()` in test fixture teardowns to prevent resource leaks.

---

### Phase 7: [UNIVERSAL CORE] Verification Suite & Enterprise CI/CD Hardening
*Goal: Enforce 100% automated verification, multi-version testing, and containerized deployment.*

- [ ] **7.1 Comprehensive Pytest Suite:** Develop an automated test suite achieving $\ge 90\%$ code coverage across schemas, heuristics, Gemini reasoning, fallback cascades, SSE authentication, CLI, security guardrails, MCP prompts/resources, and SQLite persistence.
- [ ] **7.2 Multi-Version GitHub Actions CI, Quality Gates, Secret & Supply-Chain Scanning:** Configure GitHub Actions workflow running matrix tests across Python 3.13 (primary blocking) and 3.14 (`continue-on-error: true` until upstream wheels stabilize) on `ubuntu-latest`, executing `ruff`, `mypy`, and quiet `pytest` coverage checks alongside `pip-audit` (dependency vulnerability scanning), pinned lockfile hash verification (`uv.lock` / `requirements.lock`), PEP 639-aware license compliance audit via `importlib.metadata` (allowing permissive `MIT`, `Apache-2.0`, `BSD`, `ISC`, `PSF-2.0`, `MPL-2.0`, `0BSD` and rejecting copyleft `GPL`/`AGPL`/`LGPL`/`SSPL`), scoped secret-scanning checks (excluding `.github/workflows/ci.yml` and honoring `# pragma: allowlist secret` in test fixtures), and mandatory live green GitHub Actions verification (`gh run list`) on every push and PR to gate each module before advancing. *(Note: During Phase 0 and Phase 1 before application source code is generated under `src/`, static validation syntax analysis must run exclusively on Markdown hyperlinked integrity, schema validation files, and configuration syntax, preventing empty directory tool errors. Remote GitHub Actions CI becomes mandatory for all subsequent tasks once Phase 7.2 is complete.)*
- [ ] **7.3 Code Coverage Reporting:** Enforce automated coverage gates via `pytest --cov=src/smartrx_safety_agents --cov-fail-under=90`.
- [ ] **7.4 Multi-Stage Non-Root Docker Packaging:** Author minimal, secure, non-root `Dockerfile` (< 75MB image size) and `docker-compose.yml` hosting the MCP SSE server with persistent SQLite volume and health probes.
- [ ] **7.5 Container Build & Live Health Probe Verification:** Build Docker image (`smartrx-safety-agents:latest`) and validate live HTTP 200 on `/health` probe within container runtime.

---

### Phase 8: [UNIVERSAL CORE / DEPLOYMENT PROFILE] Turnkey Standard Enterprise Cloud (AWS / Azure / Kubernetes) Production Deployment
*Goal: Package and blueprint deployment options for Standard Enterprise Cloud (AWS / Azure / Kubernetes) compute environments.*

- [ ] **8.1 Turnkey Compute Deployment Blueprint:** Author `deploy/smartrx-safety-agents-deploy.sh` and `docker-compose.prod.yml` configured for Standard Enterprise Cloud (AWS / Azure / Kubernetes), hard-capping container memory at 2048MB (`mem_limit: 2048m`).
- [ ] **8.2 Serverless Container Blueprint:** Author serverless container deployment configuration and Dockerfile for zero-server, pay-per-request execution.
- [ ] **8.3 Ephemeral Ledger Architecture Guide:** Author architectural guide detailing ephemeral storage considerations across serverless container runtimes and detailing persistent volume synchronization for ledger durability.
- [ ] **8.4 Turnkey Deployment Verification:** Verify Docker Compose local stack with volume persistence (`./data:/app/data`) and simulate deployment script execution.

---

### Phase 9: [UNIVERSAL CORE & DOMAIN HARDENING] Enterprise Security Hardening & Zero-Hallucination Guardrails
*Goal: Systematize all 22 Phase 9 hardening controls into permanent automated invariants.*

- [ ] **9.1 Authenticated SSE Transport, Streaming Chunk Counter & Async Offloading:** Dual-header and query parameter authentication with 401 Unauthorized rejection; dual-layer 10MB payload size limit middleware (fast-path header inspection + streaming chunk counter for chunked requests rejecting with HTTP 413); and `asyncio.to_thread()` offloading for all database writes.
- [ ] **9.2 Cryptographic HMAC-SHA256 Plan Signing:** Tamper-evident signing using server-side secret with `verify_plan_signature()` helper and strict canonical JSON serialization.
- [ ] **9.3 EC2 Memory Floor & Pricing Model Awareness:** Abort downsizing if memory utilization $> 65.0\%$; zero out savings on `reserved` or `savings_plan` commitments.
- [ ] **9.4 S3 Intelligent-Tiering Small-Object Guardrail:** Enforce average object size $\ge 128\text{ KB}$ threshold before recommending intelligent tiering.
- [ ] **9.5 Quarantine Pattern for Missing Mitigations & Invalid Enums:** Quarantine Risk $\ge 3$ actions lacking explicit mitigations or actions with invalid Enum types.
- [ ] **9.6 Gemini `responseSchema` Dereferencing & Token Cap:** Dereference `$defs`, strip unsupported fields via `ALLOWED_GEMINI_FIELDS`, and enforce `maxOutputTokens=8192` with high-thinking RAM guardrails.
- [ ] **9.7 Lambda Distributed Ledger Durability:** Document distributed synchronization options (Amazon EFS mount vs. S3 bucket sync).
- [ ] **9.8 Deterministic IAM & CLI Execution Overwriting:** Strip and discard LLM-generated execution payloads, replacing them with deterministic Python templates.
- [ ] **9.9 Real AWS Pricing Catalog Lookup & CatalogNotFoundError:** Real rate lookup in `config/instance_mappings.json` calculating `(curr_rate - tgt_rate) * 730.0`; raises `CatalogNotFoundError` on missing catalog and routes to Tertiary engine.
- [ ] **9.10 Constant-Time Authentication & Fail-Closed Enforcement:** `hmac.compare_digest()` matching with fail-closed production checks.
- [ ] **9.11 Verification Test Suite Expansion:** Dedicated unit tests for all security controls in `tests/test_phase9_hardening.py`.
- [ ] **9.12 Gemini `responseSchema` OpenAPI 3.0 `anyOf` Collapse:** Collapse Pydantic `{"anyOf": [{"type": "..."}, {"type": "null"}]}` into OpenAPI 3.0 `{"type": "...", "nullable": True}`.
- [ ] **9.13 Full Cryptographic Seal on `execution_payload`:** Include `execution_payload` in HMAC canonical payload hash.
- [ ] **9.14 Query Parameter API Key Plaintext Logging Advisory:** Publish SecOps guidance on URL query parameter exposure in access logs.
- [ ] **9.15 Pre-Commit Repository Hygiene:** Enforce zero un-ignored `.env` files and verify cleanliness via pre-commit hooks.
- [ ] **9.16 Live Gemini API Schema Pre-Flight Verification:** Validate `responseSchema` deserialization against live Google Protobuf parser.
- [ ] **9.17 Valid AWS ARNs & Scoped IAM Actions:** Enforce strictly formatted AWS ARNs and action-specific permissions; reject unknown resource types.
- [ ] **9.18 Full-Payload HMAC Signing, Anti-Replay TTL, Unicode Normalization & Canonical Serialization:** Full-payload canonical JSON serialization via `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)` with mandatory production secret enforcement, Unicode NFKC normalization (`unicodedata.normalize("NFKC", val).strip().casefold()`), and anti-replay verification (`issued_at`, `expires_at` TTL $\le 300\text{s}$ rejecting `current_time >= expires_at`, and unique `plan_id` nonce).
- [ ] **9.19 Allowlist Protobuf Schema Sanitizer:** Allowlist schema fields (`ALLOWED_GEMINI_FIELDS`), strip unsupported OpenAPI constraints, and exclude `execution_payload` from LLM schema egress.
- [ ] **9.20 Strip `<think>` Reasoning Blocks:** Remove `<think>` blocks and code fences from OpenRouter secondary model responses.
- [ ] **9.21 Query Parameter API Key Redaction in Access Logs:** Active uvicorn filter masking `?apiKey=***`.
- [ ] **9.22 Security Hardening Test Suite Integration:** Maintain 100% passing rate across all security regression tests.

---

### Phase 10: [UNIVERSAL CORE / DEPLOYMENT PROFILE] Standard Enterprise Cloud (AWS / Azure / Kubernetes) Production Release Documentation & Operational Sign-Off
*Goal: Formulate comprehensive operational manuals and SRE readiness reviews for Standard Enterprise Cloud (AWS / Azure / Kubernetes) deployment.*
*(Batching Guidance: Pure documentation and operational sign-off tasks 10.1–10.3 may be executed as a single cohesive batch followed by one link/schema verification pass).*

- [ ] **10.1 Production Deployment Guide:** Author `docs/Cloud_Deployment_Guide.md` providing end-to-end guidance for Standard Enterprise Cloud (AWS / Azure / Kubernetes), IAM least-privilege policies, secrets management, container pipelines, GitHub Actions OIDC CI/CD, and rollback runbooks.
- [ ] **10.2 SRE Production Readiness Review:** Author `Blueprint_Production_Readiness_Report.md` evaluating the repository across 8 operational pillars, requiring a 100/100 score and PASS verdict across security controls, AI reasoning safety, FinOps guardrails, and concurrency bounds.
- [ ] **10.3 Test Suite Integrity Validation:** Verify 100% of automated unit, integration, and security tests pass cleanly in under 15 seconds.

---

### Phase 11: [UNIVERSAL CORE] Dedicated Post-Deployment Monitoring & Observability
*Goal: Establish comprehensive post-deployment monitoring, alerting thresholds, and runbooks across the Four Golden Signals and AI governance.*
*(Batching Guidance: Observability manual, telemetry, and alerting tasks 11.1–11.5 may be executed as a single cohesive batch followed by one link/schema verification pass).*

- [ ] **11.1 Author Monitoring & Observability Manual:** Create `docs/MONITORING_AND_OBSERVABILITY.md` detailing operational monitoring standards.
- [ ] **11.2 Infrastructure & Container Health Monitoring:**
  - Define CPU utilization thresholds ($> 80\%$ warning, $> 95\%$ critical).
  - Define memory ceiling monitor hard-capped at 2048MB (OOM watch trigger at 1750MB / $88\%$; drop active reasoning round).
  - Define SQLite WAL file size monitoring (trigger checkpointing alert when `smartrx_ledger.db-wal > 50\text{ MB}`).
  - Define `audit_logs/` JSONL directory disk monitoring (trigger retention prune alert when `audit_logs/ > 500\text{ MB}` or file age $> 30\text{ days}$).
  - Monitor container restart loops and Docker health status via `/health` and `/ready` probes.
- [ ] **11.3 API & MCP Transport Telemetry:**
  - Track request throughput (requests/sec) and p50, p95, p99 latency targets ($< 500\text{ ms}$ for heuristics, $< 3500\text{ ms}$ for Gemini reasoning).
  - Track HTTP 4xx/5xx error rates with a strict error budget ($< 0.1\%$).
  - Track HTTP 413 Payload Too Large violations (> 10MB breach detection).
  - Monitor HTTP 401 authentication failure spikes ($> 5$ failures/minute) to detect brute-force attacks.
  - Track active concurrent Server-Sent Events (SSE) connections.
- [ ] **11.4 AI & Model Governance Telemetry:**
  - Track Gemini 3.8 Flash token consumption: prompt tokens, output tokens (capped at 8192 tokens/request), and `thinkingBudget` utilization.
  - Track `responseSchema` validation failure rate (alert if $> 0.5\%$).
  - Track Gemini HTTP 429/503 rate-limit events and retry backoff delays.
  - Monitor fallback cascade frequency: Primary Gemini $\to$ Secondary OpenRouter $\to$ Tertiary Deterministic Heuristics. Alert if fallback rate $> 2.0\%$.
  - Track high-risk action quarantine frequency (`quarantined=True` rate) and `CatalogNotFoundError` occurrences.
- [ ] **11.5 Security & Audit Integrity Telemetry:**
  - Monitor HMAC-SHA256 signature verification failures (alert immediately on any failure as a potential tampering incident).
  - Track prompt-injection sanitization triggers and suspicious tag occurrences.
  - Configure alert routing to AWS CloudWatch Alarms, OpenTelemetry OTLP collectors, and Slack/PagerDuty webhooks.

---

### Phase 12: [UNIVERSAL CORE] Cross-Model Adversarial Audit & Wrinkle Elimination
*Goal: Subject the complete codebase, schemas, and documentation to multi-model red-team review to eliminate subtle blind spots before release.*

- [ ] **12.1 Post-Build Multi-Model Audit Workflow:** Establish a structured post-build review protocol once all automated tests pass at 100%. Export core schemas, prompt templates, guardrail engines, and documentation.
- [ ] **12.2 Multi-Model Red-Team Review:** Prompt secondary frontier models (Claude 3.7/4 Sonnet, OpenAI o3/GPT-4o, and Qwen 2.5 Coder 32B) with a structured red-team review prompt:
  - Identify edge-case ambiguities in heuristic thresholds.
  - Uncover race conditions in SQLite WAL file locking or SSE connection pooling.
  - Probe for silent failure modes in fallback cascades or error handlers.
  - Detect FinOps pricing or commitment traps (e.g., unintended data egress or API request fees).
  - Flag any documentation drift between `docs/TRD.md`, `README.md`, and code implementations.
- [ ] **12.3 Finding-to-Regression Test Loop:** For every confirmed finding or vulnerability identified during the adversarial audit:
  - Formulate a specific reproduction test case in `tests/`.
  - Implement the code or schema fix to resolve the edge case.
  - Verify that the test passes and add it permanently to the regression test suite.
- [ ] **12.4 Final Release Sign-Off:** Execute the complete test suite, verify zero open vulnerabilities, and sign off on the production release.
- [ ] **12.5 Post-Build Cross-Document Synchronization & Release Tagging:** Execute full synchronization of `README.md` (with clear document role descriptions and verified relative links), `PROJECT_MAP.md`, `AUDIT_REMEDIATION_LOG.md`, `docs/ARCHITECTURE.md`, `docs/TRD.md`, `docs/PRD.md`, `docs/URD.md`, `modular_prompt.md`, and `Blueprint_*.md` against actual shipped code, schemas, and test metrics—with zero dead links and zero "TBD" / "Planned" placeholders—before tagging `v1.0.0`.

---

## 3. Verification Commands Quick Reference

```bash
# 1. Install dependencies in editable mode
pip install -e ".[dev]"

# 2. Run full automated test suite with coverage
ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && pytest -q --tb=short --cov=src/smartrx_safety_agents --cov-report=term:skip-covered --cov-fail-under=90

# 3. Code quality and type safety checks
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/

# 4. Test CLI commands with dry-run
smartrx-safety-agents --help
smartrx-safety-agents audit --dry-run
smartrx-safety-agents audit --telemetry-file samples/telemetry_batch.json

# 5. Launch MCP standard I/O transport server
smartrx-safety-agents run-mcp --transport stdio

# 6. Launch MCP authenticated SSE transport server
smartrx-safety-agents run-mcp --transport sse --host 127.0.0.1 --port 8080

# 7. Build and test local Docker container
docker compose build
docker compose up -d
curl -f http://localhost:8080/health
docker compose down
```
