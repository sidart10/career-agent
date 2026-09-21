from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.journal import OperationJournal


def operation(run_id: str = "RUN-0001", key: str = "application-42") -> OperationRecord:
    return OperationRecord(
        run_id=run_id,
        operation="application.create",
        idempotency_key=key,
        status=OperationStatus.STARTED,
    )


def test_journal_recovers_operation_from_hash_chained_events(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    original = operation()

    journal.begin(original)
    journal.checkpoint(
        original.run_id, "application-allocated", {"application_id": "APP-2026-0001"}
    )
    journal.commit(original.run_id, {"result_references": ["APP-2026-0001"]})

    recovered = journal.recover(original.run_id)
    entries = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert recovered.status is OperationStatus.COMMITTED
    assert recovered.checkpoints == ("application-allocated",)
    assert recovered.result_references == ("APP-2026-0001",)
    assert entries[0]["previous_hash"] is None
    assert entries[1]["previous_hash"] == entries[0]["entry_hash"]
    assert entries[2]["previous_hash"] == entries[1]["entry_hash"]


def test_repeating_identical_events_does_not_append_duplicates(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    original = operation()
    result = {"result_references": ["APP-2026-0001"]}

    journal.begin(original)
    journal.begin(original)
    journal.checkpoint(original.run_id, "allocated", {"id": "APP-2026-0001"})
    journal.checkpoint(original.run_id, "allocated", {"id": "APP-2026-0001"})
    journal.commit(original.run_id, result)
    journal.commit(original.run_id, result)

    assert len(journal.path.read_text().splitlines()) == 3


def test_replay_returns_committed_result_for_idempotency_key(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    original = operation()
    result = {
        "application_id": "APP-2026-0001",
        "result_references": ["APP-2026-0001"],
    }
    journal.begin(original)
    journal.commit(original.run_id, result)

    replay = journal.replay(original.idempotency_key)

    assert replay is not None
    assert replay.run_id == original.run_id
    assert replay.result == result


def test_reusing_in_progress_idempotency_key_for_another_run_conflicts(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    journal.begin(operation())

    with pytest.raises(CareerError) as error:
        journal.begin(operation(run_id="RUN-0002"))

    assert error.value.code is ErrorCode.CONFLICT


def test_changed_checkpoint_payload_conflicts_instead_of_rewriting_history(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    journal.begin(operation())
    journal.checkpoint("RUN-0001", "allocated", {"id": "APP-2026-0001"})

    with pytest.raises(CareerError) as error:
        journal.checkpoint("RUN-0001", "allocated", {"id": "APP-2026-0002"})

    assert error.value.code is ErrorCode.CONFLICT


def test_tampered_complete_event_breaks_integrity_verification(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    journal.begin(operation())
    journal.checkpoint("RUN-0001", "allocated", {"id": "APP-2026-0001"})
    content = journal.path.read_text().replace("APP-2026-0001", "APP-2026-9999")
    journal.path.write_text(content)

    with pytest.raises(CareerError) as error:
        journal.recover("RUN-0001")

    assert error.value.code is ErrorCode.INTEGRITY_ERROR


def test_incomplete_final_event_is_ignored_during_recovery(tmp_path: Path) -> None:
    journal = OperationJournal(tmp_path)
    journal.begin(operation())
    with journal.path.open("ab") as stream:
        stream.write(b'{"event_type":"checkpoint"')

    assert journal.recover("RUN-0001").status is OperationStatus.STARTED
