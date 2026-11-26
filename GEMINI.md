# ==============================================================================
# GEMINI.md — Universal Enterprise Master Handbook
# ==============================================================================
# This document defines the non-negotiable engineering, security, architectural,
# testing, and operational standards for autonomous AI coding agents working in
# this repository. It is universally reusable across enterprise projects by
# customizing the [PROJECT_CONFIGURATION] block below.
# ==============================================================================

# ------------------------------------------------------------------------------
# [PROJECT_CONFIGURATION]
# ------------------------------------------------------------------------------
# Project Identifier:        smartrx-safety-agents
# Target Package Name:       smartrx_safety_agents
# Root Package Path:         src/smartrx_safety_agents
# CLI Console Entrypoint:    smartrx-safety-agents
# Primary LLM Engine:        Loaded from GEMINI_MODEL_NAME (default: gemini-3.8-flash-high, thinkingConfig.thinkingBudget=2048)
# Secondary Fallback Model:  openrouter/qwen-2.5-coder-32b-instruct
# Tertiary Engine:           Deterministic SRE Heuristics (100% offline uptime)
# MCP Protocol URI Prefix:   smartrx://
# Runtime Environment:       Python 3.13+ (Container: python:3.13-slim)
# HTTP API Gateway:          FastAPI + Starlette SSE (Uvicorn non-blocking)
# Default Service Port:      8080
# Max Memory Ceiling:        2048MB (Standard Enterprise Cloud (AWS / Azure / Kubernetes))
# Max Payload Size Ceiling:  10MB (10485760 bytes; HTTP 413 on breach)
# Max Output Token Cap:      8192 tokens (per request ceiling)
# Audit Ledger Location:     data/smartrx_ledger.db (SQLite WAL mode)
# JSONL Ledger Log Dir:      audit_logs/
# Webhook / Callback Secret: SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET
# Payload Signing Secret:    PLAN_SIGNING_SECRET
# MCP Server API Key:        MCP_API_KEY
# ------------------------------------------------------------------------------

> **Template Cloning & Universal Domain Adaptability Note:**
> This repository provides a dual-layer architectural specification:
> 1. **Universal Core Invariants (`[UNIVERSAL CORE]`):** Sections 3.3–3.7, 3.9–3.13, and Phases 5–12 define universal enterprise standards (cryptographic HMAC signing, anti-replay nonces, timing-safe auth, 10MB streaming body limits, SQLite WAL concurrency, UTF-8 I/O, LLM token cost circuit breakers, and OpenAPI 3.0 schema sanitization) that are 100% reusable across any domain (healthcare, finance, security, legal, or data platforms) and AI architecture (multi-agent graphs via LangGraph/CrewAI/AutoGen, RAG pipelines via LangChain/LlamaIndex/vector stores, MCP servers, or direct typed SDKs) and must remain intact.
> 2. **Domain Reference Implementations (`[DOMAIN REFERENCE]`):** Sections 3.1, 3.2, 3.8, and Phases 2–4 use Cloud Infrastructure & FinOps as a concrete reference implementation. When cloning this blueprint for non-cloud domains, engineers customize the domain configuration block, canonical `ActionType` Literal Enum, deterministic execution templates, and heuristic rules while preserving the underlying risk-scoring, quarantine, and execution-overwriting patterns.

---

## 1. Role & Engineering Standard
You are acting as a **Principal AI Systems Architect, Lead SRE, and Staff Security Engineer**.
- **No Incomplete Implementations:** Never generate placeholder code, `TODO` stubs, mock passes, or truncated functions. Implement complete, fully functional, production-ready logic.
- **Strict Industry Best Practices:** Build every module adhering to SOLID design principles, 12-Factor App methodology, OWASP Top 10 security standards, and PEP 8 / PEP 517/621 conventions.
- **Zero-Hallucination Mandate (Code & Documentation):** Never fabricate APIs, library methods, configuration keys, CLI flags, file paths, or architectural claims. Every reference in Python source files or Markdown documentation (`docs/*.md`, `README.md`) must be verified against actual repository files and installed package versions. If an external specification or API contract is uncertain, halt and verify before writing.
  - **Release Cross-Document Sync Gate:** Before final release sign-off, comprehensively audit every `.md` file (`README.md` including clear document role descriptions, `PROJECT_MAP.md`, `docs/ARCHITECTURE.md`, `docs/TRD.md`, `docs/PRD.md`, `docs/URD.md`, `modular_prompt.md`, and `Blueprint_*.md`) against actual shipped code, CLI flags, schemas, and verified test metrics—with zero dead links and zero `"TBD"` / `"Planned"` placeholders.
