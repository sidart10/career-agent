"""Grounded, append-only document release and upload-copy operations."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePath
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from career_agent.documents.filenames import upload_filename
from career_agent.documents.pdf_validation import (
    PdfValidator,
    ValidationReport,
    ValidationRequest,
)
from career_agent.documents.render import DocumentRenderer, RenderResult, StructuredDocument
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationManifest, ApplicationStage
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.profile import ConfirmationState
from career_agent.models.release import (
    ArtifactRecord,
    ArtifactType,
    ClaimReference,
    DocumentRelease,
    UploadArtifact,
    ValidationSummary,
)
from career_agent.services.applications import ApplicationService
from career_agent.services.opportunities import OpportunityService
from career_agent.services.profile import ProfileService
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import ApplicationLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry
from career_agent.storage.repository import ApplicationRepository


class ReleaseArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: ArtifactType
    draft_relative_path: str = Field(min_length=1)
    validation: ValidationRequest | None = None


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifacts: tuple[ReleaseArtifactRequest, ...] = Field(min_length=1)
    claims: tuple[ClaimReference, ...] = ()
    idempotency_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def artifact_and_claim_identities_are_unique(self) -> ReleaseRequest:
        artifact_types = [artifact.artifact_type for artifact in self.artifacts]
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(artifact_types) != len(set(artifact_types)):
            raise ValueError("release artifact types must be unique")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("release claim IDs must be unique")
        return self


class ReleaseVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str
    release_id: str
    verified: bool
    artifact_checksums: dict[str, str]


_CANONICAL_NAMES = {
    ArtifactType.RESUME_PDF: "resume.pdf",
    ArtifactType.COVER_LETTER_PDF: "cover-letter.pdf",
    ArtifactType.RESUME_DOCX: "resume.docx",
    ArtifactType.COVER_LETTER_DOCX: "cover-letter.docx",
}

_UPLOAD_LABELS = {
    ArtifactType.RESUME_PDF: "Resume",
    ArtifactType.COVER_LETTER_PDF: "Cover_Letter",
    ArtifactType.RESUME_DOCX: "Resume",
    ArtifactType.COVER_LETTER_DOCX: "Cover_Letter",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class DocumentService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)
        self.applications = ApplicationService(self.root)
        self.repository = ApplicationRepository(self.root)
        self.profile = ProfileService(self.root)
        self.opportunities = OpportunityService(self.root)
        self.validator = PdfValidator(self.root)
        self.renderer = DocumentRenderer(self.root)

    def render_draft(
        self,
        application_id: str,
        draft: StructuredDocument,
    ) -> RenderResult:
        self.applications.load(application_id)
        return self.renderer.render_draft(application_id, draft)

    def validate(
        self,
        application_id: str,
        artifact: Path,
        request: ValidationRequest,
    ) -> ValidationReport:
        self.applications.load(application_id)
        return self.validator.validate(application_id, artifact, request)

    def _release_dir(self, application_id: str, release_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath("applications", application_id, "releases", release_id),
        )

    def _manifest_path(self, application_id: str, release_id: str) -> Path:
        return safe_resolve(self._release_dir(application_id, release_id), PurePath("release.json"))

    def list(self, application_id: str) -> tuple[DocumentRelease, ...]:
        self.applications.load(application_id)
        releases_root = safe_resolve(
            self.root,
            PurePath("applications", application_id, "releases"),
        )
        releases: list[DocumentRelease] = []
        for path in sorted(releases_root.glob("REL-*/release.json")):
            release_id = path.parent.name
            self.verify_release(application_id, release_id)
            releases.append(self.load(application_id, release_id))
        return tuple(releases)

    def load(self, application_id: str, release_id: str) -> DocumentRelease:
        try:
            return DocumentRelease.model_validate_json(
                self._manifest_path(application_id, release_id).read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Document release does not exist",
                {"application_id": application_id, "release_id": release_id},
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Document release manifest is unreadable or invalid",
                {"application_id": application_id, "release_id": release_id},
            ) from error

    def _validate_claims(self, claims: tuple[ClaimReference, ...]) -> None:
        profile = self.profile.load_state()
        confirmed = {
            fact.fact_id: fact
            for fact in profile.facts
            if fact.confirmation_state is ConfirmationState.CONFIRMED
        }
        confirmed_sources = {
            (source.source_id, source.locator, source.checksum)
            for fact in confirmed.values()
            for source in fact.sources
        }
        imported_sources = {
            source.source_id: source.checksum for source in profile.imported_sources
        }
        for claim in claims:
            missing = [fact_id for fact_id in claim.fact_ids if fact_id not in confirmed]
            if missing:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Release claim references an unconfirmed fact",
                    {"claim_id": claim.claim_id, "fact_ids": missing},
                )
            for source in claim.evidence_sources:
                exact = (source.source_id, source.locator, source.checksum) in confirmed_sources
                imported_checksum = imported_sources.get(source.source_id)
                imported = imported_checksum is not None and source.checksum in {
                    None,
                    imported_checksum,
                }
                if not exact and not imported:
                    raise CareerError(
                        ErrorCode.INVALID_INPUT,
                        "Release claim references unknown imported evidence",
                        {"claim_id": claim.claim_id, "source_id": source.source_id},
                    )

    def _draft_path(self, application_id: str, relative: str) -> Path:
        application_root = safe_resolve(
            self.root,
            PurePath("applications", application_id),
        )
        path = safe_resolve(application_root, PurePath(relative))
        drafts_root = safe_resolve(application_root, PurePath("drafts"))
        if not path.is_relative_to(drafts_root):
            raise CareerError(
                ErrorCode.UNSAFE_PATH,
                "Release artifacts must come from the application's drafts",
                {"application_id": application_id},
            )
        return path

    def _validate_render_provenance(
        self,
        application_id: str,
        artifact: ReleaseArtifactRequest,
        path: Path,
    ) -> None:
        record_path = path.with_suffix(".render.json")
        try:
            result = RenderResult.model_validate_json(record_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "PDF release requires canonical LaTeX render provenance",
                {"artifact_type": artifact.artifact_type.value},
            ) from error
        expected_document_type = (
            "resume" if artifact.artifact_type is ArtifactType.RESUME_PDF else "cover_letter"
        )
        artifact_relative = path.relative_to(self.root).as_posix()
        source = safe_resolve(self.root, PurePath(result.source_path))
        source_is_draft = source.is_relative_to(
            safe_resolve(
                self.root,
                PurePath("applications", application_id, "drafts"),
            )
        )
        valid = (
            result.application_id == application_id
            and result.document_type == expected_document_type
            and result.artifact_path == artifact_relative
            and result.artifact_checksum == sha256_file(path)
            and source_is_draft
            and source.is_file()
            and result.source_checksum == sha256_file(source)
        )
        if not valid:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "PDF render provenance does not match the application draft",
                {"artifact_type": artifact.artifact_type.value},
            )

    def _validate_artifact(
        self,
        application_id: str,
        artifact: ReleaseArtifactRequest,
    ) -> ValidationReport | dict[str, object]:
        path = self._draft_path(application_id, artifact.draft_relative_path)
        if not path.is_file():
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Draft artifact does not exist",
                {"artifact_type": artifact.artifact_type.value},
            )
        if artifact.artifact_type in {
            ArtifactType.RESUME_PDF,
            ArtifactType.COVER_LETTER_PDF,
        }:
            self._validate_render_provenance(application_id, artifact, path)
            if artifact.validation is None:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "PDF release requires a validation request",
                    {"artifact_type": artifact.artifact_type.value},
                )
            report = self.validator.validate(application_id, path, artifact.validation)
            if not report.passed:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Document failed the mechanical release gate and remains a draft",
                    {"artifact_type": artifact.artifact_type.value},
                )
            return report
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Draft artifact is unreadable",
                {"artifact_type": artifact.artifact_type.value},
            ) from error
        passed = False
        if payload.startswith(b"PK"):
            try:
                with zipfile.ZipFile(path) as archive:
                    members = set(archive.namelist())
                    required = {
                        "[Content_Types].xml",
                        "word/document.xml",
                    }
                    if required.issubset(members) and archive.testzip() is None:
                        ElementTree.fromstring(archive.read("[Content_Types].xml"))
                        ElementTree.fromstring(archive.read("word/document.xml"))
                        passed = True
            except (OSError, ElementTree.ParseError, zipfile.BadZipFile):
                passed = False
        if not passed:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "DOCX artifact is unreadable and remains a draft",
                {"artifact_type": artifact.artifact_type.value},
            )
        return {"passed": True, "engine": "docx-container", "artifact_type": artifact.artifact_type}

    @staticmethod
    def _request_digest(
        request: ReleaseRequest,
        checksums: dict[ArtifactType, str],
    ) -> str:
        payload = {
            "request": request.model_dump(mode="json", exclude={"idempotency_key"}),
            "checksums": {key.value: value for key, value in checksums.items()},
        }
        return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))

    def _attach_release(self, application_id: str, release_id: str) -> None:
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="release.attach",
            idempotency_key=f"release-attach:{application_id}:{release_id}",
            status=OperationStatus.STARTED,
        )

        def attach(current: ApplicationManifest | None) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            if release_id in current.release_ids:
                return current
            return current.model_copy(
                update={
                    "release_ids": (*current.release_ids, release_id),
                    "current_release_id": release_id,
                    "updated_at": datetime.now(UTC),
                }
            )

        self.repository.mutate(application_id, operation, attach)

    @staticmethod
    def _release_operation_key(release: DocumentRelease) -> str:
        return f"release-create:{release.application_id}:{release.idempotency_digest}"

    def _repair_or_verify_release_commit(self, release: DocumentRelease) -> None:
        operation_key = self._release_operation_key(release)
        manifest_path = self._manifest_path(release.application_id, release.release_id)
        actual_checksum = sha256_file(manifest_path)
        replay = self.journal.replay(operation_key)
        if replay is not None:
            if replay.result.get("manifest_checksum") != actual_checksum:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Release manifest checksum does not match its journal seal",
                    {"release_id": release.release_id},
                )
            return
        active = self.journal.operation_for_key(operation_key)
        if active is None:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Release manifest has no journal provenance",
                {"release_id": release.release_id},
            )
        checkpoint = self.journal.checkpoint_data(active.run_id, "release-manifest")
        if checkpoint is None or checkpoint.get("checksum") != actual_checksum:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Interrupted release manifest does not match its checkpoint",
                {"release_id": release.release_id},
            )
        self.journal.commit(
            active.run_id,
            {
                "release_id": release.release_id,
                "manifest_checksum": actual_checksum,
                "result_references": [release.release_id],
            },
        )

    def create_release(
        self,
        application_id: str,
        request: ReleaseRequest,
    ) -> DocumentRelease:
        self.applications.load(application_id)
        idempotency_digest = _sha256_text(request.idempotency_key)
        existing = next(
            (
                release
                for release in self.list(application_id)
                if release.idempotency_digest == idempotency_digest
            ),
            None,
        )
        if existing is not None:
            self.verify_release(application_id, existing.release_id)
            self._attach_release(application_id, existing.release_id)
            return existing
        self._validate_claims(request.claims)
        validation_results: list[ValidationReport | dict[str, object]] = []
        draft_paths: list[Path] = []
        checksums: dict[ArtifactType, str] = {}
        for artifact in request.artifacts:
            draft_path = self._draft_path(application_id, artifact.draft_relative_path)
            validation_results.append(self._validate_artifact(application_id, artifact))
            draft_paths.append(draft_path)
            checksums[artifact.artifact_type] = sha256_file(draft_path)
        request_digest = self._request_digest(request, checksums)
        operation_key = f"release-create:{application_id}:{idempotency_digest}"
        active = self.journal.operation_for_key(operation_key)
        reserved = (
            self.journal.checkpoint_data(active.run_id, "release-identity")
            if active is not None
            else None
        )
        if reserved is not None and reserved.get("request_digest") != request_digest:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Idempotency key is already bound to a different release request",
                {"application_id": application_id},
            )
        reserved_id = reserved.get("release_id") if reserved is not None else None
        if reserved_id is not None and not isinstance(reserved_id, str):
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Reserved release identity is invalid")
        release_id = reserved_id or self.registry.allocate_local_id(application_id, "release")
        run_id = active.run_id if active is not None else self.registry.allocate_run_id()
        operation = active or OperationRecord(
            run_id=run_id,
            operation="release.create",
            idempotency_key=operation_key,
            status=OperationStatus.STARTED,
        )
        self.journal.begin(operation)
        self.journal.checkpoint(
            operation.run_id,
            "release-identity",
            {"release_id": release_id, "request_digest": request_digest},
        )
        with ApplicationLock(self.root, application_id, run_id=operation.run_id):
            release_dir = self._release_dir(application_id, release_id)
            records: list[ArtifactRecord] = []
            summaries: list[ValidationSummary] = []
            for artifact, draft_path, validation in zip(
                request.artifacts,
                draft_paths,
                validation_results,
                strict=True,
            ):
                destination = safe_resolve(
                    release_dir,
                    PurePath(_CANONICAL_NAMES[artifact.artifact_type]),
                )
                atomic_write_bytes(destination, draft_path.read_bytes())
                report_path = safe_resolve(
                    release_dir,
                    PurePath(f"{artifact.artifact_type.value}.validation.json"),
                )
                atomic_write_json(report_path, validation)
                records.append(
                    ArtifactRecord(
                        artifact_type=artifact.artifact_type,
                        relative_path=destination.relative_to(self.root).as_posix(),
                        checksum=sha256_file(destination),
                    )
                )
                summaries.append(
                    ValidationSummary(
                        artifact_type=artifact.artifact_type,
                        passed=True,
                        report_path=report_path.relative_to(self.root).as_posix(),
                        report_checksum=sha256_file(report_path),
                    )
                )
            release = DocumentRelease(
                release_id=release_id,
                application_id=application_id,
                artifacts=tuple(records),
                claims=request.claims,
                validation_reports=tuple(summaries),
                request_digest=request_digest,
                idempotency_digest=idempotency_digest,
            )
            manifest_path = self._manifest_path(application_id, release_id)
            if manifest_path.exists():
                current = self.load(application_id, release_id)
                if current != release:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Release identity already contains different content",
                        {"release_id": release_id},
                    )
            else:
                atomic_write_json(manifest_path, release)
            manifest_checksum = sha256_file(manifest_path)
            self.journal.checkpoint(
                operation.run_id,
                "release-manifest",
                {"checksum": manifest_checksum},
            )
        self._attach_release(application_id, release_id)
        self.journal.commit(
            operation.run_id,
            {
                "release_id": release_id,
                "manifest_checksum": manifest_checksum,
                "result_references": [release_id],
            },
        )
        return release

    def verify_release(self, application_id: str, release_id: str) -> ReleaseVerification:
        manifest_path = self._manifest_path(application_id, release_id)
        try:
            release = self.load(application_id, release_id)
        except CareerError as error:
            if error.code is ErrorCode.INTEGRITY_ERROR and manifest_path.is_file():
                self._quarantine_path(
                    application_id,
                    release_id,
                    artifact_type="release_manifest",
                    expected_checksum="valid sealed manifest",
                    path=manifest_path,
                    actual_checksum=sha256_file(manifest_path),
                )
            raise
        try:
            self._repair_or_verify_release_commit(release)
        except CareerError:
            self._quarantine_path(
                application_id,
                release.release_id,
                artifact_type="release_manifest",
                expected_checksum="journal seal",
                path=manifest_path,
                actual_checksum=sha256_file(manifest_path),
            )
            raise
        checksums: dict[str, str] = {}
        for artifact in release.artifacts:
            path = safe_resolve(self.root, PurePath(artifact.relative_path))
            actual = sha256_file(path) if path.is_file() else "missing"
            checksums[artifact.artifact_type.value] = actual
            if actual != artifact.checksum:
                self._quarantine(application_id, release, artifact, path, actual)
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Release checksum mismatch; artifact was quarantined",
                    {
                        "application_id": application_id,
                        "release_id": release_id,
                        "artifact_type": artifact.artifact_type.value,
                    },
                )
        for summary in release.validation_reports:
            report_path = safe_resolve(self.root, PurePath(summary.report_path))
            actual = sha256_file(report_path) if report_path.is_file() else "missing"
            if actual != summary.report_checksum:
                self._quarantine_path(
                    application_id,
                    release.release_id,
                    artifact_type=f"{summary.artifact_type.value}_validation",
                    expected_checksum=summary.report_checksum,
                    path=report_path,
                    actual_checksum=actual,
                )
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Release validation report checksum mismatch",
                    {"release_id": release_id},
                )
        return ReleaseVerification(
            application_id=application_id,
            release_id=release_id,
            verified=True,
            artifact_checksums=checksums,
        )

    def _quarantine(
        self,
        application_id: str,
        release: DocumentRelease,
        artifact: ArtifactRecord,
        path: Path,
        actual_checksum: str,
    ) -> None:
        self._quarantine_path(
            application_id,
            release.release_id,
            artifact_type=artifact.artifact_type.value,
            expected_checksum=artifact.checksum,
            path=path,
            actual_checksum=actual_checksum,
        )

    def _quarantine_path(
        self,
        application_id: str,
        release_id: str,
        *,
        artifact_type: str,
        expected_checksum: str,
        path: Path,
        actual_checksum: str,
    ) -> None:
        now = datetime.now(UTC)
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="release.quarantine",
            idempotency_key=(f"release-quarantine:{application_id}:{release_id}:{artifact_type}"),
            status=OperationStatus.STARTED,
        )
        quarantine = safe_resolve(
            self.root,
            PurePath(
                "applications",
                application_id,
                "quarantine",
                f"{release_id}-{path.name}",
            ),
        )
        with ApplicationLock(self.root, application_id, run_id=run_id):
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                os.replace(path, quarantine)
            incident_path = quarantine.with_suffix(f"{quarantine.suffix}.json")
            atomic_write_json(
                incident_path,
                {
                    "application_id": application_id,
                    "release_id": release_id,
                    "artifact_type": artifact_type,
                    "expected_checksum": expected_checksum,
                    "actual_checksum": actual_checksum,
                    "quarantined_at": now.isoformat(),
                },
            )
            uploads = safe_resolve(
                self.root,
                PurePath("applications", application_id, "uploads"),
            )
            for record_path in uploads.glob("*.json"):
                try:
                    upload = UploadArtifact.model_validate_json(
                        record_path.read_text(encoding="utf-8")
                    )
                except (OSError, ValidationError, json.JSONDecodeError):
                    continue
                if upload.release_id == release_id and upload.valid:
                    atomic_write_json(
                        record_path,
                        upload.model_copy(
                            update={
                                "valid": False,
                                "invalidated_at": now,
                                "invalidation_reason": "source release checksum mismatch",
                                "updated_at": now,
                            }
                        ),
                    )

        def invalidate(current: ApplicationManifest | None) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            target = (
                ApplicationStage.PREPARING
                if current.stage in {ApplicationStage.READY_FOR_REVIEW, ApplicationStage.APPROVED}
                else current.stage
            )
            return current.model_copy(
                update={
                    "stage": target,
                    "approval_invalidated_at": now,
                    "approval_invalidation_reason": "release checksum mismatch",
                    "updated_at": now,
                }
            )

        self.repository.mutate(application_id, operation, invalidate)

    def prepare_upload_copy(
        self,
        application_id: str,
        release_id: str,
        artifact_type: ArtifactType,
    ) -> UploadArtifact:
        self.verify_release(application_id, release_id)
        release = self.load(application_id, release_id)
        artifact = next(
            (item for item in release.artifacts if item.artifact_type is artifact_type),
            None,
        )
        if artifact is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Release does not contain the requested artifact type",
                {"artifact_type": artifact_type.value},
            )
        application = self.applications.load(application_id)
        opportunity = self.opportunities.get(application.opportunity_id)
        facts = {fact.key: fact.value for fact in self.profile.load_state().facts}
        first_name = facts.get("identity.first_name")
        last_name = facts.get("identity.last_name")
        legal_name = facts.get("identity.legal_name")
        if (not isinstance(first_name, str) or not isinstance(last_name, str)) and isinstance(
            legal_name, str
        ):
            name_parts = legal_name.split()
            if len(name_parts) >= 2:
                first_name, last_name = name_parts[0], name_parts[-1]
        if not isinstance(first_name, str) or not isinstance(last_name, str):
            raise CareerError(
                ErrorCode.NOT_READY,
                "Confirmed first and last name are required for upload filenames",
            )
        extension = Path(artifact.relative_path).suffix.lstrip(".")
        filename = upload_filename(
            first_name=first_name,
            last_name=last_name,
            company=opportunity.company,
            role=opportunity.title,
            artifact_label=_UPLOAD_LABELS[artifact_type],
            checksum=artifact.checksum,
            extension=extension,
        )
        destination = safe_resolve(
            self.root,
            PurePath("applications", application_id, "uploads", filename),
        )
        source = safe_resolve(self.root, PurePath(artifact.relative_path))
        record_path = destination.with_suffix(f"{destination.suffix}.json")
        upload = UploadArtifact(
            application_id=application_id,
            release_id=release_id,
            artifact_type=artifact_type,
            filename=filename,
            relative_path=destination.relative_to(self.root).as_posix(),
            record_path=record_path.relative_to(self.root).as_posix(),
            source_relative_path=artifact.relative_path,
            source_checksum=artifact.checksum,
        )
        run_id = self.registry.allocate_run_id()
        with ApplicationLock(self.root, application_id, run_id=run_id):
            atomic_write_bytes(destination, source.read_bytes())
            if sha256_file(destination) != artifact.checksum:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Upload copy checksum does not match its source release",
                    {"release_id": release_id, "artifact_type": artifact_type.value},
                )
            atomic_write_json(record_path, upload)
        return upload
