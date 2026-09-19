from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationStage, RecruitingEventKind
from career_agent.models.opportunity import OpportunityStatus
from career_agent.services.applications import ApplicationService
from career_agent.services.opportunities import OpportunityCapture, OpportunityService
from career_agent.services.postings import (
    PostingCapture,
    PostingChangeClassification,
    PostingService,
)

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def create_application(root: Path) -> tuple[str, str]:
    opportunity_id = (
        OpportunityService(root)
        .add(
            OpportunityCapture(
                company="Example Labs",
                title="Senior Product Manager",
                location="Remote",
                url="https://jobs.example.test/roles/42?utm_source=feed",
                captured_at=NOW,
                posting_text="Lead measurement products.\nPartner with engineering.",
                posting_complete=True,
                requisition_id="REQ-42",
            ),
            idempotency_key="capture-42",
        )
        .opportunity_id
    )
    application = ApplicationService(root).create_from_opportunity(opportunity_id, "pursue-42")
    return application.application_id, opportunity_id


def capture(**updates: object) -> PostingCapture:
    values: dict[str, object] = {
        "raw_text": "Lead measurement products.\nPartner with engineering.",
        "source_url": "https://jobs.example.test/roles/42?utm_campaign=new",
        "retrieved_at": NOW,
        "source_adapter": "fixture",
        "source_adapter_metadata": {"request_id": "request-2"},
        "availability": "open",
        "responsibilities": (
            "Lead measurement products.",
            "Partner with engineering.",
        ),
        "location": "Remote",
        "compensation": "$180k-$220k",
        "eligibility": "US work authorization",
        "deadline": "2026-10-01",
        "requisition_id": "REQ-42",
    }
    values.update(updates)
    return PostingCapture.model_validate(values)


def test_whitespace_reordering_and_tracking_parameters_are_not_material(
    tmp_path: Path,
) -> None:
    service = PostingService(tmp_path)
    previous = service.snapshot_from_capture("APP-2026-0001", "PST-0001", capture())
    current = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0002",
        capture(
            raw_text="  Partner with engineering.\n\n Lead measurement products. ",
            source_url="https://jobs.example.test/roles/42?utm_source=other",
            responsibilities=(
                "Partner with engineering.",
                "Lead measurement products.",
            ),
        ),
    )

    change = service.compare(previous, current)

    assert change.classification is PostingChangeClassification.NONE
    assert change.material_fields == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("responsibilities", ("Own pricing strategy.",)),
        ("location", "New York, NY"),
        ("compensation", "$150k-$170k"),
        ("eligibility", "No sponsorship available"),
        ("deadline", "2026-09-20"),
        ("requisition_id", "REQ-99"),
    ],
)
def test_structured_posting_changes_are_material(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    service = PostingService(tmp_path)
    previous = service.snapshot_from_capture("APP-2026-0001", "PST-0001", capture())
    current = service.snapshot_from_capture("APP-2026-0001", "PST-0002", capture(**{field: value}))

    change = service.compare(previous, current)

    assert change.classification is PostingChangeClassification.MATERIAL
    assert field in change.material_fields


def test_availability_change_to_unknown_is_material(tmp_path: Path) -> None:
    service = PostingService(tmp_path)
    previous = service.snapshot_from_capture("APP-2026-0001", "PST-0001", capture())
    current = service.snapshot_from_capture(
        "APP-2026-0001", "PST-0002", capture(availability="unknown")
    )

    change = service.compare(previous, current)

    assert change.classification is PostingChangeClassification.MATERIAL
    assert "availability" in change.material_fields


def test_unstructured_responsibility_change_is_uncertain_and_material(
    tmp_path: Path,
) -> None:
    service = PostingService(tmp_path)
    previous = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0001",
        capture(responsibilities=(), raw_text="Build the product."),
    )
    current = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0002",
        capture(responsibilities=(), raw_text="Sell the product."),
    )

    change = service.compare(previous, current)

    assert change.classification is PostingChangeClassification.UNCERTAIN
    assert change.is_material is True
    assert "responsibilities" in change.material_fields


