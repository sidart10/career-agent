from __future__ import annotations

from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.profile import ConfirmationState
from career_agent.services.profile import ProfileService
from career_agent.storage.journal import OperationJournal

FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"


def test_apply_import_records_proposals_and_unresolved_conflicts(tmp_path: Path) -> None:
    service = ProfileService(tmp_path / "workspace")
    preview = service.preview_import(
        [FIXTURES / "consistent.txt", FIXTURES / "conflicting-title.txt"]
    )

    result = service.apply_import(preview.run_id)
    state = service.load_state()

    assert state.facts == ()
    assert {conflict.key for conflict in result.conflicts} == {
        "employment.current_start_date",
        "employment.current_title",
    }
    assert all(conflict.resolved_fact_id is None for conflict in state.conflicts)
    assert all(proposal.fact_id is not None for proposal in state.proposals)


def test_confirm_fact_requires_exact_supported_value_and_source(tmp_path: Path) -> None:
    service = ProfileService(tmp_path / "workspace")
    preview = service.preview_import(
        [FIXTURES / "consistent.txt", FIXTURES / "conflicting-title.txt"]
    )
    result = service.apply_import(preview.run_id)
    selected = next(
        proposal
        for proposal in result.proposed_facts
        if proposal.key == "employment.current_title" and proposal.value == "Senior Product Manager"
    )

    fact = service.confirm_fact(
        selected.fact_id or "",
        selected.value,
        [selected.sources[0].source_id],
    )

    assert fact.confirmation_state is ConfirmationState.CONFIRMED
    assert fact.confirmer == "user"
    assert service.get_confirmed_fact(fact.fact_id) == fact
    conflict = next(item for item in service.load_state().conflicts if item.key == fact.key)
    assert conflict.resolved_fact_id == fact.fact_id
    assert len(conflict.alternatives) == 2


def test_confirm_fact_rejects_changed_value_or_unrelated_source(tmp_path: Path) -> None:
    service = ProfileService(tmp_path / "workspace")
    preview = service.preview_import([FIXTURES / "consistent.txt"])
    result = service.apply_import(preview.run_id)
    proposal = result.proposed_facts[0]

    with pytest.raises(CareerError) as changed_value:
        service.confirm_fact(
            proposal.fact_id or "", "Different Person", [proposal.sources[0].source_id]
        )
    with pytest.raises(CareerError) as unrelated_source:
        service.confirm_fact(proposal.fact_id or "", proposal.value, ["SRC-unrelated"])

    assert changed_value.value.code is ErrorCode.INVALID_INPUT
    assert unrelated_source.value.code is ErrorCode.INVALID_INPUT
    assert service.load_state().facts == ()


def test_unsupported_suggestion_cannot_be_confirmed(tmp_path: Path) -> None:
    source = tmp_path / "suggestion.txt"
    source.write_text("Suggested Claim: Increased revenue by 500%\n")
    service = ProfileService(tmp_path / "workspace")
    preview = service.preview_import([source])
    result = service.apply_import(preview.run_id)
    proposal = result.proposed_facts[0]
    assert proposal.supported is False

    with pytest.raises(CareerError) as error:
        service.confirm_fact(
            proposal.fact_id or "",
            proposal.value,
            [proposal.sources[0].source_id],
        )

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_reapplying_same_run_is_idempotent(tmp_path: Path) -> None:
    service = ProfileService(tmp_path / "workspace")
    preview = service.preview_import([FIXTURES / "consistent.txt"])
    first = service.apply_import(preview.run_id)
    second = service.apply_import(preview.run_id)

    assert second == first
    assert len(service.load_state().proposals) == len(first.proposed_facts)


def test_confirmed_fact_rejects_replay_with_changed_arguments(tmp_path: Path) -> None:
    service = ProfileService(tmp_path / "workspace")
    preview = service.preview_import([FIXTURES / "consistent.txt"])
    result = service.apply_import(preview.run_id)
    proposal = result.proposed_facts[0]
    service.confirm_fact(
        proposal.fact_id or "",
        proposal.value,
        [proposal.sources[0].source_id],
    )

    with pytest.raises(CareerError) as error:
        service.confirm_fact(
            proposal.fact_id or "",
            "a different value",
            [proposal.sources[0].source_id],
        )

    assert error.value.code is ErrorCode.CONFLICT