- **Strict Type Hints:** Enforce explicit type annotations (`typing`, `Literal`, `Annotated`, `Callable`, `TypeVar`) across all functions, classes, and variables compatible with Python 3.13+.
- **Test-Driven Development (TDD):** Author or update `pytest` verification tests before or alongside every code change. Code is only considered complete when all tests pass cleanly.
- **Anti-Test-Cheating & Verifiable Proof Invariant:**
  - **Zero Test Tampering:** Never delete, comment out, weaken assertions, lower coverage gates, or add `@pytest.mark.skip` / `xfail` to bypass a failing test.
  - **No Self-Mocking:** Mocks/stubs are permitted only for external network boundaries (e.g., Gemini/OpenRouter HTTP calls); mocking the internal function or guardrail under test is strictly forbidden.
  - **Verbatim Proof Required:** Never fabricate or summarize test results. Every task completion report must include the exact verbatim terminal output line from `pytest` showing passed/failed test counts and code coverage percentage.
- **Cross-Platform UTF-8 File I/O Invariant:** All file reading, writing, logging, schema loading, and subprocess text decoding must explicitly specify `encoding="utf-8"` (e.g., `Path.read_text(encoding="utf-8")`, `Path.write_text(..., encoding="utf-8")`, `open(..., encoding="utf-8")`). Omitting explicit encoding or relying on OS platform defaults (such as Windows `cp1252`) is strictly forbidden to guarantee complete cross-platform portability without `UnicodeDecodeError` or `UnicodeEncodeError` across Windows, macOS, Linux, and Docker environments.

---

## 2. Technology Stack & AI Orchestration Standard
- **Runtime:** CPython 3.13+ managed via `uv` or virtualenv (`.venv`) and containerized via `python:3.13-slim` Docker image.
  - **Deterministic Lockfile Rule:** Whenever CI enforces supply-chain lockfile verification, Phase 1 must generate and commit `uv.lock` or `requirements.lock` alongside editable installation to guarantee reproducible builds.
  - **Windows Sandbox Loopback (`WinError 10013`) Note:** Windows sandboxed runners and environments must allow `127.0.0.1` loopback socket binding for Python `asyncio` event-loop initialization and local server probes.
- **AI Orchestration Policy:** Permits any multi-agent, RAG, or MCP orchestration framework (including LangChain, LangGraph, LlamaIndex, CrewAI, AutoGen, Google ADK, or direct typed SDKs) provided that all inter-agent messages, retrieval chunks, state schemas, and data contracts strictly enforce Pydantic v2 validation (extra='forbid', frozen=True) and all external actions/tools are encapsulated inside deterministic GuardrailEngine wrappers. Supports multi-agent orchestration (LangGraph, CrewAI, AutoGen), RAG pipelines (LangChain, LlamaIndex, pgvector, FAISS, Chroma), Model Context Protocol (MCP) servers, or direct typed SDKs. All data exchanges must strictly adhere to Pydantic v2 data contracts.
- **Validation & Data Contracts:** `pydantic` v2 (`ConfigDict(extra="forbid", frozen=True)` for all data contracts, schemas, and inter-agent messages).
- **Primary AI Reasoning Engine:** Google Gemini (primary model ID dynamically loaded from `GEMINI_MODEL_NAME`, default `gemini-3.8-flash-high`, never hardcoded in client logic) configured with dynamic `thinkingConfig.thinkingBudget` (default: 2048) and native constrained decoding via `generationConfig.responseSchema`. Capped at a maximum output token ceiling of **8192 tokens** per request (`maxOutputTokens=8192`).
- **RAM Protection Guardrail:** If active context graphs and reasoning buffers risk breaching the 2048MB RAM ceiling, the engine must proactively drop the active reasoning round and fall back to Secondary or Tertiary engines.
- **API Gateway & Transports:** `fastapi` + `uvicorn` (async non-blocking endpoints, line-delimited `stdio` JSON-RPC 2.0, and authenticated Server-Sent Events `/sse`). Enforces a strict **10MB incoming body-size ceiling** returning HTTP 413 Payload Too Large / JSON-RPC error on breach.
- **Persistence & Mutex Locking:** SQLite in WAL mode (`PRAGMA journal_mode=WAL;`) with cross-platform write-only file locking (`filelock.FileLock`) preserving MVCC for concurrent non-blocking reads.
- **Observability:** OpenTelemetry API/SDK (`opentelemetry-api`, `opentelemetry-sdk`) with structured JSON logging and access-log secret filters.
- **Code Quality:** `ruff` (linting and formatting), `mypy` (strict static typing), `pytest` + `pytest-asyncio` + `pytest-cov` ($\ge 90\%$ coverage gate) with mandatory **`pytest-timeout`** (`timeout = 15`, `timeout_method = "thread"`) configured in `pyproject.toml` from Phase 1.1 so no async generator, SQLite lock, or background daemon thread can ever hang CI/CD indefinitely.

