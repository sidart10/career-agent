"""Canonical, digest-bound final review payloads for one submission attempt."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path, PurePath, PurePosixPath
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from career_agent.documents.release import DocumentService
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import RetentionClass
from career_agent.models.application import ApplicationStage
from career_agent.models.base import (
    ApplicationId,
    PersistedModel,
    PostingSnapshotId,
    SubmissionId,
)
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.release import ArtifactType, ReleaseId, UploadArtifact
from career_agent.models.submission import SubmissionResolution, SubmissionStatus
from career_agent.security.content import sanitize_untrusted_filename
from career_agent.security.prohibited_values import reject_prohibited
from career_agent.security.urls import canonicalize_public_http_url
from career_agent.services.answers import AnswerService
from career_agent.services.applications import ApplicationService
from career_agent.services.postings import PostingAvailability, PostingService
from career_agent.storage.atomic import atomic_write_bytes, atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import ApplicationLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PayloadPosting(_ContractModel):
    snapshot_id: PostingSnapshotId
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    freshness: Literal["current"] = "current"


class PayloadArtifact(_ContractModel):
    artifact_type: ArtifactType
    filename: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_release_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("filename")
    @classmethod
    def filename_is_a_basename(cls, value: str) -> str:
        if PurePosixPath(value).name != value:
            raise ValueError("artifact filename must not contain a path")
        return value


class AttachmentCategory(StrEnum):
    PORTFOLIO = "portfolio"
    CERTIFICATE = "certificate"
    TRANSCRIPT = "transcript"
    REFERENCE = "reference"
    WRITING_SAMPLE = "writing_sample"
    OTHER = "other"


class AttachmentRequest(_ContractModel):
    attachment_id: str = Field(min_length=1)
    category: AttachmentCategory
    source_relative_path: str = Field(min_length=1)
    upload_filename: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    permission_reference: str | None = None

    @field_validator("source_relative_path")
    @classmethod
    def source_path_is_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("attachment source path must remain relative")
        return value

    @model_validator(mode="after")
    def references_require_permission(self) -> AttachmentRequest:
        if self.category is AttachmentCategory.REFERENCE and not self.permission_reference:
            raise ValueError("reference attachment requires permission evidence")
        return self


class PayloadAttachment(_ContractModel):
    attachment_id: str = Field(min_length=1)
    category: AttachmentCategory
    filename: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_relative_path: str = Field(min_length=1)
    permission_reference: str | None = None

    @field_validator("filename")
    @classmethod
    def filename_is_a_basename(cls, value: str) -> str:
        if PurePosixPath(value).name != value:
            raise ValueError("attachment filename must not contain a path")
        return value

    @field_validator("relative_path", "source_relative_path")
    @classmethod
    def paths_are_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("attachment path must remain relative")
        return value

    @field_validator("relative_path")
    @classmethod
    def path_is_relative_and_contained(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact path must remain relative")
        return value


class PayloadField(_ContractModel):
    field_id: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    value: JsonValue
    answer_id: str | None = Field(default=None, pattern=r"^ANS-\d{4}$")
    retention_class: RetentionClass
    requires_final_review: bool = False
    conditional: bool = False
    exact_sensitive_history_opt_in: bool = False

    @model_validator(mode="after")
    def sensitive_history_requires_explicit_opt_in(self) -> PayloadField:
        if (
            self.retention_class is RetentionClass.SENSITIVE
            and not self.exact_sensitive_history_opt_in
        ):
            raise ValueError("sensitive payload history requires explicit opt-in")
        return self


class PayloadAttestation(_ContractModel):
    attestation_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    completed_by_human: Literal[True]
    source_reference: str = Field(min_length=1)


class CanonicalSubmissionPayload(PersistedModel):
    payload_version: Literal[1] = 1
    digest_algorithm: Literal["sha256-v1"] = "sha256-v1"
    application_id: ApplicationId
    submission_id: SubmissionId
    posting: PayloadPosting
    release_id: ReleaseId
    artifacts: tuple[PayloadArtifact, ...] = Field(min_length=1)
    attachments: tuple[PayloadAttachment, ...] = ()
    fields: tuple[PayloadField, ...] = ()
    attestations: tuple[PayloadAttestation, ...] = ()
    anomalies: tuple[str, ...] = ()
    evidence_limitations: tuple[str, ...] = ()
    destination: AnyHttpUrl
    irreversible_action: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def material_identities_are_unique(self) -> CanonicalSubmissionPayload:
        artifacts = [item.artifact_type for item in self.artifacts]
        attachments = [item.attachment_id for item in self.attachments]
        fields = [item.field_id for item in self.fields]
        attestations = [item.attestation_id for item in self.attestations]
        if len(artifacts) != len(set(artifacts)):
            raise ValueError("payload artifact types must be unique")
        if len(attachments) != len(set(attachments)):
            raise ValueError("payload attachment IDs must be unique")
        if len(fields) != len(set(fields)):
            raise ValueError("payload field IDs must be unique")
        if len(attestations) != len(set(attestations)):
            raise ValueError("payload attestation IDs must be unique")
        return self


class PrepareSubmissionRequest(_ContractModel):
    release_id: ReleaseId
    upload_record_paths: tuple[str, ...] = Field(min_length=1)
    attachments: tuple[AttachmentRequest, ...] = ()
    fields: tuple[PayloadField, ...] = ()
    attestations: tuple[PayloadAttestation, ...] = ()
    anomalies: tuple[str, ...] = ()
    evidence_limitations: tuple[str, ...] = ()
    destination: str = Field(min_length=1)
    irreversible_action: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class PayloadService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.applications = ApplicationService(self.root)
        self.answers = AnswerService(self.root)
        self.postings = PostingService(self.root)
        self.documents = DocumentService(self.root)
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    @staticmethod
    def material(payload: CanonicalSubmissionPayload) -> dict[str, object]:
        return {
            "payload_version": payload.payload_version,
            "digest_algorithm": payload.digest_algorithm,
            "application_id": payload.application_id,
            "submission_id": payload.submission_id,
            "posting": payload.posting.model_dump(mode="json"),
            "release_id": payload.release_id,
            "artifacts": [
                item.model_dump(mode="json")
                for item in sorted(
                    payload.artifacts,
                    key=lambda item: (item.artifact_type.value, item.filename),
                )
            ],
            "attachments": [
                item.model_dump(mode="json")
                for item in sorted(
                    payload.attachments,
                    key=lambda item: item.attachment_id,
                )
            ],
            "fields": [
                item.model_dump(mode="json")
                for item in sorted(payload.fields, key=lambda item: item.field_id)
            ],
            "attestations": [
                item.model_dump(mode="json")
                for item in sorted(
                    payload.attestations,
                    key=lambda item: item.attestation_id,
                )
            ],
            "anomalies": sorted(payload.anomalies),
            "evidence_limitations": sorted(payload.evidence_limitations),
            "destination": str(payload.destination),
            "irreversible_action": payload.irreversible_action,
        }

    @classmethod
    def serialize(cls, payload: CanonicalSubmissionPayload) -> bytes:
        return json.dumps(
            cls.material(payload),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @classmethod
    def digest(cls, payload: CanonicalSubmissionPayload) -> str:
        return hashlib.sha256(cls.serialize(payload)).hexdigest()

    def path(self, application_id: str, submission_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath(
                "applications",
                application_id,
                "submissions",
                submission_id,
                "payload.json",
            ),
        )

    @staticmethod
    def _operation_key(application_id: str, idempotency_digest: str) -> str:
        return f"submission-prepare:{application_id}:{idempotency_digest}"

    def _verified_uploads(
        self,
        application_id: str,
        release_id: str,
        record_paths: tuple[str, ...],
    ) -> tuple[PayloadArtifact, ...]:
        release = self.documents.load(application_id, release_id)
        release_artifacts = {item.artifact_type: item for item in release.artifacts}
        uploads_root = safe_resolve(
            self.root,
            PurePath("applications", application_id, "uploads"),
        )
        artifacts: list[PayloadArtifact] = []
        for record_relative in record_paths:
            record_path = safe_resolve(self.root, PurePath(record_relative))
            if not record_path.is_relative_to(uploads_root):
                raise CareerError(
                    ErrorCode.UNSAFE_PATH,
                    "Submission uploads must belong to the application",
                    {"application_id": application_id},
                )
            try:
                upload = UploadArtifact.model_validate_json(record_path.read_text())
            except (OSError, ValidationError, json.JSONDecodeError) as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Upload record is unreadable or invalid",
                    {"application_id": application_id},
                ) from error
            source = release_artifacts.get(upload.artifact_type)
            copy_path = safe_resolve(self.root, PurePath(upload.relative_path))
            valid = (
                upload.application_id == application_id
                and upload.release_id == release_id
                and upload.record_path == record_relative
                and upload.valid
                and source is not None
                and upload.source_relative_path == source.relative_path
                and upload.source_checksum == source.checksum
                and copy_path.is_relative_to(uploads_root)
                and copy_path.is_file()
                and sha256_file(copy_path) == source.checksum
            )
            if not valid:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Upload copy does not match its verified source release",
                    {
                        "application_id": application_id,
                        "artifact_type": upload.artifact_type.value,
                    },
                )
            assert source is not None
            artifacts.append(
                PayloadArtifact(
                    artifact_type=upload.artifact_type,
                    filename=upload.filename,
                    relative_path=upload.relative_path,
                    checksum=source.checksum,
                    source_release_checksum=source.checksum,
                )
            )
        return tuple(artifacts)

    def _attachment_material(
        self,
        application_id: str,
        submission_id: str,
        requests: tuple[AttachmentRequest, ...],
    ) -> tuple[tuple[PayloadAttachment, Path], ...]:
        resources = safe_resolve(self.root, PurePath("resources"))
        material: list[tuple[PayloadAttachment, Path]] = []
        for request in requests:
            source = safe_resolve(self.root, PurePath(request.source_relative_path))
            if not source.is_relative_to(resources) or not source.is_file():
                raise CareerError(
                    ErrorCode.UNSAFE_PATH,
                    "Additional attachments must come from canonical resources",
                    {"attachment_id": request.attachment_id},
                )
            if sha256_file(source) != request.checksum:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Attachment checksum does not match the selected resource",
                    {"attachment_id": request.attachment_id},
                )
            sanitized = sanitize_untrusted_filename(request.upload_filename)
            stem = Path(sanitized).stem
            suffix = Path(sanitized).suffix.casefold()
            filename = f"{stem}_{request.checksum[:8]}{suffix}"
            destination = safe_resolve(
                self.root,
                PurePath(
                    "applications",
                    application_id,
                    "submissions",
                    submission_id,
                    "attachments",
                    filename,
                ),
            )
            material.append(
                (
                    PayloadAttachment(
                        attachment_id=request.attachment_id,
                        category=request.category,
                        filename=filename,
                        relative_path=destination.relative_to(self.root).as_posix(),
                        checksum=request.checksum,
                        source_relative_path=request.source_relative_path,
                        permission_reference=request.permission_reference,
                    ),
                    source,
                )
            )
        return tuple(material)

    @staticmethod
    def _validate_fields(fields: tuple[PayloadField, ...]) -> None:
        for field in fields:
            reject_prohibited(field.field_id, field.value)
            if field.retention_class is RetentionClass.PROHIBITED:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Prohibited fields cannot enter a submission payload",
                    {"field_id": field.field_id},
                )
            if (
                field.retention_class
                in {
                    RetentionClass.HIGH_RISK,
                    RetentionClass.SENSITIVE,
                }
                and not field.requires_final_review
            ):
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "High-risk and sensitive fields require final review",
                    {"field_id": field.field_id},
                )

    def _verify_answer_references(self, fields: tuple[PayloadField, ...]) -> None:
        answers = {item.answer_id: item for item in self.answers.load_state().answers}
        for field in fields:
            if field.answer_id is None:
                continue
            answer = answers.get(field.answer_id)
            if (
                answer is None
                or answer.value != field.value
                or answer.retention_class is not field.retention_class
            ):
                raise CareerError(
                    ErrorCode.NOT_READY,
                    "Submission field no longer matches its reusable answer source",
                    {"field_id": field.field_id, "answer_id": field.answer_id},
                )

    @staticmethod
    def _request_digest(
        request: PrepareSubmissionRequest,
        *,
        posting_checksum: str,
        artifacts: tuple[PayloadArtifact, ...],
    ) -> str:
        material = {
            "request": request.model_dump(mode="json", exclude={"idempotency_key"}),
            "posting_checksum": posting_checksum,
            "artifacts": [
                item.model_dump(mode="json")
                for item in sorted(
                    artifacts,
                    key=lambda item: (item.artifact_type.value, item.filename),
                )
            ],
        }
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def prepare(
        self,
        application_id: str,
        request: PrepareSubmissionRequest,
    ) -> CanonicalSubmissionPayload:
        application = self.applications.load(application_id)
        unresolved = any(
            item.status is SubmissionStatus.UNCERTAIN
            and item.resolution is not SubmissionResolution.UNSUCCESSFUL
            for item in application.attempts
        )
        if unresolved:
            raise CareerError(
                ErrorCode.CONFLICT,
                "An uncertain submission must be resolved before preparing another attempt",
                {"application_id": application_id},
            )
        if application.stage is not ApplicationStage.READY_FOR_REVIEW:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Application must be ready for review before submission preparation",
                {"application_id": application_id, "stage": application.stage.value},
            )
        if application.current_release_id != request.release_id:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Submission must use the current verified release",
                {"application_id": application_id},
            )
        snapshot_id = application.current_posting_snapshot_id
        if snapshot_id is None:
            raise CareerError(ErrorCode.NOT_READY, "Application has no current posting snapshot")
        posting = self.postings.load(application_id, snapshot_id)
        if posting.availability is not PostingAvailability.OPEN:
            raise CareerError(
                ErrorCode.NOT_READY,
                "Posting freshness is not confirmed open",
                {"application_id": application_id},
            )
        self.documents.verify_release(application_id, request.release_id)
        artifacts = self._verified_uploads(
            application_id,
            request.release_id,
            request.upload_record_paths,
        )
        self._validate_fields(request.fields)
        self._verify_answer_references(request.fields)
        destination = canonicalize_public_http_url(request.destination)
        request_digest = self._request_digest(
            request,
            posting_checksum=posting.checksum,
            artifacts=artifacts,
        )
        idempotency_digest = hashlib.sha256(request.idempotency_key.encode()).hexdigest()
        operation_key = self._operation_key(application_id, idempotency_digest)
        replay = self.journal.replay(operation_key)
        if replay is not None:
            submission_id = replay.result.get("submission_id")
            if not isinstance(submission_id, str):
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Submission preparation replay has no attempt identity",
                )
            existing = self.load(application_id, submission_id)
            if existing.request_digest != request_digest:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Idempotency key is bound to a different submission payload",
                )
            return existing
        active = self.journal.operation_for_key(operation_key)
        reserved = (
            self.journal.checkpoint_data(active.run_id, "submission-identity")
            if active is not None
            else None
        )
        if reserved is not None and reserved.get("request_digest") != request_digest:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Idempotency key is bound to a different submission payload",
            )
        reserved_id = reserved.get("submission_id") if reserved is not None else None
        if reserved_id is not None and not isinstance(reserved_id, str):
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Reserved submission ID is invalid")
        submission_id = reserved_id or self.registry.allocate_local_id(
            application_id,
            "submission",
        )
        run_id = active.run_id if active is not None else self.registry.allocate_run_id()
        operation = active or OperationRecord(
            run_id=run_id,
            operation="submission.prepare",
            idempotency_key=operation_key,
            status=OperationStatus.STARTED,
        )
        payload = CanonicalSubmissionPayload(
            application_id=application_id,
            submission_id=submission_id,
            posting=PayloadPosting(
                snapshot_id=posting.snapshot_id,
                checksum=posting.checksum,
            ),
            release_id=request.release_id,
            artifacts=artifacts,
            attachments=tuple(
                item
                for item, _ in self._attachment_material(
                    application_id,
                    submission_id,
                    request.attachments,
                )
            ),
            fields=request.fields,
            attestations=request.attestations,
            anomalies=request.anomalies,
            evidence_limitations=request.evidence_limitations,
            destination=AnyHttpUrl(destination),
            irreversible_action=request.irreversible_action,
            request_digest=request_digest,
            idempotency_digest=idempotency_digest,
        )
        self.journal.begin(operation)
        self.journal.checkpoint(
            operation.run_id,
            "submission-identity",
            {"submission_id": submission_id, "request_digest": request_digest},
        )
        path = self.path(application_id, submission_id)
        attachment_material = self._attachment_material(
            application_id,
            submission_id,
            request.attachments,
        )
        with ApplicationLock(self.root, application_id, run_id=operation.run_id):
            for attachment, source in attachment_material:
                attachment_destination = safe_resolve(
                    self.root,
                    PurePath(attachment.relative_path),
                )
                atomic_write_bytes(attachment_destination, source.read_bytes())
            if path.exists():
                try:
                    current = CanonicalSubmissionPayload.model_validate_json(path.read_text())
                except (OSError, ValidationError, json.JSONDecodeError) as error:
                    raise CareerError(
                        ErrorCode.INTEGRITY_ERROR,
                        "Canonical submission payload is unreadable or invalid",
                    ) from error
                if current != payload:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Submission identity contains a different payload",
                    )
            else:
                atomic_write_json(path, payload)
            payload_checksum = sha256_file(path)
            payload_digest = self.digest(payload)
            self.journal.checkpoint(
                operation.run_id,
                "payload-written",
                {"checksum": payload_checksum, "digest": payload_digest},
            )
        self.journal.commit(
            operation.run_id,
            {
                "submission_id": submission_id,
                "payload_checksum": payload_checksum,
                "payload_digest": payload_digest,
                "result_references": [submission_id],
            },
        )
        return payload

    def load(
        self,
        application_id: str,
        submission_id: str,
    ) -> CanonicalSubmissionPayload:
        path = self.path(application_id, submission_id)
        try:
            payload = CanonicalSubmissionPayload.model_validate_json(path.read_text())
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Canonical submission payload does not exist",
                {"application_id": application_id, "submission_id": submission_id},
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Canonical submission payload is unreadable or invalid",
                {"application_id": application_id, "submission_id": submission_id},
            ) from error
        if payload.application_id != application_id or payload.submission_id != submission_id:
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Submission payload identity mismatch")
        operation_key = self._operation_key(application_id, payload.idempotency_digest)
        replay = self.journal.replay(operation_key)
        actual_checksum = sha256_file(path)
        actual_digest = self.digest(payload)
        if replay is None:
            active = self.journal.operation_for_key(operation_key)
            checkpoint = (
                self.journal.checkpoint_data(active.run_id, "payload-written")
                if active is not None
                else None
            )
            if (
                active is None
                or checkpoint is None
                or checkpoint.get("checksum") != actual_checksum
                or checkpoint.get("digest") != actual_digest
            ):
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Submission payload has no valid journal seal",
                )
            self.journal.commit(
                active.run_id,
                {
                    "submission_id": submission_id,
                    "payload_checksum": actual_checksum,
                    "payload_digest": actual_digest,
                    "result_references": [submission_id],
                },
            )
        elif (
            replay.result.get("payload_checksum") != actual_checksum
            or replay.result.get("payload_digest") != actual_digest
        ):
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Submission payload does not match its journal seal",
            )
        application = self.applications.load(application_id)
        if (
            application.current_posting_snapshot_id != payload.posting.snapshot_id
            or application.current_release_id != payload.release_id
        ):
            raise CareerError(
                ErrorCode.NOT_READY,
                "Submission payload is stale relative to the application",
            )
        posting = self.postings.load(application_id, payload.posting.snapshot_id)
        if (
            posting.checksum != payload.posting.checksum
            or posting.availability is not PostingAvailability.OPEN
        ):
            raise CareerError(ErrorCode.NOT_READY, "Submission posting is stale or closed")
        self.documents.verify_release(application_id, payload.release_id)
        self._verify_answer_references(payload.fields)
        uploads_root = safe_resolve(
            self.root,
            PurePath("applications", application_id, "uploads"),
        )
        for artifact in payload.artifacts:
            upload_path = safe_resolve(self.root, PurePath(artifact.relative_path))
            if (
                not upload_path.is_relative_to(uploads_root)
                or not upload_path.is_file()
                or sha256_file(upload_path) != artifact.checksum
            ):
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Submission upload bytes no longer match the reviewed payload",
                    {"artifact_type": artifact.artifact_type.value},
                )
        for attachment in payload.attachments:
            path = safe_resolve(self.root, PurePath(attachment.relative_path))
            if not path.is_file() or sha256_file(path) != attachment.checksum:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Submission attachment bytes no longer match the reviewed payload",
                    {"attachment_id": attachment.attachment_id},
                )
        return payload
