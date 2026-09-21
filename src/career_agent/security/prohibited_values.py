"""Reject credential and identity secrets before governed answer persistence."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from career_agent.errors import CareerError, ErrorCode

_PROHIBITED_QUESTION_PARTS = {
    "password",
    "passkey",
    "mfa",
    "one_time_code",
    "national_identifier",
    "social_security",
    "banking",
    "bank_account",
    "routing_number",
    "identity_document",
    "passport",
    "drivers_license",
}

_PROHIBITED_VALUE_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def prohibited_category(question_id: str, *values: object) -> str | None:
    normalized_id = question_id.casefold().replace("-", "_")
    if any(part in normalized_id for part in _PROHIBITED_QUESTION_PARTS):
        return "prohibited_field"
    for value in values:
        for text in _strings(value):
            if any(pattern.search(text) for pattern in _PROHIBITED_VALUE_PATTERNS):
                return "prohibited_value_pattern"
    return None


def reject_prohibited(question_id: str, *values: object) -> None:
    category = prohibited_category(question_id, *values)
    if category is None:
        return
    raise CareerError(
        ErrorCode.INVALID_INPUT,
        "Prohibited credential or identity data cannot be persisted",
        {"question_id": question_id, "category": category},
    )
