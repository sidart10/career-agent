"""Copy-first career evidence import and deterministic fact proposals."""

from __future__ import annotations

import hashlib
import json
import os
import warnings
import zipfile
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from io import BytesIO
from pathlib import Path, PurePath
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


class ImportedSource(_ContractModel):
    source_id: str
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_paths: tuple[str, ...]
    stored_path: str
    media_type: str
    extraction_status: ExtractionStatus


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


def _extract_text(data: bytes, media_type: str) -> str:
    if media_type == "text/plain":
        return data.decode("utf-8")
    if media_type == "application/pdf":
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"builtin type (SwigPyPacked|SwigPyObject|swigvarlink).*",
                category=DeprecationWarning,
            )
            import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]
            return "\n".join(page.get_text() for page in document)
    if media_type == DOCX_MEDIA_TYPE:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            document_xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(document_xml)
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        return "\n".join(element.text or "" for element in root.iter(f"{namespace}t"))
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
            text = ""
            try:
                text = _extract_text(data, media_type)
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
                extracted_text=text,
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
            for key, value, supported in extract_declared_facts(text):
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

    def apply(self, run_id: str) -> ImportResult:
        preview_path = safe_resolve(
            self.root,
            PurePath("runs", run_id, "import-preview.json"),
        )
        result_path = self.result_path(run_id)
        try:
            return ImportResult.model_validate_json(result_path.read_text(encoding="utf-8"))
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

        source_payloads: dict[str, bytes] = {}
        for source in preview.source_files:
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
            fact_ids[proposal.proposal_id] = self.registry.allocate_fact_id()
            applied_proposals.append(
                proposal.model_copy(update={"fact_id": fact_ids[proposal.proposal_id]})
            )

        for source in preview.source_files:
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
            imported.append(
                ImportedSource(
                    source_id=source.source_id,
                    checksum=source.checksum,
                    source_paths=source.source_paths,
                    stored_path=str(destination),
                    media_type=source.media_type,
                    extraction_status=source.extraction_status,
                )
            )

        conflicts = tuple(
            conflict.model_copy(
                update={
                    "alternatives": tuple(
                        alternative.model_copy(
                            update={"fact_id": fact_ids[alternative.proposal_id]}
                        )
                        for alternative in conflict.alternatives
                    )
                }
            )
            for conflict in preview.conflicts
        )
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
