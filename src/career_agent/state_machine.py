"""Explicit lifecycle transitions and cross-dimensional invariants."""

from __future__ import annotations

from career_agent.models.application import ApplicationManifest, ApplicationStage
from career_agent.models.submission import (
    SubmissionResolution,
    SubmissionStatus,
)


class InvalidWorkspaceState(ValueError):
    """Raised when one manifest contains an impossible state combination."""


class InvalidTransition(ValueError):
    """Raised when two valid manifests form a forbidden transition."""


ALLOWED_STAGE_TRANSITIONS: dict[ApplicationStage, frozenset[ApplicationStage]] = {
    ApplicationStage.PREPARING: frozenset(
        {ApplicationStage.PREPARING, ApplicationStage.READY_FOR_REVIEW, ApplicationStage.CLOSED}
    ),
    ApplicationStage.READY_FOR_REVIEW: frozenset(
        {
            ApplicationStage.READY_FOR_REVIEW,
            ApplicationStage.PREPARING,
            ApplicationStage.APPROVED,
            ApplicationStage.CLOSED,
        }
    ),
    ApplicationStage.APPROVED: frozenset(
        {
            ApplicationStage.APPROVED,
            ApplicationStage.PREPARING,
            ApplicationStage.APPLYING,
            ApplicationStage.CLOSED,
        }
    ),
    ApplicationStage.APPLYING: frozenset(
        {
            ApplicationStage.APPLYING,
            ApplicationStage.APPROVED,
            ApplicationStage.SUBMITTED,
            ApplicationStage.CLOSED,
        }
    ),
    ApplicationStage.SUBMITTED: frozenset({ApplicationStage.SUBMITTED, ApplicationStage.CLOSED}),
    ApplicationStage.CLOSED: frozenset({ApplicationStage.CLOSED}),
}


def validate_workspace_state(application: ApplicationManifest) -> None:
    """Reject cross-dimensional combinations that cannot be truthful."""

    attempt_ids = [attempt.submission_id for attempt in application.attempts]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise InvalidWorkspaceState("submission attempt IDs must be unique")

    event_ids = [event.event_id for event in application.events]
    if len(event_ids) != len(set(event_ids)):
        raise InvalidWorkspaceState("recruiting event IDs must be unique")

    posting_ids = application.posting_snapshot_ids
    if len(posting_ids) != len(set(posting_ids)):
        raise InvalidWorkspaceState("posting snapshot IDs must be unique")
    expected_current = posting_ids[-1] if posting_ids else None
    if application.current_posting_snapshot_id != expected_current:
        raise InvalidWorkspaceState("current posting snapshot must be the latest snapshot")

    release_ids = application.release_ids
    if len(release_ids) != len(set(release_ids)):
        raise InvalidWorkspaceState("release IDs must be unique")
    expected_release = release_ids[-1] if release_ids else None
    if application.current_release_id != expected_release:
        raise InvalidWorkspaceState("current release must be the latest release")

    confirmed_attempts = [
        attempt
        for attempt in application.attempts
        if attempt.status is SubmissionStatus.CONFIRMED
        and attempt.resolution is SubmissionResolution.CONFIRMED
    ]
    if application.stage is ApplicationStage.SUBMITTED and not confirmed_attempts:
        raise InvalidWorkspaceState("submitted requires a confirmed submission attempt")
    if (
        application.stage is ApplicationStage.SUBMITTED
        and application.submission_status is not SubmissionStatus.CONFIRMED
    ):
        raise InvalidWorkspaceState("submitted requires confirmed submission status")

    if application.submission_status is SubmissionStatus.UNCERTAIN:
        if application.stage is not ApplicationStage.APPLYING:
            raise InvalidWorkspaceState("an uncertain submission must remain applying")
        if not application.attempts:
            raise InvalidWorkspaceState("uncertain status requires an uncertain attempt")
        latest = application.attempts[-1]
        if latest.status is not SubmissionStatus.UNCERTAIN or latest.resolution is not None:
            raise InvalidWorkspaceState("uncertain status requires an unresolved uncertain attempt")

    if application.submission_status is SubmissionStatus.IN_PROGRESS:
        if application.stage is not ApplicationStage.APPLYING:
            raise InvalidWorkspaceState("an in-progress submission must be applying")
        if (
            not application.attempts
            or application.attempts[-1].status is not SubmissionStatus.IN_PROGRESS
        ):
            raise InvalidWorkspaceState("in-progress status requires an active attempt")

    if application.submission_status is SubmissionStatus.CONFIRMED and not confirmed_attempts:
        raise InvalidWorkspaceState("confirmed status requires a confirmed submission attempt")
    if application.submission_status is SubmissionStatus.CONFIRMED and application.stage not in {
        ApplicationStage.SUBMITTED,
        ApplicationStage.CLOSED,
    }:
        raise InvalidWorkspaceState("confirmed status requires a submitted or closed stage")

    if application.stage is ApplicationStage.APPLYING and application.submission_status not in {
        SubmissionStatus.IN_PROGRESS,
        SubmissionStatus.UNCERTAIN,
    }:
        raise InvalidWorkspaceState("applying requires an active submission status")

    if application.stage is ApplicationStage.CLOSED:
        if application.submission_status in {
            SubmissionStatus.IN_PROGRESS,
            SubmissionStatus.UNCERTAIN,
        }:
            raise InvalidWorkspaceState("closed cannot retain an active submission status")
        if application.outcome is None and not application.closure_reason:
            raise InvalidWorkspaceState("administrative closure requires a closure reason")
    elif application.outcome is not None:
        raise InvalidWorkspaceState("an outcome requires the closed stage")

    if application.outcome is not None and not application.attempts and not application.events:
        raise InvalidWorkspaceState("an outcome requires application history")