---

## 3. Non-Negotiable Architectural & Security Invariants

### 1. [DOMAIN REFERENCE: CLOUD FINOPS] Calibrated Safety Enforcement, Strict Action Enum & Quarantine Pattern
Every action proposed by the system must be scored on a 1–5 Safety Risk scale and strictly validated against the canonical `ActionType` Enum:
`ActionType = Literal["TERMINATE_INSTANCE", "STOP_INSTANCE", "MODIFY_INSTANCE_TYPE", "MODIFY_S3_LIFECYCLE", "DELETE_EBS_VOLUME", "RELEASE_EIP", "ENABLE_INTELLIGENT_TIERING"]`
- **Strict Enum Allowlist:** If the LLM generates a target action outside this valid Enum allowlist, the `GuardrailEngine` must immediately reject the payload fail-closed and quarantine the action (`quarantined=True`, `quarantine_reason="INVALID_ACTION_ENUM_TYPE"`).
- **Quarantine on Missing Mitigation:** Any action with Safety Risk Score $\ge 3$ lacking explicit, validated automated mitigations and deterministic rollback procedures must be quarantined (`quarantined=True`, `quarantine_reason="MISSING_MANDATORY_ROLLBACK"`). Never silently inject generic templates or execute unmitigated high-risk actions.

### 2. [DOMAIN REFERENCE: CLOUD FINOPS] Deterministic Execution Overwriting (Zero-Hallucination Guardrail)
To eliminate AI hallucination vulnerabilities in cloud infrastructure operations, LLMs must never synthesize executable commands directly. The `GuardrailEngine` must unconditionally overwrite `execution_payload["iam_policy"]`, `execution_payload["aws_cli"]`, and `execution_payload["rollback"]` using deterministic Python functions mapped strictly to the internal `ActionType` matrix:
- IAM policies must validate standard AWS ARNs (`arn:aws:ec2:*:*:instance/{res_id}`, `arn:aws:s3:::{res_id}`, etc.).
- Wildcard permissions (`"Action": "*"`, `"Resource": "*"`) are strictly forbidden.
- Unknown resource types, unallowlisted actions, or invalid identifiers must raise an immediate `ValueError` and trigger fail-closed quarantine.

### 3. [UNIVERSAL CORE] Full-Payload Cryptographic HMAC-SHA256 Signing, Anti-Replay & Canonical Serialization
All remediation plans and webhook payloads must be cryptographically sealed before persistence or transmission to guarantee absolute tamper-evidence and replay immunity:
- **Anti-Replay Invariant:** Every signed remediation plan must contain an ISO-8601 UTC timestamp `issued_at`, an `expires_at` timestamp enforcing a strict TTL of $\le 300\text{ seconds}$ (5 minutes), and a unique `plan_id` (monotonic nonce). The verification engine must reject expired plans (`current_time >= expires_at`) or replayed plan IDs with HTTP 400 / fail-closed.
- **Canonical Serialization Invariant:** The system must compute a SHA-256 `plan_digest` and an HMAC-SHA256 `plan_signature` over the strict canonical JSON representation:
  `json.dumps(plan.model_dump(mode="json", exclude={"plan_digest", "plan_signature"}), sort_keys=True, separators=(',', ':'), ensure_ascii=False)`
- **Serialization Prohibition:** Generic, non-sorted, or non-deterministic serialization methods (such as default `json.dumps()` without fixed separators, or unconstrained Pydantic serialization) are strictly forbidden to prevent cryptographic signature mismatch.
- **Constant-Time Verification:** Verification of inbound signatures must exclusively utilize constant-time comparison via `hmac.compare_digest()` to prevent side-channel timing attacks.
- **Fail-Closed Secret Enforcement:** If `ENVIRONMENT=production` and `PLAN_SIGNING_SECRET` or `SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET` is unconfigured, empty, or set to a default value, the application must immediately fail closed with a `RuntimeError` during startup.
- **Request Idempotency & Deduplication Invariant:** Every remediation request and state mutation must accept and validate a unique monotonic `plan_id` / `idempotency_key`. The ledger and guardrail execution layers must check for duplicate keys; any replayed or identical request within the TTL window must return the existing cached signed plan without re-executing state mutations or generating duplicate ledger events, guaranteeing strict end-to-end idempotency.

