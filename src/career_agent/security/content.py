"""Treat imported text and filenames as inert data."""

from __future__ import annotations

import re
from pathlib import Path

_FACT_LABELS = {
    "name": ("identity.legal_name", True),
    "current title": ("employment.current_title", True),
    "employment start": ("employment.current_start_date", True),
    "suggested claim": ("unverified.claim", False),
}


def sanitize_untrusted_filename(name: str) -> str:
    """Return one portable basename without interpreting document-supplied paths."""

    basename = Path(name).name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip(" ._")
    return sanitized or "imported-file"


def extract_declared_facts(text: str) -> tuple[tuple[str, str, bool], ...]:
    """Extract only allowlisted factual labels; all other text remains inert."""

    facts: list[tuple[str, str, bool]] = []
    for line in text.splitlines():
        label, separator, value = line.partition(":")
        if not separator:
            continue
        field = _FACT_LABELS.get(label.strip().casefold())
        normalized_value = value.strip()
        if field is not None and normalized_value:
            key, supported = field
            facts.append((key, normalized_value, supported))
    return tuple(facts)
