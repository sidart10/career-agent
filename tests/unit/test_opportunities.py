from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from career_agent.models.opportunity import OpportunityStatus
from career_agent.services.opportunities import OpportunityCapture, OpportunityService
from career_agent.storage.journal import OperationJournal

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def capture(**overrides: object) -> OpportunityCapture:
    values: dict[str, object] = {
        "company": "Example Labs",
        "title": "Senior Product Manager",
        "location": "Remote — US",
        "url": "https://jobs.example.test/roles/42",
        "captured_at": NOW,
        "posting_text": "Build measurement products with engineering.",
        "posting_complete": True,
        "requisition_id": "REQ-42",
    }
    values.update(overrides)
    return OpportunityCapture.model_validate(values)


def test_add_captures_lightweight_opportunity_without_creating_application(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = OpportunityService(workspace)

    opportunity = service.add(capture(), idempotency_key="capture-42")

    assert opportunity.opportunity_id == "OPP-2026-0001"
    assert opportunity.company == "Example Labs"
    assert str(opportunity.canonical_url) == "https://jobs.example.test/roles/42"
    assert service.list() == (opportunity,)
    assert not (workspace / "applications").exists()


def test_add_preserves_non_latin_title_and_marks_past_deadline_expired(tmp_path: Path) -> None:
    service = OpportunityService(tmp_path / "workspace")

    opportunity = service.add(
        capture(
            title="シニアプロダクトマネージャー",
            deadline=date.today() - timedelta(days=1),
            requisition_id="REQ-JP-1",
            url="https://jobs.example.test/roles/jp-1",
        ),
        idempotency_key="capture-jp-1",
    )

    assert opportunity.title == "シニアプロダクトマネージャー"
    assert opportunity.status is OpportunityStatus.EXPIRED


def test_replaying_add_returns_existing_opportunity_without_allocating_another_id(
    tmp_path: Path,
) -> None:
    service = OpportunityService(tmp_path / "workspace")
    first = service.add(capture(), idempotency_key="capture-42")

    second = service.add(capture(), idempotency_key="capture-42")

    assert second == first
    assert len(service.load_state().opportunities) == 1


def test_replay_finishes_add_journal_after_state_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = OpportunityService(workspace)
    real_commit = service.journal.commit
    service.journal.commit = lambda run_id, result: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("interrupt before commit")
    )

    with pytest.raises(RuntimeError, match="interrupt before commit"):
        service.add(capture(), idempotency_key="capture-42")

    service.journal.commit = real_commit  # type: ignore[method-assign]
    replayed = service.add(capture(), idempotency_key="capture-42")
    operation = OperationJournal(workspace).operation_for_key("opportunity-add:capture-42")
    assert replayed.opportunity_id == "OPP-2026-0001"
    assert operation is not None
    assert OperationJournal(workspace).recover(operation.run_id).status.value == "committed"