### 4. [UNIVERSAL CORE] Timing-Safe Multi-Transport Authentication & Streaming Body-Size Defense
All incoming requests over HTTP/SSE must authenticate against `MCP_API_KEY` via `Authorization: Bearer <key>`, `X-API-Key: <key>`, or `?apiKey=<key>`:
- Token comparison must strictly utilize `hmac.compare_digest()`. If `ENVIRONMENT=production` or `REQUIRE_AUTH=true` and `MCP_API_KEY` is not configured, the server must fail closed with HTTP 401 Unauthorized.
- Server access logs must register a `SensitiveQueryParamFilter` to sanitize `?apiKey=...` to `?apiKey=***`.
- **Dual-Layer 10MB Payload Size Defense:** To isolate the system from denial-of-service memory exploitation vectors within the 2048MB RAM ceiling, all FastAPI, SSE, and JSON-RPC transports must enforce a strict incoming payload upper body cap of 10MB (10,485,760 bytes):
  1. *Fast-Path Header Inspection:* If `Content-Length` is present and $> 10,485,760$ bytes, reject immediately with HTTP 413 Payload Too Large / JSON-RPC error code `-32600`.
  2. *Streaming Chunk Byte Counter:* For `Transfer-Encoding: chunked` or streaming requests lacking a `Content-Length` header, wrap the incoming stream in a streaming byte counter that terminates the connection and raises HTTP 413 the moment cumulative bytes exceed 10MB, before heap buffering.

### 5. [UNIVERSAL CORE] Dual-Path Resilience, High-Thinking Safeguards & Total Exception Cascade
The system must guarantee 100% evaluation uptime through a tiered fallback cascade:
1. **Primary:** Gemini 3.8 Flash High with exponential backoff and jitter (3 attempts on HTTP 429/503), dynamic `thinkingBudget=2048`, and output hard-capped at 8192 tokens per request (`maxOutputTokens=8192`).
2. **Secondary:** OpenRouter/OpenAI-compatible client (e.g., Qwen 2.5 Coder 32B), automatically stripping `<think>...</think>` internal reasoning tags and markdown code blocks before JSON decoding.
3. **Tertiary:** Deterministic SRE Heuristics engine executing offline rules (guaranteeing zero-cost GitHub CI/CD execution and 100% uptime during total AI API outages).
- **Total Exception Cascade Guarantee:** Primary reasoning must be wrapped in an exhaustive exception handler. **Any** exception during Primary evaluation—including `httpx.TimeoutException`, `httpx.HTTPStatusError`, `json.JSONDecodeError`, `pydantic.ValidationError`, Protobuf parsing errors, empty/null model outputs, or RAM ceiling watchdog triggers—must be recorded in telemetry and immediately cascade to Secondary. Any failure in Secondary must cascade cleanly to Tertiary, with zero unhandled crashes.
- **RAM Ceiling Watchdog:** If the structural evaluation context graph combined with token buffering runs a calculated hazard of breaching 1750MB (85–88% of the 2048MB RAM ceiling), the engine must proactively cancel the generation turn and immediately drop down to the secondary or tertiary engine paths.
- **Deterministic Static Data Catalog Fallback:** If `config/instance_mappings.json` is missing, corrupted, unreadable, or fails schema validation, the system must immediately raise a custom `CatalogNotFoundError` and automatically route execution to the Tertiary Deterministic Heuristics engine. Quiet fallbacks (such as defaulting to $0.0 savings or emitting an unhandled warning) are strictly forbidden.

### 6. [UNIVERSAL CORE] SQLite WAL Lock Isolation, Async Thread Offloading & Checkpoint Lifecycle
All SQLite database and JSONL ledger operations must enforce strict concurrency isolation:
- **MVCC Isolation Layer:** Cross-platform `filelock.FileLock` with a default 10.0-second timeout (configurable via `FILELOCK_TIMEOUT_SEC` in `config.py`) must wrap **WRITE mutations only** (`INSERT`, `UPDATE`, `DELETE`, `PRAGMA wal_checkpoint`). Dynamically instantiate `filelock.FileLock(..., timeout=FILELOCK_TIMEOUT_SEC)` inside each write method (per-operation instantiation) rather than sharing a single `FileLock` instance across `asyncio.to_thread()` worker threads, preventing Windows file-descriptor conflicts and nested lock deadlocks. All **READ transactions** (`SELECT`, ledger queries) must completely bypass `filelock` and rely exclusively on SQLite's native Multi-Version Concurrency Control (MVCC) in WAL mode (`PRAGMA journal_mode=WAL;`), eliminating writer starvation and WAL bloat. Windows-only locks (`msvcrt`) are strictly forbidden.
- **Async Event-Loop Offloading:** Synchronous `filelock.FileLock` write mutations and blocking SQLite disk I/O executed inside asynchronous FastAPI routes must be offloaded to worker threads via `asyncio.to_thread()` (or `anyio.to_thread.run_sync()`). This guarantees that concurrent `/sse` client event streams and HTTP routing loops never experience event-loop starvation.
- **Busy Timeout, WAL Checkpoint & Explicit Resource Teardown Lifecycle:** All SQLite connections must set `PRAGMA busy_timeout = 5000;` (5.0-second wait on transient locks before raising OperationalError) and must close deterministically inside `try...finally` blocks. In test fixtures, OpenTelemetry `TracerProvider` and `MeterProvider` instances must explicitly invoke `.shutdown()` during teardown to avoid resource leaks. To definitively prevent `*.db-wal` from expanding past the 50MB runtime ceiling, background workers must execute periodic passive checkpoints (`PRAGMA wal_checkpoint(PASSIVE);`), and enforce truncate checkpoints (`PRAGMA wal_checkpoint(TRUNCATE);`) upon graceful application shutdown or whenever WAL file size exceeds 50MB.
- **SQLite Schema Versioning & Idempotent Migrations:** On application startup, the database initialization layer must query and track `PRAGMA user_version`. Schema mutations must be executed strictly via idempotent migration scripts incrementing `user_version` within a dedicated write transaction. Unversioned, ad-hoc table alterations or raw `CREATE TABLE IF NOT EXISTS` statements that bypass migration version checks are strictly forbidden, guaranteeing existing ledgers are never corrupted across deployments.

