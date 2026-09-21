"""Application ownership, stable identity, and lifecycle operations."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path, PurePath

from pydantic import Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import (
    ApplicationManifest,
    ApplicationStage,
    RecruitingEvent,
)
from career_agent.models.base import PersistedModel
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.opportunity import OpportunityStatus
from career_agent.services.events import RecruitingEventService
from career_agent.services.opportunities import OpportunityService
from career_agent.services.postings import PostingService
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry
from career_agent.storage.repository import ApplicationRepository


class ApplicationIndex(PersistedModel):
    application_ids: tuple[str, ...] = ()
    opportunity_applications: dict[str, str] = Field(default_factory=dict)
    idempotency_results: dict[str, str] = Field(default_factory=dict)


def _slug(*parts: str) -> str:
    value = "-".join(parts)
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
    return normalized or "application"


class ApplicationService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.index_path = safe_resolve(
            self.root,
            PurePath("applications", "index.json"),
        )
        self.repository = ApplicationRepository(self.root)
        self.opportunities = OpportunityService(self.root)
        self.postings = PostingService(self.root)
        self.registry = SequenceRegistry(self.root)
        self.events = RecruitingEventService(self.root)

    def _load_index(self) -> ApplicationIndex:
        try:
            return ApplicationIndex.model_validate_json(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ApplicationIndex()
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Application index is unreadable or invalid",
                {"path": str(self.index_path)},
            ) from error

    def load(self, application_id: str) -> ApplicationManifest:
        return self.repository.load(application_id)

    def list(self) -> tuple[ApplicationManifest, ...]:
        index = self._load_index()
        return tuple(self.load(application_id) for application_id in index.application_ids)

    def _register_application_unlocked(
        self,
        application: ApplicationManifest,
        idempotency_key: str,
    ) -> None:
        index = self._load_index()
        opportunity_owner = index.opportunity_applications.get(application.opportunity_id)
        key_owner = index.idempotency_results.get(idempotency_key)
        for owner in (opportunity_owner, key_owner):
            if owner is not None and owner != application.application_id:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Application index maps the pursuit to another application",
                    {
                        "application_id": application.application_id,
                        "existing_application_id": owner,
                    },
                )
        opportunity_applications = dict(index.opportunity_applications)
        opportunity_applications[application.opportunity_id] = application.application_id
        idempotency_results = dict(index.idempotency_results)
        idempotency_results[idempotency_key] = application.application_id
        application_ids = tuple(dict.fromkeys((*index.application_ids, application.application_id)))
        atomic_write_json(
            self.index_path,
            index.model_copy(
                update={
                    "application_ids": application_ids,
                    "opportunity_applications": opportunity_applications,
                    "idempotency_results": idempotency_results,
                    "updated_at": datetime.now(UTC),
                }
            ),
        )

    def _application_for_opportunity(
        self,
        opportunity_id: str,
    ) -> ApplicationManifest | None:
        applications_dir = safe_resolve(self.root, PurePath("applications"))
        matches: list[ApplicationManifest] = []
        for manifest_path in sorted(applications_dir.glob("APP-*/manifest.json")):
            candidate = self.load(manifest_path.parent.name)
            if candidate.opportunity_id == opportunity_id:
                matches.append(candidate)
        if len(matches) > 1:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Multiple applications own the same opportunity",
                {"opportunity_id": opportunity_id},
            )
        return matches[0] if matches else None

    def _finish_creation_unlocked(
        self,
        application: ApplicationManifest,
        idempotency_key: str,
    ) -> ApplicationManifest:
        opportunity = self.opportunities.get(application.opportunity_id)
        snapshot_id = application.current_posting_snapshot_id
        if snapshot_id is None:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "New application has no initial posting snapshot reference",
                {"application_id": application.application_id},
            )
        self.postings.capture_from_opportunity(
            application.application_id,
            snapshot_id,
            opportunity,
        )
        self._register_application_unlocked(application, idempotency_key)
        return application

    def _ensure_pursued_status(self, opportunity_id: str) -> None:
        opportunity = self.opportunities.get(opportunity_id)
        if opportunity.status in {
            OpportunityStatus.DISCOVERED,
            OpportunityStatus.EVALUATING,
        }:
            self.opportunities.set_status(
                opportunity_id,
                OpportunityStatus.PURSUED,
                "application created",
            )

    def create_from_opportunity(
        self,
        opportunity_id: str,
        idempotency_key: str,
    ) -> ApplicationManifest:
        index = self._load_index()
        opportunity_owner = index.opportunity_applications.get(opportunity_id)
        key_owner = index.idempotency_results.get(idempotency_key)
        if opportunity_owner is not None:
            if key_owner is not None and key_owner != opportunity_owner:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to another application",
                    {"existing_application_id": key_owner},
                )
            application = self.load(opportunity_owner)
            self._ensure_pursued_status(opportunity_id)
            return application
        if key_owner is not None:
            keyed_application = self.load(key_owner)
            if keyed_application.opportunity_id != opportunity_id:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Idempotency key belongs to another opportunity",
                    {
                        "opportunity_id": opportunity_id,
                        "existing_opportunity_id": keyed_application.opportunity_id,
                    },
                )
            self._ensure_pursued_status(opportunity_id)
            return keyed_application
        opportunity = self.opportunities.get(opportunity_id)
        if opportunity.status is OpportunityStatus.EXPIRED:
            raise CareerError(
                ErrorCode.CONFLICT,
                "Expired opportunity cannot create a new application",
                {"opportunity_id": opportunity_id},
            )
        application_id = self.registry.allocate_application_id(opportunity.created_at.year)
        snapshot_id = self.registry.allocate_posting_id(application_id)
        run_id = self.registry.allocate_run_id()
        candidate = ApplicationManifest(
            application_id=application_id,
            opportunity_id=opportunity_id,
            display_slug=_slug(opportunity.company, opportunity.title),
            posting_snapshot_ids=(snapshot_id,),
            current_posting_snapshot_id=snapshot_id,
        )
        operation_key = f"application-create:{idempotency_key}"
        with WorkspaceLock(self.root, run_id=run_id):
            locked_index = self._load_index()
            opportunity_owner = locked_index.opportunity_applications.get(opportunity_id)
            key_owner = locked_index.idempotency_results.get(idempotency_key)
            if opportunity_owner is not None:
                if key_owner is not None and key_owner != opportunity_owner:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Idempotency key belongs to another application",
                        {"existing_application_id": key_owner},
                    )
                saved = self.load(opportunity_owner)
            elif key_owner is not None:
                saved = self.load(key_owner)
                if saved.opportunity_id != opportunity_id:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Idempotency key belongs to another opportunity",
                        {
                            "opportunity_id": opportunity_id,
                            "existing_opportunity_id": saved.opportunity_id,
                        },
                    )
            else:
                replay = self.repository.journal.replay(operation_key)
                if replay is not None:
                    replayed_id = replay.result.get("application_id")
                    if not isinstance(replayed_id, str):
                        raise CareerError(
                            ErrorCode.INTEGRITY_ERROR,
                            "Application creation replay has no application identity",
                        )
                    saved = self.load(replayed_id)
                    if saved.opportunity_id != opportunity_id:
                        raise CareerError(
                            ErrorCode.CONFLICT,
                            "Idempotency key belongs to another opportunity",
                        )
                else:
                    existing_application = self._application_for_opportunity(opportunity_id)
                    if existing_application is not None:
                        saved = existing_application
                    else:
                        locked_opportunity = self.opportunities.get(opportunity_id)
                        if locked_opportunity.status is OpportunityStatus.EXPIRED:
                            raise CareerError(
                                ErrorCode.CONFLICT,
                                "Expired opportunity cannot create a new application",
                                {"opportunity_id": opportunity_id},
                            )
                        operation = OperationRecord(
                            run_id=run_id,
                            operation="application.create",
                            idempotency_key=operation_key,
                            status=OperationStatus.STARTED,
                        )
                        saved = self.repository.create(candidate, operation)
            saved = self._finish_creation_unlocked(saved, idempotency_key)
        self._ensure_pursued_status(opportunity_id)
        return saved

    def rename_display(
        self,
        application_id: str,
        *,
        company: str,
        role: str,
    ) -> ApplicationManifest:
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="application.rename-display",
            idempotency_key=f"application-rename:{application_id}:{_slug(company, role)}",
            status=OperationStatus.STARTED,
        )

        def rename(current: ApplicationManifest | None) -> ApplicationManifest:
            if current is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            return current.model_copy(
                update={
                    "display_slug": _slug(company, role),
                    "updated_at": datetime.now(UTC),
                }
            )

        return self.repository.mutate(application_id, operation, rename)

    def transition(
        self,
        application_id: str,
        target: ApplicationStage,
        reason: str,
    ) -> ApplicationManifest:
        if not reason.strip():
            raise CareerError(ErrorCode.INVALID_INPUT, "Transition reason is required")
        current = self.load(application_id)
        if current.posting_closed_at is not None and target is ApplicationStage.APPLYING:
            raise CareerError(
                ErrorCode.NOT_READY,
                "A closed posting blocks new submission attempts",
                {"application_id": application_id},
            )
        event = self.events.status_transition(
            application_id,
            before=current.stage,
            after=target,
            reason=reason,
        )
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="application.transition",
            idempotency_key=f"application-transition:{application_id}:{event.event_id}",
            status=OperationStatus.STARTED,
        )

        def apply_transition(existing: ApplicationManifest | None) -> ApplicationManifest:
            if existing is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            return existing.model_copy(
                update={
                    "stage": target,
                    "events": (*existing.events, event),
                    "updated_at": datetime.now(UTC),
                }
            )

        return self.repository.mutate(application_id, operation, apply_transition)

    def add_event(
        self,
        application_id: str,
        event: RecruitingEvent,
    ) -> ApplicationManifest:
        current = self.load(application_id)
        duplicate = next(
            (existing for existing in current.events if existing.event_id == event.event_id),
            None,
        )
        if duplicate is not None:
            if duplicate == event:
                return current
            raise CareerError(
                ErrorCode.CONFLICT,
                "Recruiting event ID already contains different content",
                {"application_id": application_id, "event_id": event.event_id},
            )
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="application.add-event",
            idempotency_key=f"application-event:{application_id}:{event.event_id}",
            status=OperationStatus.STARTED,
        )

        def append_event(existing: ApplicationManifest | None) -> ApplicationManifest:
            if existing is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Application does not exist")
            if any(item.event_id == event.event_id for item in existing.events):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Recruiting event ID already exists",
                    {"event_id": event.event_id},
                )
            return existing.model_copy(
                update={
                    "events": (*existing.events, event),
                    "updated_at": datetime.now(UTC),
                }
            )

        return self.repository.mutate(application_id, operation, append_event)
