"""Portable, collision-resistant employer-facing document filenames."""

from __future__ import annotations

import re
import unicodedata


def filename_component(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_")
    return normalized or "Document"


def upload_filename(
    *,
    first_name: str,
    last_name: str,
    company: str,
    role: str,
    artifact_label: str,
    checksum: str,
    extension: str,
) -> str:
    parts = (
        first_name,
        last_name,
        company,
        role,
        artifact_label,
        checksum[:8],
    )
    stem = "_".join(filename_component(part) for part in parts)
    return f"{stem}.{extension.casefold()}"