### 7. [UNIVERSAL CORE] Prompt Injection Defense & Path Traversal Isolation
- All untrusted input data, external metrics, and freeform resource tags passed to LLM reasoning prompts must be sanitized and enclosed inside `<untrusted_telemetry_data>` XML-style delimiters.
- Prompt file loaders must strictly enforce `Path.is_relative_to(prompts_dir)` to prevent path traversal attacks.

### 8. [DOMAIN REFERENCE: CLOUD FINOPS] Reference Heuristic Guardrails & Safety Floors
In multi-round evaluation or deliberation loops, stakeholder votes and state maps must be reset upon round increment. Heuristic engines must enforce hard domain safeguards:
- **Unicode NFKC Normalization:** All inbound tag keys, tag values, and principal/resource identifiers must pass through `unicodedata.normalize("NFKC", val).strip().casefold()` prior to allowlist, risk-matrix, or protected-identity comparisons to block fullwidth homoglyph, zero-width, and non-breaking space (`\u00a0`) bypasses.
- **EC2 Memory Floor:** Abort downsizing if `memory_utilization_avg_pct > 65.0\%` to protect against OOM crashes.
- **Commitment Awareness:** Zero out projected savings if resources are covered by `reserved` or `savings_plan` commitments.
- **S3 Object Size Threshold:** Require average object size $\ge 128\text{ KB}$ before recommending `INTELLIGENT_TIERING` to avoid per-object monitoring fee penalties.

### 9. [UNIVERSAL CORE] OpenAPI 3.0 Strict Schema Sanitization (Allowlist Protobuf Compliance)
When binding Pydantic schemas to Gemini `responseSchema`:
- Dereference and inline all `$defs` and `$ref` pointers.
- Collapse Pydantic v2 `{"anyOf": [{"type": "..."}, {"type": "null"}]}` structures into OpenAPI 3.0 `{"type": "...", "nullable": True}`.
- Strip all unsupported fields (`$schema`, `additionalProperties`, `minimum`, `maximum`) using a strict field allowlist (`ALLOWED_GEMINI_FIELDS`) to prevent Google Protobuf C++ parser deserialization errors:
  `ALLOWED_GEMINI_FIELDS = {"type", "description", "nullable", "enum", "properties", "items", "required", "title"}`
- **Object Schema Preservations:** If the schema contains variable metadata mapping dictionaries (e.g. `dict[str, Any]` fields), the extraction code must re-inject an explicit `{'type': 'object'}` component token flag right after cleaning out forbidden properties variables to ensure the Gemini internal Protobuf C++ parser recognizes the dynamic scope appropriately without throwing validation exceptions.
- Explicitly exclude `execution_payload` (and any untyped `dict[str, Any]` fields) from the LLM `responseSchema` before sending to Gemini; these must be populated deterministically by `GuardrailEngine` after LLM inference.

### 10. [UNIVERSAL CORE] Cloud-Native Volume Portability, 2048MB RAM Ceiling & Audit Log Quotas
- All storage paths (`DB_PATH`, `AUDIT_LOG_DIR`) must be configurable via environment variables.
- In containerized environments, the entire process must execute as a non-root user (`sentinel:sentinel`, UID 10001) and stay strictly within a **2048MB RAM ceiling** (suitable for Standard Enterprise Cloud (AWS / Azure / Kubernetes)).
- **Audit Log Rotation & Storage Retention Quota:** To prevent disk exhaustion on Standard Enterprise Cloud (AWS / Azure / Kubernetes) storage (e.g. 8GB–20GB root volumes), `audit_logs/` JSONL files must enforce daily rotation (`audit-YYYY-MM-DD.jsonl`), a 50MB per-file ceiling, and automated retention pruning (`AUDIT_LOG_MAX_RETENTION_DAYS=30`, cumulative storage cap of 500MB via `AUDIT_LOG_MAX_SIZE_MB=500`).

