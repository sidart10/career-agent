"""Mechanical PDF validation beyond successful compilation."""

# Concept provenance: ai-job-search@27eb57a tools/verify_pdf.py. This adaptation
# uses application-owned paths and persisted V1 reports while preserving raw ATS
# extraction separately from normalized comparison text.

from __future__ import annotations

import re
from pathlib import Path, PurePath

import pymupdf
from pydantic import BaseModel, ConfigDict, Field

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import ApplicationId, PersistedModel
from career_agent.storage.atomic import atomic_write_bytes
from career_agent.storage.paths import safe_resolve

from .layout_validation import PageLayout, analyze_layout


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool
    detail: str


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_fields: tuple[str, ...] = ()
    logical_order: tuple[str, ...] = ()
    minimum_text_characters: int = Field(default=80, ge=0)
    maximum_pages: int = Field(default=2, ge=1)


class ValidationReport(PersistedModel):
    application_id: ApplicationId
    passed: bool
    engine: str
    page_count: int
    readable: CheckResult
    required_fields: tuple[CheckResult, ...]
    placeholders: tuple[CheckResult, ...]
    layout: tuple[CheckResult, ...]
    ats_text_path: str
    raw_ats_text: str
    normalized_ats_text: str
    logical_order: tuple[CheckResult, ...]


_PLACEHOLDERS = (
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"\b(?:TODO|TBD|PLACEHOLDER|XXX)\b", re.IGNORECASE),
)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class PdfValidator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)

    def validate(
        self,
        application_id: str,
        artifact: Path,
        request: ValidationRequest,
    ) -> ValidationReport:
        expected_drafts = safe_resolve(
            self.root,
            PurePath("applications", application_id, "drafts"),
        )
        resolved_artifact = artifact.resolve(strict=False)
        try:
            resolved_artifact.relative_to(expected_drafts)
        except ValueError as error:
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "PDF validation is restricted to the application's drafts",
                {"application_id": application_id},
            ) from error
        raw_text = ""
        layouts: list[PageLayout] = []
        readable = True
        try:
            with pymupdf.open(resolved_artifact) as document:  # type: ignore[no-untyped-call]
                for page_index, page in enumerate(document):
                    page_text = page.get_text("text")
                    raw_text += page_text
                    if page_index + 1 < document.page_count:
                        raw_text += "\f"
                    blocks = tuple(
                        (
                            float(item[0]),
                            float(item[1]),
                            float(item[2]),
                            float(item[3]),
                            str(item[4]),
                        )
                        for item in page.get_text("blocks")
                    )
                    layouts.append(
                        PageLayout(
                            page_number=page_index + 1,
                            width=float(page.rect.width),
                            height=float(page.rect.height),
                            text=page_text,
                            blocks=blocks,
                        )
                    )
        except (FileNotFoundError, pymupdf.FileDataError, RuntimeError, ValueError):
            readable = False
        normalized_text = _normalized(raw_text)
        ats_path = resolved_artifact.with_suffix(".ats.txt")
        atomic_write_bytes(ats_path, raw_text.encode())
        readable_check = CheckResult(
            name="readable",
            passed=readable and bool(normalized_text),
            detail="PDF opened and yielded text" if readable else "PDF could not be read",
        )
        required_checks = tuple(
            CheckResult(
                name=f"required:{field}",
                passed=_normalized(field) in normalized_text,
                detail=(
                    "required field present" if _normalized(field) in normalized_text else "missing"
                ),
            )
            for field in request.required_fields
        )
        placeholder_checks = tuple(
            CheckResult(
                name="placeholder_free",
                passed=pattern.search(raw_text) is None,
                detail="no unresolved placeholder" if pattern.search(raw_text) is None else "found",
            )
            for pattern in _PLACEHOLDERS
        )
        layout_checks = [
            CheckResult(name=item.name, passed=item.passed, detail=item.detail)
            for item in analyze_layout(
                layouts,
                minimum_text_characters=request.minimum_text_characters,
            )
        ]
        layout_checks.append(
            CheckResult(
                name="page_count",
                passed=0 < len(layouts) <= request.maximum_pages,
                detail=f"{len(layouts)} pages; maximum {request.maximum_pages}",
            )
        )
        order_positions = [
            normalized_text.find(_normalized(item)) for item in request.logical_order
        ]
        logical_passed = all(
            position >= 0 for position in order_positions
        ) and order_positions == sorted(order_positions)
        logical_checks = (
            CheckResult(
                name="logical_order",
                passed=logical_passed,
                detail="required sections follow the configured logical order",
            ),
        )
        checks = (
            readable_check,
            *required_checks,
            *placeholder_checks,
            *layout_checks,
            *logical_checks,
        )
        return ValidationReport(
            application_id=application_id,
            passed=all(check.passed for check in checks),
            engine="pymupdf",
            page_count=len(layouts),
            readable=readable_check,
            required_fields=required_checks,
            placeholders=placeholder_checks,
            layout=tuple(layout_checks),
            ats_text_path=ats_path.relative_to(self.root).as_posix(),
            raw_ats_text=raw_text,
            normalized_ats_text=normalized_text,
            logical_order=logical_checks,
        )
