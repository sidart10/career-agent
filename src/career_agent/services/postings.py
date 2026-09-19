"""Immutable posting snapshots and fail-closed freshness classification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePath
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationManifest, ApplicationStage
from career_agent.models.base import (
    ApplicationId,
    PersistedModel,
    PostingSnapshotId,
    UtcDateTime,
)
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.opportunity import Opportunity, OpportunityStatus
from career_agent.security.urls import canonicalize_public_http_url
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry
from career_agent.storage.repository import ApplicationRepository


class PostingAvailability(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class PostingChangeClassification(StrEnum):
    NONE = "none"
    MATERIAL = "material"
    UNCERTAIN = "uncertain"
    CLOSED = "closed"


class ResponsibilityChangeClassification(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNCERTAIN = "uncertain"


class ResponsibilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: ResponsibilityChangeClassification
    rationale: str = Field(min_length=1)


class PostingCapture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_text: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    retrieved_at: UtcDateTime
    source_adapter: str = Field(min_length=1)
    source_adapter_metadata: dict[str, Any] = Field(default_factory=dict)
    availability: PostingAvailability = PostingAvailability.UNKNOWN
    responsibilities: tuple[str, ...] = ()
    location: str | None = None
    compensation: str | None = None
    eligibility: str | None = None
    deadline: str | None = None
    requisition_id: str | None = None


def normalize_posting_text(value: str) -> str:
    return " ".join(value.split())


class PostingSnapshot(PersistedModel):
    snapshot_id: PostingSnapshotId
    application_id: ApplicationId
    raw_text: str
    normalized_text: str
    source_url: AnyHttpUrl
    retrieved_at: UtcDateTime
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_adapter: str
    source_adapter_metadata: dict[str, Any] = Field(default_factory=dict)
    availability: PostingAvailability = PostingAvailability.UNKNOWN
    responsibilities: tuple[str, ...] = ()
    location: str | None = None
    compensation: str | None = None
    eligibility: str | None = None
    deadline: str | None = None
    requisition_id: str | None = None


class PostingChangeSet(PersistedModel):
    application_id: ApplicationId
    previous_snapshot_id: PostingSnapshotId
    current_snapshot_id: PostingSnapshotId
    classification: PostingChangeClassification
    material_fields: tuple[str, ...] = ()
    is_material: bool


def _normalized_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_posting_text(value).casefold()
    return normalized or None


def _normalized_responsibilities(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(
        normalized for item in values if (normalized := _normalized_optional(item)) is not None
    )


class PostingService:
    def __init__(
        self,
        root: Path,
        *,
        responsibility_classifier: Callable[[str, str], object] | None = None,
    ) -> None:
        self.root = root.resolve(strict=False)
        self.registry = SequenceRegistry(self.root)
        self.repository = ApplicationRepository(self.root)
        self.responsibility_classifier = responsibility_classifier

    def _assess_unstructured_responsibilities(
        self,
        previous: PostingSnapshot,
        current: PostingSnapshot,
    ) -> ResponsibilityChangeClassification:
        if self.responsibility_classifier is None:
            return ResponsibilityChangeClassification.UNCERTAIN
        try:
            result = self.responsibility_classifier(previous.raw_text, current.raw_text)
            return ResponsibilityAssessment.model_validate(result).classification
        except (ValidationError, TypeError, ValueError):
            return ResponsibilityChangeClassification.UNCERTAIN

    def path(self, application_id: str, snapshot_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath("applications", application_id, "postings", f"{snapshot_id}.json"),
        )

    def change_path(self, application_id: str, snapshot_id: str) -> Path:
        return safe_resolve(
            self.root,
            PurePath(
                "applications",
                application_id,
                "posting-changes",
                f"{snapshot_id}.json",
            ),
        )

    def snapshot_from_capture(
        self,
        application_id: str,
        snapshot_id: str,
        capture: PostingCapture,
    ) -> PostingSnapshot:
        return PostingSnapshot(
            created_at=capture.retrieved_at,
            updated_at=capture.retrieved_at,
            snapshot_id=snapshot_id,
            application_id=application_id,
            raw_text=capture.raw_text,
            normalized_text=normalize_posting_text(capture.raw_text),
            source_url=AnyHttpUrl(canonicalize_public_http_url(capture.source_url)),
            retrieved_at=capture.retrieved_at,
            checksum=hashlib.sha256(capture.raw_text.encode()).hexdigest(),
            source_adapter=capture.source_adapter,
            source_adapter_metadata=capture.source_adapter_metadata,
            availability=capture.availability,
            responsibilities=capture.responsibilities,
            location=capture.location,
            compensation=capture.compensation,
            eligibility=capture.eligibility,
            deadline=capture.deadline,
            requisition_id=capture.requisition_id,
        )

    def _write_snapshot(self, snapshot: PostingSnapshot) -> PostingSnapshot:
        path = self.path(snapshot.application_id, snapshot.snapshot_id)
        if path.exists():
            try:
                existing = PostingSnapshot.model_validate_json(path.read_text())
            except (OSError, ValidationError, json.JSONDecodeError) as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Posting snapshot is unreadable or invalid",
                    {"path": str(path)},
                ) from error
            if existing != snapshot:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Posting snapshot ID already contains different content",
                    {"snapshot_id": snapshot.snapshot_id},
                )
            return existing
        atomic_write_json(path, snapshot)
        return snapshot

    def capture_from_opportunity(
        self,
        application_id: str,
        snapshot_id: str,
        opportunity: Opportunity,
    ) -> PostingSnapshot:
        if opportunity.canonical_url is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Opportunity has no canonical posting URL",
                {"opportunity_id": opportunity.opportunity_id},
            )
        capture = PostingCapture(
            raw_text=opportunity.posting_text,
            source_url=str(opportunity.canonical_url),
            retrieved_at=opportunity.created_at,
            source_adapter="opportunity-capture",
            source_adapter_metadata={"opportunity_id": opportunity.opportunity_id},
            availability=(
                PostingAvailability.CLOSED
                if opportunity.status is OpportunityStatus.EXPIRED
                else PostingAvailability.OPEN
            ),
            responsibilities=tuple(
                item.strip() for item in opportunity.posting_text.splitlines() if item.strip()
            ),
            location=opportunity.location,
            deadline=opportunity.deadline.isoformat() if opportunity.deadline else None,
            requisition_id=opportunity.requisition_id,
        )
        return self._write_snapshot(
            self.snapshot_from_capture(application_id, snapshot_id, capture)
        )

    def capture(
        self,
        application_id: str,
        posting: PostingCapture,
    ) -> PostingSnapshot:
        self.repository.load(application_id)
        snapshot_id = self.registry.allocate_posting_id(application_id)
        snapshot = self._write_snapshot(
            self.snapshot_from_capture(application_id, snapshot_id, posting)
        )
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="posting.capture",
            idempotency_key=f"posting-capture:{application_id}:{snapshot_id}",
            status=OperationStatus.STARTED,
        )

        def attach(current: ApplicationManifest | None) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            return current.model_copy(
                update={
                    "posting_snapshot_ids": (*current.posting_snapshot_ids, snapshot_id),
                    "current_posting_snapshot_id": snapshot_id,
                    "updated_at": datetime.now(UTC),
                }
            )

        self.repository.mutate(application_id, operation, attach)
        return snapshot

    def load(self, application_id: str, snapshot_id: str) -> PostingSnapshot:
        try:
            return PostingSnapshot.model_validate_json(
                self.path(application_id, snapshot_id).read_text()
            )
        except FileNotFoundError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Posting snapshot does not exist",
                {"application_id": application_id, "snapshot_id": snapshot_id},
            ) from error
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Posting snapshot is unreadable or invalid",
                {"application_id": application_id, "snapshot_id": snapshot_id},
            ) from error

    def compare(
        self,
        previous: PostingSnapshot,
        current: PostingSnapshot,
    ) -> PostingChangeSet:
        if previous.application_id != current.application_id:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Posting snapshots belong to different applications",
            )
        changed: list[str] = []
        if previous.availability is not current.availability:
            changed.append("availability")
        previous_responsibilities = _normalized_responsibilities(previous.responsibilities)
        current_responsibilities = _normalized_responsibilities(current.responsibilities)
        responsibility_uncertain = False
        if previous_responsibilities or current_responsibilities:
            if previous_responsibilities != current_responsibilities:
                changed.append("responsibilities")
        elif previous.normalized_text.casefold() != current.normalized_text.casefold():
            assessment = self._assess_unstructured_responsibilities(previous, current)
            if assessment is not ResponsibilityChangeClassification.UNCHANGED:
                changed.append("responsibilities")
            responsibility_uncertain = assessment is ResponsibilityChangeClassification.UNCERTAIN
        for field in (
            "location",
            "compensation",
            "eligibility",
            "deadline",
            "requisition_id",
        ):
            if _normalized_optional(getattr(previous, field)) != _normalized_optional(
                getattr(current, field)
            ):
                changed.append(field)
        if current.availability is PostingAvailability.CLOSED:
            classification = PostingChangeClassification.CLOSED
        elif responsibility_uncertain:
            classification = PostingChangeClassification.UNCERTAIN
        elif changed:
            classification = PostingChangeClassification.MATERIAL
        else:
            classification = PostingChangeClassification.NONE
        return PostingChangeSet(
            created_at=current.retrieved_at,
            updated_at=current.retrieved_at,
            application_id=current.application_id,
            previous_snapshot_id=previous.snapshot_id,
            current_snapshot_id=current.snapshot_id,
            classification=classification,
            material_fields=tuple(changed),
            is_material=classification is not PostingChangeClassification.NONE,
        )

    def _write_change_set(self, change_set: PostingChangeSet) -> None:
        path = self.change_path(
            change_set.application_id,
            change_set.current_snapshot_id,
        )
        if path.exists():
            try:
                existing = PostingChangeSet.model_validate_json(path.read_text())
            except (OSError, ValidationError, json.JSONDecodeError) as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Posting change history is unreadable or invalid",
                    {"path": str(path)},
                ) from error
            if existing != change_set:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Posting change history is immutable",
                    {"snapshot_id": change_set.current_snapshot_id},
                )
            return
        atomic_write_json(path, change_set)

    def apply_freshness(
        self,
        application_id: str,
        change_set: PostingChangeSet,
    ) -> ApplicationManifest:
        if change_set.application_id != application_id:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Posting change set belongs to another application",
            )
        current = self.repository.load(application_id)
        if len(current.posting_snapshot_ids) < 2 or current.posting_snapshot_ids[-2:] != (
            change_set.previous_snapshot_id,
            change_set.current_snapshot_id,
        ):
            raise CareerError(
                ErrorCode.CONFLICT,
                "Posting change set is stale or does not compare adjacent snapshots",
                {
                    "application_id": application_id,
                    "current_snapshot_id": current.current_posting_snapshot_id,
                },
            )
        self._write_change_set(change_set)
        if not change_set.is_material:
            return current
        reason = (
            f"posting freshness {change_set.classification.value}: "
            f"{', '.join(change_set.material_fields)}"
        )
        from career_agent.services.events import RecruitingEventService

        event = RecruitingEventService(self.root).freshness_event(application_id, reason=reason)
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="posting.apply-freshness",
            idempotency_key=(
                f"posting-freshness:{application_id}:{change_set.current_snapshot_id}"
            ),
            status=OperationStatus.STARTED,
        )

        def invalidate(existing: ApplicationManifest | None) -> ApplicationManifest:
            if existing is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            now = datetime.now(UTC)
            target = (
                ApplicationStage.PREPARING
                if existing.stage in {ApplicationStage.READY_FOR_REVIEW, ApplicationStage.APPROVED}
                else existing.stage
            )
            return existing.model_copy(
                update={
                    "stage": target,
                    "approval_invalidated_at": now,
                    "approval_invalidation_reason": reason,
                    "posting_closed_at": (
                        now
                        if change_set.classification is PostingChangeClassification.CLOSED
                        else existing.posting_closed_at
                    ),
                    "events": (*existing.events, event),
                    "updated_at": now,
                }
            )

        updated = self.repository.mutate(application_id, operation, invalidate)
        if change_set.classification is PostingChangeClassification.CLOSED:
            from career_agent.services.opportunities import OpportunityService

            OpportunityService(self.root).set_status(
                current.opportunity_id,
                OpportunityStatus.EXPIRED,
                "posting freshness check found closure",
            )
        return updated
