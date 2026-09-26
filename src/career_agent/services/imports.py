"""Copy-first career evidence import and deterministic fact proposals."""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
import warnings
import zipfile
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from io import BytesIO
from pathlib import Path, PurePath
from typing import Literal
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel, SourceReference
from career_agent.security.content import extract_declared_facts, sanitize_untrusted_filename
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExtractionStatus(StrEnum):
    EXTRACTED = "extracted"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class ExtractionBlock(_ContractModel):
    block_id: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class ExtractionOutput(_ContractModel):
    text: str
    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    blocks: tuple[ExtractionBlock, ...]
    warnings: tuple[str, ...] = ()
    ocr_status: Literal["not_applicable", "not_required", "unsupported", "performed"]


class ImportSource(_ContractModel):
    source_id: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_paths: tuple[str, ...]
    original_filenames: tuple[str, ...]
    media_type: str
    size_bytes: int = Field(ge=0)
    extraction_status: ExtractionStatus
    extraction_error: str | None = None
    extracted_text: str = ""
    extracted_at: datetime
    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    normalized_text_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blocks: tuple[ExtractionBlock, ...] = ()
    warnings: tuple[str, ...] = ()
    ocr_status: Literal["not_applicable", "not_required", "unsupported", "performed"]


class ImportedSource(_ContractModel):
    source_id: str
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_paths: tuple[str, ...]
    stored_path: str
    media_type: str
    extraction_status: ExtractionStatus
    extracted_at: datetime
    extracted_text_path: str | None = None
    normalized_text_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    blocks: tuple[ExtractionBlock, ...] = ()
    warnings: tuple[str, ...] = ()
    ocr_status: Literal["not_applicable", "not_required", "unsupported", "performed"]


class DuplicateSource(_ContractModel):
    source_id: str
    source_paths: tuple[str, ...]


class ProposedFact(_ContractModel):
    proposal_id: str
    fact_id: str | None = None
    key: str
    value: JsonValue
    sources: tuple[SourceReference, ...]
    supported: bool = True


class FactConflict(_ContractModel):
    conflict_id: str
    key: str
    alternatives: tuple[ProposedFact, ...]
    resolved_fact_id: str | None = None


class ImportPreview(PersistedModel):
    run_id: str
    source_files: tuple[ImportSource, ...]
    duplicates: tuple[DuplicateSource, ...]
    proposed_facts: tuple[ProposedFact, ...]
    conflicts: tuple[FactConflict, ...]


class ImportResult(PersistedModel):
    run_id: str
    imported_sources: tuple[ImportedSource, ...]
    proposed_facts: tuple[ProposedFact, ...]
    conflicts: tuple[FactConflict, ...]


def _detect_media_type(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return "application/octet-stream"
        if {"[Content_Types].xml", "word/document.xml"}.issubset(names):
            return DOCX_MEDIA_TYPE
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    return "text/plain"


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def _single_block(text: str) -> tuple[ExtractionBlock, ...]:
    return (
        ExtractionBlock(
            block_id="document",
            start_offset=0,
            end_offset=len(text),
        ),
    )


def _extract_text(data: bytes, media_type: str) -> ExtractionOutput:
    if media_type == "text/plain":
        text = _normalize_text(data.decode("utf-8"))
        return ExtractionOutput(
            text=text,
            extractor="career-agent-text",
            extractor_version="1",
            blocks=_single_block(text),
            ocr_status="not_applicable",
        )
    if media_type == "application/pdf":
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"builtin type (SwigPyPacked|SwigPyObject|swigvarlink).*",
                category=DeprecationWarning,
            )
            import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]
            text = ""
            blocks: list[ExtractionBlock] = []
            for page_number, page in enumerate(document, start=1):
                page_text = _normalize_text(page.get_text())
                if text:
                    text += "\n"
                start = len(text)
                text += page_text
                blocks.append(
                    ExtractionBlock(
                        block_id=f"page-{page_number}",
                        page_number=page_number,
                        start_offset=start,
                        end_offset=len(text),
                    )
                )
            if not text.strip():
                return ExtractionOutput(
                    text="",
                    extractor="pymupdf",
                    extractor_version=str(getattr(pymupdf, "VersionBind", "unknown")),
                    blocks=tuple(blocks),
                    warnings=("image_only_pdf",),
                    ocr_status="unsupported",
                )
            return ExtractionOutput(
                text=text,
                extractor="pymupdf",
                extractor_version=str(getattr(pymupdf, "VersionBind", "unknown")),
                blocks=tuple(blocks),
                ocr_status="not_required",
            )
    if media_type == DOCX_MEDIA_TYPE:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            document_xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(document_xml)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        text = _normalize_text(
            "\n".join(element.text or "" for element in root.iter(f"{namespace}t"))
        )
        return ExtractionOutput(
            text=text,
            extractor="career-agent-docx-xml",
            extractor_version="1",
            blocks=_single_block(text),
            ocr_status="not_applicable",
        )
    raise ValueError("unsupported media type")


