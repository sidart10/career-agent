"""Factories for repeatable, application-local recruiting events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from career_agent.models.application import (
    ApplicationStage,
    RecruitingEvent,
    RecruitingEventKind,
)
from career_agent.storage.registry import SequenceRegistry
from career_agent.storage.repository import ApplicationRepository


class RecruitingEventService:
    def __init__(self, root: Path) -> None:
        self.registry = SequenceRegistry(root)
        self.repository = ApplicationRepository(root)

    def _next_event_id(self, application_id: str) -> str:
        existing_ids = {event.event_id for event in self.repository.load(application_id).events}
        while True:
            event_id = self.registry.allocate_event_id(application_id)
            if event_id not in existing_ids:
                return event_id

    def status_transition(
        self,
        application_id: str,
        *,
        before: ApplicationStage,
        after: ApplicationStage,
        reason: str,
    ) -> RecruitingEvent:
        return RecruitingEvent(
            event_id=self._next_event_id(application_id),
            kind=RecruitingEventKind.STATUS,
            occurred_at=datetime.now(UTC),
            source_reference="user:application-transition",
            reason=reason,
            from_stage=before,
            to_stage=after,
        )

    def freshness_event(
        self,
        application_id: str,
        *,
        reason: str,
    ) -> RecruitingEvent:
        return RecruitingEvent(
            event_id=self._next_event_id(application_id),
            kind=RecruitingEventKind.STATUS,
            occurred_at=datetime.now(UTC),
            source_reference="system:posting-freshness",
            reason=reason,
        )
