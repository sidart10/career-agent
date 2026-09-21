from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import (
    ApplicationStage,
    RecruitingEvent,
    RecruitingEventKind,
)
from career_agent.services.applications import ApplicationService
from career_agent.services.opportunities import OpportunityCapture, OpportunityService

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def application_service(root: Path) -> tuple[ApplicationService, str]:
    opportunity_id = (
        OpportunityService(root)
        .add(
            OpportunityCapture(
                company="Example Labs",
                title="Product Manager",
                location="Remote",
                url="https://jobs.example.test/roles/42",
                captured_at=NOW,
                posting_text="Build products.",
                posting_complete=True,
            ),
            idempotency_key="capture-42",
        )
        .opportunity_id
    )
    service = ApplicationService(root)
    application = service.create_from_opportunity(opportunity_id, "pursue-42")
    return service, application.application_id


def event(event_id: str, kind: RecruitingEventKind) -> RecruitingEvent:
    return RecruitingEvent(
        event_id=event_id,
        kind=kind,
        occurred_at=NOW,
        source_reference=f"user:{event_id}",
    )


def test_interviews_follow_ups_and_offers_are_repeatable_history(tmp_path: Path) -> None:
    service, application_id = application_service(tmp_path)

    for item in (
        event("EVT-0001", RecruitingEventKind.INTERVIEW),
        event("EVT-0002", RecruitingEventKind.INTERVIEW),
        event("EVT-0003", RecruitingEventKind.FOLLOW_UP),
        event("EVT-0004", RecruitingEventKind.OFFER),
        event("EVT-0005", RecruitingEventKind.OFFER),
    ):
        service.add_event(application_id, item)

    application = service.load(application_id)
    assert [item.kind for item in application.events] == [
        RecruitingEventKind.INTERVIEW,
        RecruitingEventKind.INTERVIEW,
        RecruitingEventKind.FOLLOW_UP,
        RecruitingEventKind.OFFER,
        RecruitingEventKind.OFFER,
    ]
    assert application.stage is ApplicationStage.PREPARING


def test_duplicate_event_id_is_rejected_without_replacing_history(tmp_path: Path) -> None:
    service, application_id = application_service(tmp_path)
    first = event("EVT-0001", RecruitingEventKind.INTERVIEW)
    service.add_event(application_id, first)

    with pytest.raises(CareerError) as error:
        service.add_event(
            application_id,
            event("EVT-0001", RecruitingEventKind.OFFER),
        )

    assert error.value.code is ErrorCode.CONFLICT
    assert service.load(application_id).events == (first,)


def test_transition_is_explicit_and_records_reason_without_event_bypass(
    tmp_path: Path,
) -> None:
    service, application_id = application_service(tmp_path)
    service.add_event(
        application_id,
        event("EVT-0001", RecruitingEventKind.INTERVIEW),
    )

    transitioned = service.transition(
        application_id,
        ApplicationStage.READY_FOR_REVIEW,
        "all documents generated",
    )

    assert transitioned.stage is ApplicationStage.READY_FOR_REVIEW
    assert transitioned.events[0].kind is RecruitingEventKind.INTERVIEW
    assert transitioned.events[-1].kind is RecruitingEventKind.STATUS
    assert transitioned.events[-1].reason == "all documents generated"
    assert transitioned.events[-1].to_stage is ApplicationStage.READY_FOR_REVIEW