### 11. [UNIVERSAL CORE] Centralized Modular Prompt Registry (`modular_prompt.md`)
All modular system prompts, domain prompt templates, and agent instructions created or modified during development must be saved, indexed, and maintained inside `modular_prompt.md` at the repository root (synchronized with any runtime prompt modules under `prompts/modules/`). Never scatter undocumented prompts inline inside Python source files.

### 12. [UNIVERSAL CORE] LLM Session Token & API Cost Circuit Breaker
To prevent runaway autonomous agent loops from exhausting API quotas or racking up unexpected cloud bills, the reasoning client must track cumulative prompt tokens, completion tokens, and estimated cost across turns:
- **Session Budget Cap:** If cumulative session tokens exceed `MAX_SESSION_TOKEN_BUDGET` (default: 500,000 tokens) or cumulative spend breaches `DAILY_API_COST_LIMIT_USD` (default: $10.00), the client must immediately trip a circuit breaker.
- **Fail-Safe Fallback:** Upon tripping the cost/token circuit breaker, the engine must immediately halt active frontier LLM calls, log an alert, and fall back to the Tertiary Deterministic Heuristics engine (guaranteeing 100% offline uptime at zero additional API cost).

### 13. [UNIVERSAL CORE] Context Compaction & Telemetry Ingestion Hygiene (Zero Context Dumping)
Dumping unindexed, raw multi-megabyte log files, large CSVs, or whole database dumps directly into reasoning prompts is strictly forbidden:
- **Bounded Ingestion:** All tool-assisted file reads and metrics telemetry must enforce strict upper limits (max 800 lines or 46KB per tool invocation).
- **Compacted Context Graphs:** Telemetry batches must be aggregated, deduplicated, and compacted into structured JSON summaries consuming $< 4,000$ tokens per 50-resource batch prior to LLM reasoning ingestion. Raw, unsummarized payloads that dilute reasoning density or approach context limits must be rejected fail-closed.

---

## 4. Dual-Transport Model Context Protocol (MCP) Standards

### Standard I/O Transport (`stdio`)
- Line-delimited JSON-RPC 2.0 loop reading strictly from `sys.stdin` and writing responses to `sys.stdout`.
- **UTF-8 Multibyte Boundary & Payload Cap:** Accumulate raw bytes to newline boundaries before decoding to prevent UTF-8 multibyte codepoint splitting (`UnicodeDecodeError`). Enforce the 10MB payload size limit on accumulated raw bytes; reject oversized frames with JSON-RPC error code `-32600` (Invalid Request / Payload Too Large).
- **BrokenPipe & EOF Disconnection Defense:** Catch `BrokenPipeError` and `EOFError` gracefully when writing to `sys.stdout` or reading from `sys.stdin`, terminating the loop cleanly without polluting `sys.stderr` with unhandled exception traces. All operational logging, diagnostics, and debugging outputs must be explicitly redirected to `sys.stderr`. Polluting `sys.stdout` with non-JSON text is strictly forbidden.

### Server-Sent Events Transport (`SSE`)
- FastAPI application serving SSE streaming over `/sse` and message handling over `/messages`.
- Enforces middleware limiting request bodies to 10MB (fast-path header inspection + streaming chunk byte counter), raising HTTP 413 Payload Too Large on breach.
- Provide `/health` and `/ready` endpoints returning HTTP 200 with runtime diagnostics (memory consumption, database connectivity, model provider status).
- Protect `/sse` and `/messages` with timing-safe authentication.
- **Graceful Shutdown & Drainage Lifecycle:** Server must register asynchronous signal handlers for `SIGTERM` and `SIGINT` to gracefully drain active `/sse` streams without dropping client connections abruptly, close accepting new incoming requests, and execute `PRAGMA wal_checkpoint(TRUNCATE);` before container process termination, guaranteeing zero WAL file corruption or dangling lock state on restart.
- **API Versioning & Protocol Negotiation:** All HTTP/SSE endpoints must support versioned routing prefixed with `/v1/` (`/v1/sse`, `/v1/messages`, `/v1/health`) alongside root backward-compatibility aliases (`/sse`, `/messages`, `/health`). For MCP transports (`stdio` and `SSE`), the server must implement protocol version negotiation during initialization (`initialize` method responding with supported protocol versions, e.g. `2024-11-05`), rejecting incompatible protocol major versions with JSON-RPC error code `-32602`.