def test_confirm_fact_commits_a_governed_operation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = ProfileService(workspace)
    preview = service.preview_import([FIXTURES / "consistent.txt"])
    result = service.apply_import(preview.run_id)
    proposal = result.proposed_facts[0]

    service.confirm_fact(
        proposal.fact_id or "",
        proposal.value,
        [proposal.sources[0].source_id],
    )

    journal = OperationJournal(workspace)
    entries = journal.path.read_text().splitlines()
    assert any('"operation":"profile.fact.confirm"' in entry for entry in entries)
    assert any(
        '"event_type":"commit"' in entry and '"run_id":"RUN-0002"' in entry for entry in entries
    )


def test_later_import_extends_conflict_without_losing_prior_alternatives(
    tmp_path: Path,
) -> None:
    service = ProfileService(tmp_path / "workspace")
    first = service.preview_import(
        [FIXTURES / "consistent.txt", FIXTURES / "conflicting-title.txt"]
    )
    service.apply_import(first.run_id)
    third_source = tmp_path / "third-title.txt"
    third_source.write_text("Current Title: Principal Product Manager\n")
    second = service.preview_import([FIXTURES / "consistent.txt", third_source])
    service.apply_import(second.run_id)

    conflict = next(
        item for item in service.load_state().conflicts if item.key == "employment.current_title"
    )
    assert {item.value for item in conflict.alternatives} == {
        "Senior Product Manager",
        "Lead Product Manager",
        "Principal Product Manager",
    }


def test_replaying_later_import_returns_same_canonical_fact_ids(tmp_path: Path) -> None:
    service = ProfileService(tmp_path / "workspace")
    first_preview = service.preview_import([FIXTURES / "consistent.txt"])
    first = service.apply_import(first_preview.run_id)
    second_preview = service.preview_import([FIXTURES / "consistent.txt"])
    second = service.apply_import(second_preview.run_id)

    replayed = service.apply_import(second_preview.run_id)

    assert replayed == second
    first_ids = {item.proposal_id: item.fact_id for item in first.proposed_facts}
    second_ids = {item.proposal_id: item.fact_id for item in second.proposed_facts}
    assert second_ids == first_ids


def test_replay_finishes_import_journal_after_profile_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = ProfileService(workspace)
    preview = service.preview_import([FIXTURES / "consistent.txt"])
    real_commit = service.journal.commit
    service.journal.commit = lambda run_id, result: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("interrupt before commit")
    )

    with pytest.raises(RuntimeError, match="interrupt before commit"):
        service.apply_import(preview.run_id)

    service.journal.commit = real_commit  # type: ignore[method-assign]
    service.apply_import(preview.run_id)

    assert OperationJournal(workspace).recover(preview.run_id).status.value == "committed"


def test_replay_finishes_confirmation_journal_after_profile_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    service = ProfileService(workspace)
    preview = service.preview_import([FIXTURES / "consistent.txt"])
    result = service.apply_import(preview.run_id)
    proposal = result.proposed_facts[0]
    real_commit = service.journal.commit
    service.journal.commit = lambda run_id, payload: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("interrupt before commit")
    )

    with pytest.raises(RuntimeError, match="interrupt before commit"):
        service.confirm_fact(
            proposal.fact_id or "",
            proposal.value,
            [proposal.sources[0].source_id],
        )

    service.journal.commit = real_commit  # type: ignore[method-assign]
    service.confirm_fact(
        proposal.fact_id or "",
        proposal.value,
        [proposal.sources[0].source_id],
    )
    operation = OperationJournal(workspace).operation_for_key(f"profile-confirm:{proposal.fact_id}")
    assert operation is not None
    assert OperationJournal(workspace).recover(operation.run_id).status.value == "committed"
