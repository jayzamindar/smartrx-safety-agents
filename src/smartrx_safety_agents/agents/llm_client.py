"""Async multi-tier LLM resilience client with pre-LLM PHI scrubbing and schema sanitization."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from smartrx_safety_agents.config import Settings, get_settings
from smartrx_safety_agents.heuristics.phi_redactor import PHIRedactor

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ALLOWED_GEMINI_FIELDS: Final[frozenset[str]] = frozenset(
    {"type", "description", "nullable", "enum", "properties", "items", "required", "title"}
)
DEFAULT_PROMPTS_DIR: Final[Path] = Path(__file__).resolve().parents[3] / "prompts" / "modules"
_THINK_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE
)
_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^Version:\s*(v[0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)
_MAX_OUTPUT_TOKENS_CEILING: Final[int] = 8192
_RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 503})


@dataclass(frozen=True)
class LLMCallResult[T: BaseModel]:
    """Structured result from a multi-tier LLM or deterministic fallback invocation."""

    parsed: T
    tier_used: Literal["primary_gemini", "secondary_openrouter", "deterministic_fallback"]
    model_version: str
    prompt_tokens: int = 0
    output_tokens: int = 0
    redaction_count: int = 0


def strip_think_tags(raw_text: str) -> str:
    """Strip `<think>...</think>` reasoning blocks and markdown code fences before JSON decoding."""
    cleaned = _THINK_TAG_RE.sub("", raw_text).strip()
    fence_match = _CODE_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    return cleaned


def wrap_untrusted_data(payload: str) -> str:
    """Sanitize delimiter collisions and enclose untrusted data in XML-style tags."""
    sanitized = payload.replace("</untrusted_telemetry_data>", "[/untrusted_telemetry_data]")
    sanitized = sanitized.replace("<untrusted_telemetry_data>", "[untrusted_telemetry_data]")
    return f"<untrusted_telemetry_data>\n{sanitized}\n</untrusted_telemetry_data>"


def load_prompt_module(
    module_name: str,
    prompts_dir: Path | None = None,
) -> tuple[str, str]:
    """Load a prompt module enforcing path traversal isolation and UTF-8 I/O."""
    base_dir = (prompts_dir or DEFAULT_PROMPTS_DIR).resolve()
    target_path = (base_dir / module_name).resolve()
    if not target_path.is_relative_to(base_dir):
        raise ValueError(f"Path traversal blocked for prompt module: {module_name!r}")
    if not target_path.is_file():
        raise FileNotFoundError(f"Prompt module not found: {target_path}")
    content = target_path.read_text(encoding="utf-8")
    version_match = _VERSION_RE.search(content)
    version = version_match.group(1) if version_match else "v1.0.0"
    return content, version


def clean_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a Pydantic JSON schema for Gemini OpenAPI 3.0 Protobuf compliance."""
    defs: dict[str, Any] = {}
    if isinstance(schema.get("$defs"), dict):
        defs.update(schema["$defs"])
    if isinstance(schema.get("definitions"), dict):
        defs.update(schema["definitions"])

    def _resolve_node(node: Any, seen_refs: frozenset[str]) -> Any:
        if not isinstance(node, dict):
            return node

        if "$ref" in node and isinstance(node["$ref"], str):
            ref_key = node["$ref"].rsplit("/", maxsplit=1)[-1]
            if ref_key in defs and ref_key not in seen_refs:
                merged = dict(defs[ref_key])
                for k, v in node.items():
                    if k != "$ref":
                        merged[k] = v
                return _resolve_node(merged, seen_refs | {ref_key})

        working = dict(node)
        if "anyOf" in working and isinstance(working["anyOf"], list):
            variants = working.pop("anyOf")
            has_null = any(isinstance(v, dict) and v.get("type") == "null" for v in variants)
            non_null = [
                v for v in variants if not (isinstance(v, dict) and v.get("type") == "null")
            ]
            if non_null:
                chosen = _resolve_node(non_null[0], seen_refs)
                if isinstance(chosen, dict):
                    for k, v in chosen.items():
                        working.setdefault(k, v)
            if has_null:
                working["nullable"] = True

        had_additional_props = "additionalProperties" in working
        cleaned: dict[str, Any] = {}
        for key, value in working.items():
            if key not in ALLOWED_GEMINI_FIELDS:
                continue
            if key == "properties" and isinstance(value, dict):
                cleaned["properties"] = {
                    prop_k: _resolve_node(prop_v, seen_refs) for prop_k, prop_v in value.items()
                }
            elif key == "items" and isinstance(value, dict):
                cleaned["items"] = _resolve_node(value, seen_refs)
            else:
                cleaned[key] = value

        if had_additional_props and "type" not in cleaned:
            cleaned["type"] = "object"
        return cleaned

    result = _resolve_node(schema, frozenset())
    return result if isinstance(result, dict) else {"type": "object"}


