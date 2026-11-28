# Security Hardening & Zero-Hallucination Controls (`docs/SECURITY_HARDENING.md`)

**Project:** `smartrx-safety-agents`  
**Standard:** Phase 9 Enterprise Security Hardening & Zero-Hallucination Guardrails (Tasks 9.1–9.22)  
**Regression Suite:** [`tests/test_phase9_hardening.py`](../tests/test_phase9_hardening.py)

---

## 1. Query Parameter API Key Plaintext Logging Advisory (Task 9.14 & 9.21)

### SecOps Guidance
The FastAPI gateway (`src/smartrx_safety_agents/api/server.py`) supports three authentication mechanisms for `MCP_API_KEY`:
1. **`Authorization: Bearer <key>`** *(Recommended)*
2. **`X-API-Key: <key>`** *(Recommended)*
3. **`?apiKey=<key>`** *(Compatibility fallback for SSE/EventSource clients that cannot set custom headers)*

**Security Advisory:** Passing credentials in URL query strings (`?apiKey=...`) exposes secrets in:
- Reverse proxy, load balancer, and ingress access logs (e.g., NGINX, Envoy, AWS ALB)
- Browser history, bookmarks, and `Referer` headers
- APM traces and crash-report breadcrumbs

**Operational Mandate:**
- Always use `Authorization: Bearer <key>` or `X-API-Key: <key>` in backend-to-backend, CLI, and MCP integrations.
- When `?apiKey=<key>` is unavoidable for browser SSE (`EventSource`) clients, terminate TLS at the ingress and configure upstream proxies to strip or mask `apiKey` query parameters.
- At the application layer, `create_app()` attaches `SensitiveQueryParamFilter` to `uvicorn.access` (`src/smartrx_safety_agents/api/server.py`), rewriting `?apiKey=<secret>` to `?apiKey=***` before log emission.

---

## 2. Pre-Commit & Repository Hygiene (Task 9.15)

- **Zero Un-Ignored `.env` Files:** `.gitignore` explicitly excludes `.env` (`git check-ignore -v .env` -> `.gitignore:14:.env`). Only the secret-free template `.env.example` may be committed.
- **Fail-Closed Production Secret Checks:** `Settings.validate_production_secrets()` in `src/smartrx_safety_agents/config.py` and `GuardrailEngine.__init__()` in `src/smartrx_safety_agents/guardrails/engine.py` raise `RuntimeError` at startup if `ENVIRONMENT=production` and `PLAN_SIGNING_SECRET`, `SMARTRX_SAFETY_AGENTS_WEBHOOK_SECRET`, or `MCP_API_KEY` are missing, shorter than 16 characters, or set to insecure defaults (`changeme`, `default`, `secret`, `test`, `placeholder`, `none`).
- **CI Secret & Dependency Gate:** `.github/workflows/ci.yml` executes `pip-audit`, PEP 639 license checks, and scoped secret scanning on every push and pull request.

---

## 3. Phase 9 Control Verification Matrix (Tasks 9.1–9.22)

| Control | Implementation Location | Verification |
|---|---|---|
| **9.1** Dual-layer 10MB limit, auth, `asyncio.to_thread()` DB writes | `api/server.py` (`PayloadSizeLimitMiddleware`, `_lifespan`, `_health_check`) | `tests/test_phase9_hardening.py` |
| **9.2, 9.13, 9.18** Canonical JSON HMAC-SHA256, `expires_at` ($\le 300\text{s}$), nonce replay | `guardrails/engine.py` (`canonical_plan_json`, `verify_plan_signature`, `GuardrailEngine.verify_plan`) | `tests/test_phase9_hardening.py` |
| **9.3** Fail-closed `HOLD_PRESCRIPTION` + `ESCALATE_TO_CLINICAL_PHARMACIST` | `heuristics/ddi_engine.py`, `heuristics/allergy_checker.py`, `heuristics/engine.py`, `agents/specialists.py` | `tests/test_phase9_hardening.py` |
| **9.4** Organ-function dosing bounds & missing NTI labs (`REQUEST_RENAL_HEPATIC_LABS`) | `heuristics/dosing_validator.py`, `heuristics/engine.py` | `tests/test_phase9_hardening.py` |
| **9.5** Quarantine on Risk $\ge 3$ without rollback or invalid `ActionType` | `guardrails/engine.py` (`GuardrailEngine.enforce`), `guardrails/rollback.py` | `tests/test_phase9_hardening.py` |
| **9.6, 9.12, 9.16, 9.19** Gemini `responseSchema` `$defs` deref, `anyOf` collapse, `ALLOWED_GEMINI_FIELDS`, `execution_payload` exclusion, `maxOutputTokens=8192` | `agents/llm_client.py` (`clean_gemini_schema`, `MultiTierLLMClient`) | `tests/test_phase9_hardening.py` |
| **9.7** SQLite WAL + JSONL durability & deterministic HIPAA PHI redaction | `persistence/ledger.py`, `heuristics/phi_redactor.py`, `docs/Ephemeral_Ledger_Architecture.md` | `tests/test_guardrails_ledger.py`, `tests/test_observability_and_retention.py` |
| **9.8, 9.17** Deterministic HL7 FHIR R4 payload overwriting & identifier validation | `guardrails/fhir_generator.py` (`generate_fhir_payload`), `guardrails/engine.py` | `tests/test_phase9_hardening.py` |
| **9.9** Fail-closed `CatalogNotFoundError` on missing/corrupt `config/drug_interactions.json` | `heuristics/ddi_engine.py` (`load_catalog`, `CatalogNotFoundError`) | `tests/test_phase9_hardening.py` |
| **9.10** Constant-time `hmac.compare_digest()` auth & fail-closed enforcement | `api/server.py` (`_build_auth_dependency`), `config.py` | `tests/test_phase9_hardening.py` |
| **9.14, 9.21** Query param API key SecOps advisory & `SensitiveQueryParamFilter` | `docs/SECURITY_HARDENING.md`, `api/server.py` | `tests/test_phase9_hardening.py` |
| **9.15** Pre-commit & `.env` repository hygiene | `.gitignore`, `.env.example`, `.github/workflows/ci.yml` | `git check-ignore -v .env` |
| **9.20** Strip `<think>` reasoning blocks & code fences from secondary LLM responses | `agents/llm_client.py` (`strip_think_tags`) | `tests/test_phase9_hardening.py` |
| **9.11, 9.22** Dedicated Phase 9 regression suite & 100% passing CI gate | `tests/test_phase9_hardening.py` | `pytest` (>=90% coverage) |
