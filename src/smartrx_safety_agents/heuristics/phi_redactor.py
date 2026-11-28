"""Deterministic HIPAA PHI redaction and reversible local tokenization."""

from __future__ import annotations

import hashlib
import re
from typing import Final

from smartrx_safety_agents.models.clinical import StrictClinicalModel, normalize_clinical_identifier

_SSN_RE: Final[re.Pattern[str]] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_MRN_RE: Final[re.Pattern[str]] = re.compile(
    r"\bMRN[:#\s-]*[A-Z0-9]{2,}(?:-[A-Z0-9]+)*\b", re.IGNORECASE
)
_DOB_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:DOB|Date\s+of\s+Birth)[:\s]*(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.IGNORECASE,
)
_PHONE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
_EMAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_LABELED_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:Patient(?:\s+Name)?|Name)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)


class RedactionResult(StrictClinicalModel):
    """Result of deterministic PHI scrubbing with reversible local token map."""

    redacted_text: str
    token_map: dict[str, str]
    redaction_count: int


class PHIRedactor:
    """Deterministic regex and identifier redactor preventing PHI egress to LLMs."""

    @staticmethod
    def tokenize_patient_id(raw_id: str) -> str:
        """Return a deterministic, non-reversible SHA-256 patient token."""
        digest = hashlib.sha256(raw_id.strip().encode("utf-8")).hexdigest()[:12]
        return f"pt_{digest}"

    def redact(
        self,
        text: str,
        *,
        known_names: tuple[str, ...] = (),
        known_mrns: tuple[str, ...] = (),
    ) -> RedactionResult:
        """Scrub PHI from text and return redacted text with a reversible token map."""
        token_map: dict[str, str] = {}
        counters: dict[str, int] = {}
        current = text

        def _make_token(category: str, original: str) -> str:
            for existing_token, existing_val in token_map.items():
                if existing_val == original:
                    return existing_token
            idx = counters.get(category, 0) + 1
            counters[category] = idx
            token = f"[PHI_{category}_{idx}]"
            token_map[token] = original
            return token

        for name in sorted((n.strip() for n in known_names if n.strip()), key=len, reverse=True):
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            current = pattern.sub(lambda m: _make_token("NAME", m.group(0)), current)

        for mrn in sorted((m.strip() for m in known_mrns if m.strip()), key=len, reverse=True):
            pattern = re.compile(re.escape(mrn), re.IGNORECASE)
            current = pattern.sub(lambda m: _make_token("MRN", m.group(0)), current)

        def _replace_labeled_name(match: re.Match[str]) -> str:
            full = match.group(0)
            name_part = match.group(1)
            prefix = full[: len(full) - len(name_part)]
            return f"{prefix}{_make_token('NAME', name_part)}"

        current = _LABELED_NAME_RE.sub(_replace_labeled_name, current)
        current = _SSN_RE.sub(lambda m: _make_token("SSN", m.group(0)), current)
        current = _MRN_RE.sub(lambda m: _make_token("MRN", m.group(0)), current)
        current = _DOB_RE.sub(lambda m: _make_token("DOB", m.group(0)), current)
        current = _EMAIL_RE.sub(lambda m: _make_token("EMAIL", m.group(0)), current)
        current = _PHONE_RE.sub(lambda m: _make_token("PHONE", m.group(0)), current)

        return RedactionResult(
            redacted_text=current,
            token_map=token_map,
            redaction_count=len(token_map),
        )

    @staticmethod
    def restore(redacted_text: str, token_map: dict[str, str]) -> str:
        """Restore original PHI locally using the reversible token map."""
        restored = redacted_text
        for token, original in token_map.items():
            restored = restored.replace(token, original)
        return restored

    @staticmethod
    def contains_phi(text: str, *, known_identifiers: tuple[str, ...] = ()) -> bool:
        """Return True if any detectable PHI pattern or known identifier remains."""
        for pattern in (_SSN_RE, _MRN_RE, _DOB_RE, _EMAIL_RE, _PHONE_RE, _LABELED_NAME_RE):
            if pattern.search(text):
                return True
        lowered = normalize_clinical_identifier(text)
        return any(
            normalize_clinical_identifier(ident) in lowered
            for ident in known_identifiers
            if ident.strip()
        )