def test_schema_validated_responsibility_classifier_can_mark_cosmetic_change(
    tmp_path: Path,
) -> None:
    service = PostingService(
        tmp_path,
        responsibility_classifier=lambda _before, _after: {
            "classification": "unchanged",
            "rationale": "Same duties with rewritten prose",
        },
    )
    previous = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0001",
        capture(responsibilities=(), raw_text="Build the product."),
    )
    current = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0002",
        capture(responsibilities=(), raw_text="You will build our product."),
    )

    assert service.compare(previous, current).classification is PostingChangeClassification.NONE


def test_invalid_responsibility_classifier_output_fails_closed(tmp_path: Path) -> None:
    service = PostingService(
        tmp_path,
        responsibility_classifier=lambda _before, _after: {"classification": "maybe"},
    )
    previous = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0001",
        capture(responsibilities=(), raw_text="Build the product."),
    )
    current = service.snapshot_from_capture(
        "APP-2026-0001",
        "PST-0002",
        capture(responsibilities=(), raw_text="Sell the product."),
    )

    change = service.compare(previous, current)

    assert change.classification is PostingChangeClassification.UNCERTAIN
    assert change.is_material is True


def test_material_change_preserves_original_and_invalidates_approval(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, _ = create_application(root)
    applications = ApplicationService(root)
    applications.transition(application_id, ApplicationStage.READY_FOR_REVIEW, "drafts ready")
    applications.transition(application_id, ApplicationStage.APPROVED, "approved by user")
    postings = PostingService(root)
    original_path = postings.path(application_id, "PST-0001")
    original_bytes = original_path.read_bytes()

    current = postings.capture(application_id, capture(location="New York, NY"))
    previous = postings.load(application_id, "PST-0001")
    change = postings.compare(previous, current)
    updated = postings.apply_freshness(application_id, change)

    assert original_path.read_bytes() == original_bytes
    assert updated.posting_snapshot_ids == ("PST-0001", "PST-0002")
    assert updated.current_posting_snapshot_id == "PST-0002"
    assert updated.stage is ApplicationStage.PREPARING
    assert updated.approval_invalidated_at is not None
    assert updated.events[-1].kind is RecruitingEventKind.STATUS
    assert (root / "applications" / application_id / "posting-changes" / "PST-0002.json").is_file()


def test_closure_expires_opportunity_and_preserves_application_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, opportunity_id = create_application(root)
    applications = ApplicationService(root)
    applications.transition(application_id, ApplicationStage.READY_FOR_REVIEW, "drafts ready")
    before = applications.load(application_id)
    postings = PostingService(root)

    current = postings.capture(
        application_id,
        capture(availability="closed", raw_text="This role has been filled."),
    )
    change = postings.compare(postings.load(application_id, "PST-0001"), current)
    updated = postings.apply_freshness(application_id, change)

    assert updated.posting_closed_at is not None
    assert updated.events[: len(before.events)] == before.events
    assert OpportunityService(root).get(opportunity_id).status is OpportunityStatus.EXPIRED

    with pytest.raises(CareerError) as error:
        applications.transition(application_id, ApplicationStage.APPLYING, "start attempt")
    assert error.value.code is ErrorCode.NOT_READY
    assert "closed posting" in str(error.value).lower()


def test_stale_change_set_cannot_be_applied_after_a_newer_capture(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = create_application(root)
    postings = PostingService(root)
    original = postings.load(application_id, "PST-0001")
    second = postings.capture(application_id, capture(location="New York, NY"))
    stale_change = postings.compare(original, second)
    postings.capture(application_id, capture(location="Chicago, IL"))

    with pytest.raises(CareerError) as error:
        postings.apply_freshness(application_id, stale_change)

    assert error.value.code is ErrorCode.CONFLICT
    assert not postings.change_path(application_id, "PST-0002").exists()


def test_change_history_is_immutable_and_identical_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, _ = create_application(root)
    postings = PostingService(root)
    original = postings.load(application_id, "PST-0001")
    current = postings.capture(application_id, capture(location="New York, NY"))
    change = postings.compare(original, current)

    first = postings.apply_freshness(application_id, change)
    change_bytes = postings.change_path(application_id, "PST-0002").read_bytes()
    replayed = postings.apply_freshness(application_id, change)

    assert replayed == first
    assert postings.change_path(application_id, "PST-0002").read_bytes() == change_bytes