class MultiTierLLMClient:
    """Primary Gemini -> Secondary OpenRouter/Ollama -> Deterministic Fallback cascade."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
        secondary_base_url: str = "https://openrouter.ai/api/v1/chat/completions",
        secondary_model: str = "openrouter/qwen-2.5-coder-32b-instruct",
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings or get_settings()
        self._http_client = http_client
        self._secondary_base_url = secondary_base_url
        self._secondary_model = secondary_model
        self._sleep_fn = sleep_fn
        self._phi_redactor = PHIRedactor()
        self.session_tokens_used: int = 0
        self.session_cost_usd: float = 0.0

    @property
    def max_output_tokens(self) -> int:
        """Enforce hard 8192 output token ceiling."""
        return min(self._settings.max_output_tokens, _MAX_OUTPUT_TOKENS_CEILING)

    def _budget_exceeded(self) -> bool:
        return (
            self.session_tokens_used >= self._settings.max_session_token_budget
            or self.session_cost_usd >= self._settings.daily_api_cost_limit_usd
        )

    def _record_usage(self, prompt_tokens: int, output_tokens: int) -> None:
        self.session_tokens_used += prompt_tokens + output_tokens
        # Conservative blended cost estimate ($0.50 / 1M tokens) for circuit breaker tracking.
        self.session_cost_usd += ((prompt_tokens + output_tokens) / 1_000_000) * 0.50

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_payload: str,
        response_model: type[T],
        fallback_fn: Callable[[], T],
        known_names: tuple[str, ...] = (),
        known_mrns: tuple[str, ...] = (),
    ) -> LLMCallResult[T]:
        """Execute pre-LLM PHI scrubbing and 3-tier resilient structured generation."""
        redaction = self._phi_redactor.redact(
            user_payload,
            known_names=known_names,
            known_mrns=known_mrns,
        )
        scrubbed_payload = redaction.redacted_text
        if PHIRedactor.contains_phi(scrubbed_payload, known_identifiers=known_names + known_mrns):
            logger.warning(
                "Residual PHI detected after scrubbing; routing to deterministic fallback."
            )
            return LLMCallResult(
                parsed=fallback_fn(),
                tier_used="deterministic_fallback",
                model_version="deterministic-sre-heuristics-v1",
                redaction_count=redaction.redaction_count,
            )

        if self._budget_exceeded():
            logger.warning("Session token or daily cost budget exceeded; routing to fallback.")
            return LLMCallResult(
                parsed=fallback_fn(),
                tier_used="deterministic_fallback",
                model_version="deterministic-sre-heuristics-v1",
                redaction_count=redaction.redaction_count,
            )

        wrapped_user = wrap_untrusted_data(scrubbed_payload)

        # Tier 1: Primary Gemini
        if self._settings.gemini_api_key is not None:
            try:
                parsed, p_tok, o_tok = await self._call_primary_gemini(
                    system_prompt=system_prompt,
                    user_prompt=wrapped_user,
                    response_model=response_model,
                )
                self._record_usage(p_tok, o_tok)
                return LLMCallResult(
                    parsed=parsed,
                    tier_used="primary_gemini",
                    model_version=self._settings.gemini_model_name,
                    prompt_tokens=p_tok,
                    output_tokens=o_tok,
                    redaction_count=redaction.redaction_count,
                )
            except Exception as exc:
                logger.warning(
                    "Primary Gemini failed (%s); cascading to Secondary.",
                    type(exc).__name__,
                )

        # Tier 2: Secondary OpenRouter / Ollama
        if self._settings.openrouter_api_key is not None:
            try:
                parsed, p_tok, o_tok = await self._call_secondary_openrouter(
                    system_prompt=system_prompt,
                    user_prompt=wrapped_user,
                    response_model=response_model,
                )
                self._record_usage(p_tok, o_tok)
                return LLMCallResult(
                    parsed=parsed,
                    tier_used="secondary_openrouter",
                    model_version=self._secondary_model,
                    prompt_tokens=p_tok,
                    output_tokens=o_tok,
                    redaction_count=redaction.redaction_count,
                )
            except Exception as exc:
                logger.warning(
                    "Secondary OpenRouter failed (%s); cascading to Deterministic Fallback.",
                    type(exc).__name__,
                )

        # Tier 3: Deterministic Fallback
        return LLMCallResult(
            parsed=fallback_fn(),
            tier_used="deterministic_fallback",
            model_version="deterministic-sre-heuristics-v1",
            redaction_count=redaction.redaction_count,
        )

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, headers=headers, json=payload, timeout=15.0)
        async with httpx.AsyncClient(timeout=15.0) as client:
            return await client.post(url, headers=headers, json=payload)

    async def _call_primary_gemini(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> tuple[T, int, int]:
        assert self._settings.gemini_api_key is not None  # noqa: S101
        api_key = self._settings.gemini_api_key.get_secret_value()
        model_name = self._settings.gemini_model_name
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        )
        sanitized_schema = clean_gemini_schema(response_model.model_json_schema())
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.max_output_tokens,
                "responseMimeType": "application/json",
                "responseSchema": sanitized_schema,
                "thinkingConfig": {"thinkingBudget": self._settings.gemini_thinking_budget},
            },
        }
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._post_json(url, headers=headers, payload=payload)
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                body = response.json()
                candidates = body.get("candidates") or []
                if not candidates:
                    raise ValueError("Empty candidates returned by Gemini.")
                parts = candidates[0].get("content", {}).get("parts", [])
                raw_text = "".join(str(p.get("text", "")) for p in parts).strip()
                if not raw_text:
                    raise ValueError("Empty text returned by Gemini.")
                parsed = response_model.model_validate_json(strip_think_tags(raw_text))
                usage = body.get("usageMetadata") or {}
                return (
                    parsed,
                    int(usage.get("promptTokenCount", 0)),
                    int(usage.get("candidatesTokenCount", 0)),
                )
            except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                last_exc = exc
                status = (
                    exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                )
                if attempt < 2 and (status in _RETRYABLE_STATUS_CODES or status is None):
                    delay = min(8.0, 1.0 * (2**attempt)) * random.uniform(0.5, 1.0)  # noqa: S311
                    await self._sleep_fn(delay)
                    continue
                raise
            except (json.JSONDecodeError, ValidationError, ValueError, KeyError, TypeError):
                raise
        assert last_exc is not None  # noqa: S101
        raise last_exc

    async def _call_secondary_openrouter(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> tuple[T, int, int]:
        assert self._settings.openrouter_api_key is not None  # noqa: S101
        api_key = self._settings.openrouter_api_key.get_secret_value()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._secondary_model,
            "max_tokens": self.max_output_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        response = await self._post_json(self._secondary_base_url, headers=headers, payload=payload)
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise ValueError("Empty choices returned by OpenRouter.")
        raw_content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not raw_content:
            raise ValueError("Empty content returned by OpenRouter.")
        cleaned = strip_think_tags(raw_content)
        parsed = response_model.model_validate_json(cleaned)
        usage = body.get("usage") or {}
        return (
            parsed,
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )
