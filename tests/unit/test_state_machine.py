from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from career_agent.models.application import (
    ApplicationManifest,
    ApplicationStage,
    Outcome,
    OutcomeRecord,
    OutcomeSource,
    RecruitingEvent,
    RecruitingEventKind,
)
from career_agent.models.submission import (
    SubmissionAttempt,
    SubmissionResolution,
    SubmissionStatus,
)
from career_agent.state_machine import (
    InvalidTransition,
    InvalidWorkspaceState,
    validate_transition,
    validate_workspace_state,
)


def application(
    *,
    stage: ApplicationStage = ApplicationStage.PREPARING,
    submission_status: SubmissionStatus = SubmissionStatus.NONE,
    attempts: tuple[SubmissionAttempt, ...] = (),
    events: tuple[RecruitingEvent, ...] = (),
    outcome: OutcomeRecord | None = None,
    closure_reason: str | None = None,
    posting_snapshot_ids: tuple[str, ...] = (),
    current_posting_snapshot_id: str | None = None,
) -> ApplicationManifest:
    return ApplicationManifest(
        application_id="APP-2026-0001",
        opportunity_id="OPP-2026-0001",
        stage=stage,
        submission_status=submission_status,
        attempts=attempts,
        events=events,
        outcome=outcome,
        closure_reason=closure_reason,
        posting_snapshot_ids=posting_snapshot_ids,
        current_posting_snapshot_id=current_posting_snapshot_id,
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (ApplicationStage.PREPARING, ApplicationStage.READY_FOR_REVIEW),
        (ApplicationStage.READY_FOR_REVIEW, ApplicationStage.PREPARING),
        (ApplicationStage.READY_FOR_REVIEW, ApplicationStage.APPROVED),
        (ApplicationStage.APPROVED, ApplicationStage.PREPARING),
        (ApplicationStage.APPROVED, ApplicationStage.APPLYING),
        (ApplicationStage.APPLYING, ApplicationStage.SUBMITTED),
        (ApplicationStage.SUBMITTED, ApplicationStage.CLOSED),
    ],
)
def test_explicit_stage_transition_is_allowed(
    before: ApplicationStage,
    after: ApplicationStage,
) -> None:
    in_progress = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.IN_PROGRESS,
        approval_id="APR-0001",
    )
    confirmed = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.CONFIRMED,
        approval_id="APR-0001",
        resolution=SubmissionResolution.CONFIRMED,
    )
    before_status = SubmissionStatus.NONE
    after_status = SubmissionStatus.NONE
    before_attempts: tuple[SubmissionAttempt, ...] = ()
    after_attempts: tuple[SubmissionAttempt, ...] = ()
    if before is ApplicationStage.APPLYING:
        before_status = SubmissionStatus.IN_PROGRESS
        before_attempts = (in_progress,)
    if before is ApplicationStage.SUBMITTED:
        before_status = SubmissionStatus.CONFIRMED
        before_attempts = (confirmed,)
    if after is ApplicationStage.APPLYING:
        after_status = SubmissionStatus.IN_PROGRESS
        after_attempts = (in_progress,)
    if after in {ApplicationStage.SUBMITTED, ApplicationStage.CLOSED}:
        after_status = SubmissionStatus.CONFIRMED
        after_attempts = (confirmed,)
    closure_reason = "administrative close" if after is ApplicationStage.CLOSED else None

    validate_transition(
        application(stage=before, submission_status=before_status, attempts=before_attempts),
        application(
            stage=after,
            submission_status=after_status,
            attempts=after_attempts,
            closure_reason=closure_reason,
        ),
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (ApplicationStage.PREPARING, ApplicationStage.APPROVED),
        (ApplicationStage.PREPARING, ApplicationStage.SUBMITTED),
        (ApplicationStage.READY_FOR_REVIEW, ApplicationStage.APPLYING),
        (ApplicationStage.APPROVED, ApplicationStage.SUBMITTED),
        (ApplicationStage.SUBMITTED, ApplicationStage.PREPARING),
        (ApplicationStage.CLOSED, ApplicationStage.APPLYING),
    ],
)
def test_unlisted_stage_transition_is_rejected(
    before: ApplicationStage,
    after: ApplicationStage,
) -> None:
    with pytest.raises(InvalidTransition, match="stage transition"):
        validate_transition(application(stage=before), application(stage=after))


def test_submitted_requires_a_confirmed_attempt() -> None:
    with pytest.raises(InvalidWorkspaceState, match="confirmed submission attempt"):
        validate_workspace_state(
            application(
                stage=ApplicationStage.SUBMITTED,
                submission_status=SubmissionStatus.CONFIRMED,
            )
        )


def test_uncertain_submission_must_remain_applying() -> None:
    uncertain = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.UNCERTAIN,
        approval_id="APR-0001",
    )

    with pytest.raises(InvalidWorkspaceState, match="remain applying"):
        validate_workspace_state(
            application(
                stage=ApplicationStage.READY_FOR_REVIEW,
                submission_status=SubmissionStatus.UNCERTAIN,
                attempts=(uncertain,),
            )
        )


def test_confirmed_submission_status_requires_submitted_or_closed_stage() -> None:
    confirmed = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.CONFIRMED,
        approval_id="APR-0001",
        resolution=SubmissionResolution.CONFIRMED,
    )

    with pytest.raises(InvalidWorkspaceState, match="submitted or closed"):
        validate_workspace_state(
            application(
                stage=ApplicationStage.READY_FOR_REVIEW,
                submission_status=SubmissionStatus.CONFIRMED,
                attempts=(confirmed,),
            )
        )


def test_applying_requires_an_active_attempt() -> None:
    with pytest.raises(InvalidWorkspaceState, match="active submission"):
        validate_workspace_state(application(stage=ApplicationStage.APPLYING))


def test_unresolved_uncertain_attempt_blocks_a_new_attempt() -> None:
    uncertain = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.UNCERTAIN,
        approval_id="APR-0001",
    )
    new_attempt = SubmissionAttempt(
        submission_id="SUB-0002",
        status=SubmissionStatus.IN_PROGRESS,
        approval_id="APR-0002",
    )
    before = application(
        stage=ApplicationStage.APPLYING,
        submission_status=SubmissionStatus.UNCERTAIN,
        attempts=(uncertain,),
    )
    after = application(
        stage=ApplicationStage.APPLYING,
        submission_status=SubmissionStatus.IN_PROGRESS,
        attempts=(uncertain, new_attempt),
    )

    with pytest.raises(InvalidTransition, match="uncertain attempt"):
        validate_transition(before, after)


def test_transition_cannot_replace_existing_attempt_history() -> None:
    first = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.IN_PROGRESS,
        approval_id="APR-0001",
    )
    replacement = SubmissionAttempt(
        submission_id="SUB-0002",
        status=SubmissionStatus.IN_PROGRESS,
        approval_id="APR-0002",
    )

    with pytest.raises(InvalidTransition, match="attempt history cannot be replaced"):
        validate_transition(
            application(
                stage=ApplicationStage.APPLYING,
                submission_status=SubmissionStatus.IN_PROGRESS,
                attempts=(first,),
            ),
            application(
                stage=ApplicationStage.APPLYING,
                submission_status=SubmissionStatus.IN_PROGRESS,
                attempts=(replacement,),
            ),
        )


def test_transition_cannot_replace_existing_event_history() -> None:
    first = RecruitingEvent(
        event_id="EVT-0001",
        kind=RecruitingEventKind.INTERVIEW,
        occurred_at=datetime(2026, 9, 18, 10, tzinfo=UTC),
        source_reference="calendar-event-1",
    )
    replacement = RecruitingEvent(
        event_id="EVT-0002",
        kind=RecruitingEventKind.OFFER,
        occurred_at=datetime(2026, 9, 18, 11, tzinfo=UTC),
        source_reference="email-message-2",
    )

    with pytest.raises(InvalidTransition, match="event history cannot be replaced"):
        validate_transition(
            application(events=(first,)),
            application(events=(replacement,)),
        )


def test_current_posting_must_be_the_latest_unique_snapshot() -> None:
    with pytest.raises(InvalidWorkspaceState, match="current posting snapshot"):
        validate_workspace_state(
            application(
                posting_snapshot_ids=("PST-0001", "PST-0002"),
                current_posting_snapshot_id="PST-0001",
            )
        )

    with pytest.raises(InvalidWorkspaceState, match="posting snapshot IDs must be unique"):
        validate_workspace_state(
            application(
                posting_snapshot_ids=("PST-0001", "PST-0001"),
                current_posting_snapshot_id="PST-0001",
            )
        )


def test_transition_cannot_replace_existing_posting_history() -> None:
    with pytest.raises(InvalidTransition, match="posting snapshot history"):
        validate_transition(
            application(
                posting_snapshot_ids=("PST-0001",),
                current_posting_snapshot_id="PST-0001",
            ),
            application(
                posting_snapshot_ids=("PST-0002",),
                current_posting_snapshot_id="PST-0002",
            ),
        )


def test_resolved_unsuccessful_attempt_allows_return_to_approved() -> None:
    unresolved = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.UNCERTAIN,
        approval_id="APR-0001",
    )
    unsuccessful = SubmissionAttempt(
        submission_id="SUB-0001",
        status=SubmissionStatus.UNCERTAIN,
        approval_id="APR-0001",
        resolution=SubmissionResolution.UNSUCCESSFUL,
    )

    validate_transition(
        application(
            stage=ApplicationStage.APPLYING,
            submission_status=SubmissionStatus.UNCERTAIN,
            attempts=(unresolved,),
        ),
        application(
            stage=ApplicationStage.APPROVED,
            submission_status=SubmissionStatus.NONE,
            attempts=(unsuccessful,),
        ),
    )


def test_terminal_outcome_requires_history_and_closed_stage() -> None:
    outcome = OutcomeRecord(
        outcome=Outcome.REJECTED,
        source=OutcomeSource.ATTRIBUTABLE_EVIDENCE,
        source_reference="email-message-42",
    )

    with pytest.raises(InvalidWorkspaceState, match="application history"):
        validate_workspace_state(application(stage=ApplicationStage.CLOSED, outcome=outcome))


@given(st.lists(st.sampled_from(list(RecruitingEventKind)), max_size=5))
def test_recruiting_events_cannot_make_an_application_submitted(
    kinds: list[RecruitingEventKind],
) -> None:
    events = tuple(
        RecruitingEvent(
            event_id=f"EVT-{index:04d}",
            kind=kind,
            occurred_at=datetime(2026, 9, 18, index, tzinfo=UTC),
            source_reference=f"fixture-{index}",
        )
        for index, kind in enumerate(kinds)
    )

    with pytest.raises(InvalidWorkspaceState, match="confirmed submission attempt"):
        validate_workspace_state(
            application(
                stage=ApplicationStage.SUBMITTED,
                submission_status=SubmissionStatus.CONFIRMED,
                events=events,
            )
        )
