"""Deterministic geometric signals used by the PDF release gate."""

# Concept provenance: ai-job-search@27eb57a tools/verify_layout.py. This V1 port
# keeps the high-signal thin-page, stranded-heading, and footer-collision checks
# while emitting typed signals consumed by the application-owned release gate.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PageLayout:
    page_number: int
    width: float
    height: float
    text: str
    blocks: tuple[tuple[float, float, float, float, str], ...]


@dataclass(frozen=True)
class LayoutSignal:
    name: str
    passed: bool
    detail: str


_HEADINGS = {
    "experience",
    "education",
    "skills",
    "projects",
    "summary",
    "certifications",
}


def analyze_layout(
    pages: Sequence[PageLayout],
    *,
    minimum_text_characters: int,
) -> tuple[LayoutSignal, ...]:
    signals: list[LayoutSignal] = []
    for page in pages:
        characters = len("".join(page.text.split()))
        signals.append(
            LayoutSignal(
                name="thin_page",
                passed=characters >= minimum_text_characters,
                detail=f"page {page.page_number} contains {characters} non-space characters",
            )
        )
        stranded = any(
            block[4].strip().casefold().rstrip(":") in _HEADINGS and block[1] >= page.height * 0.85
            for block in page.blocks
        )
        signals.append(
            LayoutSignal(
                name="stranded_heading",
                passed=not stranded,
                detail=f"page {page.page_number} heading placement",
            )
        )
        footer_collision = any(block[3] >= page.height - 12 for block in page.blocks)
        signals.append(
            LayoutSignal(
                name="footer_collision",
                passed=not footer_collision,
                detail=f"page {page.page_number} bottom margin",
            )
        )
    return tuple(signals)
