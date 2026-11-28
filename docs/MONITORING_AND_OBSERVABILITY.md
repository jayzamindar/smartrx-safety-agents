# Post-Deployment Monitoring & Observability Manual (`docs/MONITORING_AND_OBSERVABILITY.md`)

**Project:** `smartrx-safety-agents`  
**Instrumentation:** [`src/smartrx_safety_agents/observability.py`](../src/smartrx_safety_agents/observability.py) (`TelemetryManager`, `trace_span`, `InMemoryMetricsLedger`)  
**Health Endpoints:** `GET /health`, `GET /v1/health`, `GET /api/v1/audit/verify`

---

## 1. Infrastructure & Container Health Thresholds (Task 11.2)

| Signal | Warning Threshold | Critical Threshold | Automated / Operational Action |
|---|---|---|---|
| **CPU Utilization** | `> 80%` sustained (5m) | `> 95%` sustained (2m) | Scale horizontally (sharded ledger) or throttle non-critical batch runs. |
| **Container Memory (RAM)** | `>= 1750 MB` (`88%` of `2048m` cap) | `>= 1950 MB` (`95%` of `2048m` cap) | Drop active LLM reasoning round immediately and route to `DeterministicClinicalEngine` (Tertiary). |
| **SQLite WAL Size (`smartrx_ledger.db-wal`)** | `> 35 MB` | `> 50 MB` | Trigger `audit_ledger.checkpoint("PASSIVE")` or `"TRUNCATE"` during low-traffic window; verify no hung reader transactions. |
| **JSONL Audit Dir (`audit_logs/`)** | `> 400 MB` or age `> 25 days` | `> 500 MB` or age `> 30 days` | Verify `JsonlAuditExporter` retention pruning (`AUDIT_LOG_MAX_SIZE_MB=500`, `AUDIT_LOG_MAX_RETENTION_DAYS=30`) and object-storage sync. |
| **Container Health & Restarts** | `1` restart in 15m | `>= 3` restarts in 15m or `/health != 200` | Inspect `/health` (`wal_mode`, `chain_valid`, `catalog_rules`) and container stderr logs. |

---

## 2. API & MCP Transport Telemetry (Task 11.3)

- **Latency Targets (p50 / p95 / p99):**
  - Deterministic Heuristics (`/api/v1/reconcile` fallback / `DeterministicClinicalEngine`): `< 500 ms` p99.
  - Full 6-Agent Gemini Reasoning Pipeline: `< 3500 ms` p95.
- **Error Budget:** HTTP 4xx/5xx server-fault rate `< 0.1%` over rolling 15-minute window.
- **HTTP 413 Payload Too Large:** Alert on any burst (`> 3` events/min) indicating oversized (> 10MB / `10,485,760` bytes) requests or potential DoS probing caught by `PayloadSizeLimitMiddleware`.
- **HTTP 401 Auth Failure Spike:** Alert at `> 5` failures/minute per source IP or global endpoint to detect credential stuffing or brute-force attempts against `MCP_API_KEY`.
- **Concurrent SSE Connections:** Track active `active_streams` on `GET /api/v1/reconcile/stream` and `GET /sse`; alert if concurrent streams approach worker file-descriptor limits.

---

## 3. AI & Model Governance Telemetry (Task 11.4)

| Metric / Signal | Budget / Threshold | Alert Condition & Mitigation |
|---|---|---|
| **Token & Cost Ceilings** | `MAX_OUTPUT_TOKENS=8192`, `GEMINI_THINKING_BUDGET=2048`, `MAX_SESSION_TOKEN_BUDGET=500000`, `DAILY_API_COST_LIMIT_USD=10.00` | `MultiTierLLMClient._budget_exceeded()` automatically halts paid API calls and routes to Tertiary heuristics; alert FinOps channel at `80%` daily spend. |
| **`responseSchema` Validation Failures** | `< 0.5%` | Page on-call if `> 0.5%` over 10m; inspect `clean_gemini_schema()` logs and Gemini API schema compatibility. |
| **HTTP 429 / 503 Rate Limits** | 3 exponential-backoff attempts | Monitor retry frequency and backoff latency on Primary Gemini. |
| **Fallback Cascade Rate** | `< 2.0%` | Alert if `secondary_openrouter` or `deterministic_fallback` tier usage exceeds `2.0%` of requests. |
| **Quarantine & Catalog Alerts** | `quarantined=True` rate / `CatalogNotFoundError` | **Immediate Critical Alert** on any `CatalogNotFoundError` (`/health` returns HTTP `503`); track `quarantined=True` (`INVALID_ACTION_ENUM_TYPE`, `MISSING_MANDATORY_ROLLBACK`, `INVALID_FHIR_IDENTIFIER`) spikes. |

---

## 4. Security & Audit Integrity Alerts (Task 11.5)

- **HMAC-SHA256 Verification Failures (`PlanVerificationError`):** **Severity: CRITICAL (Immediate Page).** Any failure in `verify_plan_signature()` or `GuardrailEngine.verify_plan()` (signature mismatch, expired `expires_at`, or replayed `plan_id` nonce) must trigger an immediate security incident alert.
- **Prompt Injection & PHI Residual Triggers:** Monitor `wrap_untrusted_data()` delimiter-collision rewrites (`[/untrusted_telemetry_data]`) and `PHIRedactor.contains_phi()` post-scrubbing blocks (`MultiTierLLMClient` routing to deterministic fallback).
- **Hash-Chain Integrity:** Poll `GET /api/v1/audit/verify` (or `AuditLedger.verify_chain_integrity()`) every 5 minutes; alert immediately if `chain_valid: false`.

### Alert Routing Topology
- **OpenTelemetry OTLP:** Export spans and `InMemoryMetricsLedger` snapshots via OTLP/gRPC or OTLP/HTTP to Grafana Tempo/Prometheus or Datadog.
- **AWS CloudWatch / Azure Monitor:** Route container stdout JSON logs, `/health` probe failures, and `401`/`413`/`503` ALB/Ingress metrics to CloudWatch Alarms.
- **Incident Escalation:** Route Warning alerts to `#smartrx-sre-alerts` (Slack) and Critical alerts (`CatalogNotFoundError`, `PlanVerificationError`, `chain_valid=false`, OOM `> 95%`) to **PagerDuty** Tier-1 on-call.
