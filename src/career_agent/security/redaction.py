"""Recursive privacy-safe redaction for answer diagnostics and projections."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_KEYS = {
    "answer",
    "exact_user_response",
    "password",
    "secret",
    "token",
    "value",
}
_INLINE_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----"),
)
REDACTED = "[REDACTED]"


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _INLINE_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def sanitize(value: Any, *, key: str | None = None) -> Any:
    if key is not None:
        normalized_key = key.casefold()
        if (
            normalized_key in _SENSITIVE_KEYS
            or normalized_key.endswith(("_value", "_answer", "_response"))
            or any(part in normalized_key for part in ("password", "secret", "token"))
        ):
            return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize(item, key=str(item_key)) for item_key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize(item) for item in value]
    return value