def validate_transition(before: ApplicationManifest, after: ApplicationManifest) -> None:
    """Validate identity, stage movement, history, and uncertainty rules."""

    if (
        before.application_id != after.application_id
        or before.opportunity_id != after.opportunity_id
    ):
        raise InvalidTransition("application and opportunity identity cannot change")

    if after.stage not in ALLOWED_STAGE_TRANSITIONS[before.stage]:
        raise InvalidTransition(f"stage transition {before.stage} -> {after.stage} is not allowed")

    validate_workspace_state(before)

    if len(after.attempts) < len(before.attempts):
        raise InvalidTransition("submission attempt history cannot shrink")
    if len(after.events) < len(before.events):
        raise InvalidTransition("recruiting event history cannot shrink")
    before_attempt_ids = tuple(attempt.submission_id for attempt in before.attempts)
    after_attempt_prefix = tuple(
        attempt.submission_id for attempt in after.attempts[: len(before.attempts)]
    )
    if before_attempt_ids != after_attempt_prefix:
        raise InvalidTransition("submission attempt history cannot be replaced")
    before_event_ids = tuple(event.event_id for event in before.events)
    after_event_prefix = tuple(event.event_id for event in after.events[: len(before.events)])
    if before_event_ids != after_event_prefix:
        raise InvalidTransition("recruiting event history cannot be replaced")
    if len(after.posting_snapshot_ids) < len(before.posting_snapshot_ids):
        raise InvalidTransition("posting snapshot history cannot shrink")
    if (
        after.posting_snapshot_ids[: len(before.posting_snapshot_ids)]
        != before.posting_snapshot_ids
    ):
        raise InvalidTransition("posting snapshot history cannot be replaced")
    if len(after.release_ids) < len(before.release_ids):
        raise InvalidTransition("release history cannot shrink")
    if after.release_ids[: len(before.release_ids)] != before.release_ids:
        raise InvalidTransition("release history cannot be replaced")

    unresolved_uncertain = any(
        attempt.status is SubmissionStatus.UNCERTAIN and attempt.resolution is None
        for attempt in before.attempts
    )
    if unresolved_uncertain and len(after.attempts) > len(before.attempts):
        raise InvalidTransition("an unresolved uncertain attempt blocks a new attempt")

    validate_workspace_state(after)