### MCP Resources & Prompts Namespace
- All resource URIs must use the project prefix: `smartrx://...` (e.g., `smartrx://audit/ledger`, `smartrx://policies/risk-matrix`, `smartrx://config/instance-mappings`, `smartrx://runbooks/waste-audit`).
- MCP prompts must be registered with typed argument schemas and descriptive runbooks.

---

## 5. Post-Deployment Monitoring & Observability Standard

Every deployment must expose and track telemetry according to the **Four Golden Signals & AI Governance**:

| Telemetry Pillar | Metric / Probe | Alert Trigger / Budget | Action / Runbook |
|---|---|---|---|
| **Latency** | p50, p95, p99 request duration | p99 $> 3500\text{ ms}$ (AI), $> 500\text{ ms}$ (Rules) | Scale compute / inspect backoff |
| **Traffic** | Requests per second, active SSE streams | Sudden $10\times$ surge | Rate limit enforcement |
| **Errors** | HTTP 4xx / 5xx error budget | $> 0.1\%$ error rate over 5 min | Inspect error logs / failover |
| **Saturation** | Memory ceiling (2048MB watch) | $> 1750\text{ MB}$ ($85\text{--}88\%$ of 2048MB) | Trigger memory GC / drop active round |
| **Payload Size** | Incoming request body byte count | Request $> 10\text{ MB}$ | Reject with HTTP 413 / error |
| **Ledger Health** | SQLite WAL file size | `*.db-wal > 50\text{ MB}` | Run `PRAGMA wal_checkpoint(TRUNCATE)` |
| **Disk Storage** | `audit_logs/` directory disk usage | `audit_logs/ > 500\text{ MB}` or file age $> 30\text{ d}$ | Trigger automated log rotation & retention prune |
| **AI Tokens** | Gemini thinkingBudget vs. output | Output $> 8192$ tokens per request | Enforce token ceiling / inspect loop |
| **Cascade Rate** | Primary $\to$ Secondary $\to$ Tertiary | Fallback $> 2.0\%$ of requests | Check Gemini API quotas / status |
| **Security** | 401 Auth failures / HMAC failures | $> 5$ auth fails/min or $> 0$ HMAC fails | Block IP / trigger security incident |

---

## 6. Cross-Model Adversarial Audit Protocol

Before any code changes are signed off for production, the repository must undergo a structured multi-model red-team review:

1. **Prerequisite:** 100% of automated unit, integration, and security tests must pass cleanly.
2. **Adversarial Red-Team Prompting:** Export core schemas, prompt templates, guardrail modules, and documentation, and submit them to secondary frontier models (Claude 3.7/4 Sonnet, OpenAI o3/GPT-4o, Qwen 2.5 Coder 32B) with the following audit mandate:
   > *"Act as an Adversarial Principal Security Engineer and Lead SRE. Review these schemas, heuristics, and execution paths. Identify subtle race conditions, silent failure modes, prompt injection bypasses, edge-case arithmetic bugs, or FinOps pricing traps."*
3. **Finding Conversion:** Every verified finding must be converted into an automated regression test in `tests/` before deploying the fix. No finding may be closed through documentation changes alone.

---

## 7. Document Hierarchy (Source of Truth)

When resolving requirements, architectural decisions, or ambiguity, adhere to this strict order of precedence:

1. `GEMINI.md` (Universal Master Handbook: Invariants, security rules, and coding standards)
2. `Enterprise_Blueprint.md` (Master engineering backlog and phase-by-phase roadmap)
3. Blueprint Audit & Debug Logs (`README.md`, `Blueprint_Debug_Log.md`, `AUDIT_REMEDIATION_LOG.md`)
4. `modular_prompt.md` (Centralized modular prompt registry and PromptOps catalog)
5. `docs/TRD.md` (Technical Requirements: exact schemas, state channels, cryptographic formulas, MCP contracts)
6. `docs/PRD.md` (Product Requirements: functional capabilities, metrics, NFRs)
7. `docs/URD.md` (User Requirements: personas, workflows, use cases)
8. `docs/ARCHITECTURE.md` (C4 diagrams, system boundaries, sequence flows)
9. `docs/MONITORING_AND_OBSERVABILITY.md` (Operational telemetry, metrics, and alerting runbooks)
10. `docs/Cloud_Deployment_Guide.md` (Turnkey deployment runbooks and infrastructure specs)

---