def _proposal_id(key: str, value: JsonValue, source_id: str) -> str:
    payload = json.dumps([key, value, source_id], separators=(",", ":"), sort_keys=True)
    return f"PROPOSAL-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def build_conflicts(proposals: Sequence[ProposedFact]) -> tuple[FactConflict, ...]:
    by_key: dict[str, list[ProposedFact]] = defaultdict(list)
    for proposal in proposals:
        by_key[proposal.key].append(proposal)
    conflicts: list[FactConflict] = []
    for key, alternatives in sorted(by_key.items()):
        distinct_values = {json.dumps(item.value, sort_keys=True) for item in alternatives}
        if len(distinct_values) < 2:
            continue
        digest = hashlib.sha256(key.encode()).hexdigest()[:12]
        conflicts.append(
            FactConflict(
                conflict_id=f"CONFLICT-{digest}",
                key=key,
                alternatives=tuple(alternatives),
            )
        )
    return tuple(conflicts)


class ImportService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.registry = SequenceRegistry(self.root)

    def _expand_sources(self, sources: Sequence[Path]) -> tuple[Path, ...]:
        expanded: list[Path] = []
        for source in sources:
            resolved = source.expanduser().resolve()
            if resolved.is_dir():
                expanded.extend(path for path in resolved.rglob("*") if path.is_file())
            elif resolved.is_file():
                expanded.append(resolved)
            else:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Import source does not exist",
                    {"path": str(source)},
                )
        return tuple(sorted(set(expanded), key=str))

    def preview(self, sources: Sequence[Path]) -> ImportPreview:
        run_id = self.registry.allocate_run_id()
        grouped: dict[str, list[Path]] = defaultdict(list)
        content_by_checksum: dict[str, bytes] = {}
        for path in self._expand_sources(sources):
            checksum = sha256_file(path)
            grouped[checksum].append(path)
            content_by_checksum.setdefault(checksum, path.read_bytes())

        imported_sources: list[ImportSource] = []
        proposals: list[ProposedFact] = []
        duplicates: list[DuplicateSource] = []
        for checksum, paths in sorted(grouped.items()):
            data = content_by_checksum[checksum]
            source_id = f"SRC-{checksum[:16]}"
            media_type = _detect_media_type(data)
            status = ExtractionStatus.EXTRACTED
            extraction_error: str | None = None
            output = ExtractionOutput(
                text="",
                extractor="career-agent-unsupported",
                extractor_version="1",
                blocks=(),
                ocr_status="not_applicable",
            )
            try:
                output = _extract_text(data, media_type)
                if output.ocr_status == "unsupported":
                    status = ExtractionStatus.FAILED
                    extraction_error = "ocr_required"
            except (
                ValueError,
                UnicodeError,
                zipfile.BadZipFile,
                KeyError,
                ElementTree.ParseError,
                RuntimeError,
            ) as error:
                status = (
                    ExtractionStatus.UNSUPPORTED
                    if media_type == "application/octet-stream"
                    else ExtractionStatus.FAILED
                )
                extraction_error = type(error).__name__
            source_paths = tuple(str(path) for path in paths)
            source = ImportSource(
                source_id=source_id,
                checksum=checksum,
                source_paths=source_paths,
                original_filenames=tuple(path.name for path in paths),
                media_type=media_type,
                size_bytes=len(data),
                extraction_status=status,
                extraction_error=extraction_error,
                extracted_text=output.text,
                extracted_at=datetime.now(UTC),
                extractor=output.extractor,
                extractor_version=output.extractor_version,
                normalized_text_checksum=(
                    hashlib.sha256(output.text.encode()).hexdigest()
                    if status is ExtractionStatus.EXTRACTED
                    else None
                ),
                blocks=output.blocks,
                warnings=output.warnings,
                ocr_status=output.ocr_status,
            )
            imported_sources.append(source)
            if len(paths) > 1:
                duplicates.append(DuplicateSource(source_id=source_id, source_paths=source_paths))
            locator = f"{paths[0].name}#extracted-text"
            reference = SourceReference(
                source_id=source_id,
                locator=locator,
                checksum=checksum,
            )
            for key, value, supported in extract_declared_facts(output.text):
                proposals.append(
                    ProposedFact(
                        proposal_id=_proposal_id(key, value, source_id),
                        key=key,
                        value=value,
                        sources=(reference,),
                        supported=supported,
                    )
                )

        preview = ImportPreview(
            run_id=run_id,
            source_files=tuple(imported_sources),
            duplicates=tuple(duplicates),
            proposed_facts=tuple(proposals),
            conflicts=build_conflicts(proposals),
        )
        preview_path = safe_resolve(
            self.root,
            PurePath("runs", run_id, "import-preview.json"),
        )
        self._ensure_private_directory(preview_path.parent)
        atomic_write_json(preview_path, preview)
        return preview

    def result_path(self, run_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath("runs", run_id, "import-result.json"),
        )

    def persist_result(self, result: ImportResult) -> None:
        path = self.result_path(result.run_id)
        self._ensure_private_directory(path.parent)
        atomic_write_json(path, result)

    def apply(
        self,
        run_id: str,
        source_ids: Sequence[str] | None = None,
    ) -> ImportResult:
        preview_path = safe_resolve(
            self.root,
            PurePath("runs", run_id, "import-preview.json"),
        )
        result_path = self.result_path(run_id)
        try:
            existing = ImportResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            if source_ids is not None and set(source_ids) != {
                source.source_id for source in existing.imported_sources
            }:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Import run was already applied with a different source selection",
                    {"run_id": run_id},
                )
            return existing
        except FileNotFoundError:
            pass
        except ValidationError as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Import result is unreadable or invalid",
                {"run_id": run_id},
            ) from error
        try:
            preview = ImportPreview.model_validate_json(preview_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Import preview run does not exist",
                {"run_id": run_id},
            ) from error
        except ValidationError as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Import preview is unreadable or invalid",
                {"run_id": run_id},
            ) from error

        available_ids = {source.source_id for source in preview.source_files}
        selected_ids = available_ids if source_ids is None else set(source_ids)
        unknown_ids = selected_ids.difference(available_ids)
        if unknown_ids:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Import selection contains an unknown source",
                {"source_ids": sorted(unknown_ids)},
            )
        if not selected_ids:
            raise CareerError(ErrorCode.INVALID_INPUT, "Import selection cannot be empty")

        source_payloads: dict[str, bytes] = {}
        for source in preview.source_files:
            if source.source_id not in selected_ids:
                continue
            original = Path(source.source_paths[0])
            data = original.read_bytes()
            if hashlib.sha256(data).hexdigest() != source.checksum:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Import source changed after preview",
                    {"source_id": source.source_id},
                )
            source_payloads[source.source_id] = data

        imported: list[ImportedSource] = []
        applied_proposals: list[ProposedFact] = []
        fact_ids: dict[str, str] = {}
        for proposal in preview.proposed_facts:
            if not any(source.source_id in selected_ids for source in proposal.sources):
                continue
            fact_ids[proposal.proposal_id] = self.registry.allocate_fact_id()
            applied_proposals.append(
                proposal.model_copy(update={"fact_id": fact_ids[proposal.proposal_id]})
            )

        for source in preview.source_files:
            if source.source_id not in selected_ids:
                continue
            filename = sanitize_untrusted_filename(source.original_filenames[0])
            destination = safe_resolve(
                self.root,
                PurePath("resources", "imports", source.source_id, filename),
            )
            self._ensure_private_directory(destination.parent)
            if destination.exists():
                if sha256_file(destination) != source.checksum:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Stored import checksum mismatch",
                        {"source_id": source.source_id},
                    )
            else:
                atomic_write_bytes(destination, source_payloads[source.source_id], mode=0o600)
            extracted_text_path: Path | None = None
            if source.extraction_status is ExtractionStatus.EXTRACTED:
                extracted_text_path = safe_resolve(
                    self.root,
                    PurePath(
                        "resources",
                        "imports",
                        source.source_id,
                        ".extracted",
                        "normalized.txt",
                    ),
                )
                self._ensure_private_directory(extracted_text_path.parent)
                encoded_text = source.extracted_text.encode()
                if source.normalized_text_checksum != hashlib.sha256(encoded_text).hexdigest():
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Extracted text checksum changed before import apply",
                        {"source_id": source.source_id},
                    )
                if extracted_text_path.exists():
                    if hashlib.sha256(extracted_text_path.read_bytes()).hexdigest() != (
                        source.normalized_text_checksum
                    ):
                        raise CareerError(
                            ErrorCode.INTEGRITY_ERROR,
                            "Stored extracted text checksum mismatch",
                            {"source_id": source.source_id},
                        )
                else:
                    atomic_write_bytes(extracted_text_path, encoded_text, mode=0o600)
            imported.append(
                ImportedSource(
                    source_id=source.source_id,
                    checksum=source.checksum,
                    source_paths=source.source_paths,
                    stored_path=str(destination),
                    media_type=source.media_type,
                    extraction_status=source.extraction_status,
                    extracted_at=source.extracted_at,
                    extracted_text_path=(
                        str(extracted_text_path) if extracted_text_path is not None else None
                    ),
                    normalized_text_checksum=source.normalized_text_checksum,
                    extractor=source.extractor,
                    extractor_version=source.extractor_version,
                    blocks=source.blocks,
                    warnings=source.warnings,
                    ocr_status=source.ocr_status,
                )
            )

        conflicts = build_conflicts(applied_proposals)
        result = ImportResult(
            run_id=run_id,
            imported_sources=tuple(imported),
            proposed_facts=tuple(applied_proposals),
            conflicts=conflicts,
        )
        self.persist_result(result)
        return result

    def _ensure_private_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            return
        relative = path.relative_to(self.root)
        current = self.root
        current.chmod(0o700)
        for component in relative.parts:
            current = current / component
            current.chmod(0o700)