## 8. Token-Efficient Phase-Batched Execution, Anti-Context-Rot Handoff & CI/CD Gate Protocol
- **Cohesive Phase-Batched Execution:** Execute **1 coherent phase or 3–5 tightly coupled tasks per turn** followed by a single quiet verification run (while preserving strict Phase/Task ID traceability). Never batch unrelated phases or skip ahead haphazardly.
- **Traceability:** Before editing, explicitly state which Phase and Task IDs from `Enterprise_Blueprint.md` (e.g., `Phase 2.1`–`2.3`, `Phase 4.1`–`4.3`) the turn satisfies.
- **Targeted Line-Range Reads & `PROJECT_MAP.md` Index Mandate:** Maintain a compact (< 60-line) `PROJECT_MAP.md` at the repository root mapping every file path to its primary classes/functions. AI agents must read only the active Phase section (via targeted line-range reads) plus the 2–4 target files relevant to the active turn rather than repeatedly re-reading entire multi-thousand-line specification files every turn.
- **CI/CD Optimization Clause:** For all initial tasks spanning Phases 0 through Phase 6, executing clean local validation sweeps across ruff, mypy, and pytest entirely satisfies the active build validation pipeline. Remote distributed GitHub Actions workflows are only fully operational and mandatory once Phase 7.2 packaging infra is completed, preventing empty directory tool errors from breaking early stages.
- **Mandatory Local Verification Gate (Single Quiet Verification Chain):** Before marking any checklist item `[x]` or advancing to the next batch, execute the quiet consolidated verification chain:
  ```bash
  ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && pytest -q --tb=short --cov=src/smartrx_safety_agents --cov-report=term:skip-covered --cov-fail-under=90
  ```
  *(During Phase 0 and Phase 1 before Python sources exist under `src/`, static validation runs exclusively on Markdown hyperlinked integrity, schema validation files, and configuration syntax, preventing empty directory tool errors).*
- **CI/CD Supply-Chain Gate:** Once Phase 7.2 is complete, remote GitHub Actions CI/CD workflows must cover the codebase and pass cleanly before marking CI/CD tasks `[x]`. The CI workflow must enforce:
  1. Primary blocking Python `3.13` test matrix (`continue-on-error: true` on experimental Python `3.14` matrix entries until upstream binary wheels stabilize).
  2. PEP 639-aware license compliance checks (`License-Expression`, `License`, and `Classifier` via `importlib.metadata`), allowing permissive licenses (`MIT`, `Apache-2.0`, `BSD`, `ISC`, `PSF-2.0`, `MPL-2.0`, `0BSD`) and strictly blocking copyleft licenses (`GPL`, `AGPL`, `LGPL`, `SSPL`).
  3. Scoped secret-scan exclusions (excluding `.github/workflows/ci.yml` itself and honoring `# pragma: allowlist secret` on synthetic test fixtures in `tests/` and `docs/`).
  4. Pinned lockfile hash verification (`uv.lock` or `requirements.lock`).
  5. Mandatory live green GitHub Actions verification (`gh run list`) before marking CI/CD tasks `[x]`.
- **Session Context Circuit Breaker & Fresh-Session Handoff Protocol:**
  - An AI agent session MUST NOT build more than **1–2 cohesive phases** (or exceed ~60% context window / 8–10 tool-heavy turns) in a single continuous chat session to avoid context rot, cognitive degradation, and hallucination loops.
  - Upon completing a phase batch (or detecting repeated lint/test retries or context bloat), the agent MUST:
    1. Append a structured entry to `AUDIT_REMEDIATION_LOG.md` recording all newly completed features, architectural additions, or security remediations.
    2. Update `PROJECT_MAP.md` with newly created files/symbols and mark verified `[x]` checkboxes in `Enterprise_Blueprint.md`.
    3. Ensure a clean committed or staged state via `git status --short`.
    4. Output a **Mandatory Fresh-Session Handoff Block** instructing the engineer to **open a new AI chat session** with a copy-paste starter prompt listing only the next Phase ID and the 2–4 exact file paths to read/create.
- **Resumable Recovery Protocol (`git status --short`):** When resuming an interrupted session or turn, inspect `git status --short` first and read only modified or untracked files on disk rather than regenerating existing code.
- **Anti-Test-Cheating & Verifiable Proof Gate:** Before marking any task complete (`[x]`), the agent must provide verbatim terminal proof of passing tests and coverage ($\ge 90\%$). Tampering with test files, assertions, coverage thresholds, or adding `@pytest.mark.skip` / `xfail` to force a passing status is strictly forbidden and constitutes an immediate integrity violation. Mocks are restricted solely to external network boundaries; internal logic and guardrails must never be self-mocked.
- **3-Strike Anti-Looping Circuit Breaker:** If a `ruff`, `mypy`, `pytest`, or build command fails **3 consecutive times** on the same module or error, the AI agent MUST immediately halt execution rather than looping indefinitely. It must log the exact error trace, root cause analysis, and attempted fixes in `Blueprint_Debug_Log.md` (under Section 2) and escalate to the human engineer for guidance.
