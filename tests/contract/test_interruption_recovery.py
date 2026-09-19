from __future__ import annotations

import json
import multiprocessing
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

import pytest

from career_agent.models.application import (
    ApplicationManifest,
    RecruitingEvent,
    RecruitingEventKind,
)
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.journal import OperationJournal
from career_agent.storage.repository import ApplicationRepository


def _terminate(exit_code: int) -> NoReturn:
    os._exit(exit_code)


def _crash_atomic_write(target: str, phase: str) -> None:
    import career_agent.storage.atomic as atomic_module

    if phase == "before-replace":
        atomic_module.os.replace = lambda source, destination: _terminate(91)
    elif phase == "after-replace":
        atomic_module._fsync_directory = lambda path: _terminate(92)
    atomic_module.atomic_write_json(Path(target), {"state": "new"})


def _operation(run_id: str, key: str) -> OperationRecord:
    return OperationRecord(
        run_id=run_id,
        operation="application.update",
        idempotency_key=key,
        status=OperationStatus.STARTED,
    )


def _crash_before_repository_commit(root: str) -> None:
    repository = ApplicationRepository(Path(root))

    def stop_before_commit(run_id: str, result: object) -> NoReturn:
        _terminate(93)

    repository.journal.commit = stop_before_commit  # type: ignore[method-assign]

    def add_event(current: ApplicationManifest | None) -> ApplicationManifest:
        assert current is not None
        event = RecruitingEvent(
            event_id="EVT-0001",
            kind=RecruitingEventKind.STATUS,
            occurred_at=datetime.now(UTC),
            source_reference="portal-status",
        )
        return current.model_copy(update={"events": (*current.events, event)})

    repository.mutate("APP-2026-0001", _operation("RUN-0002", "update-1"), add_event)


@pytest.mark.parametrize(
    ("phase", "expected_state", "exit_code"),
    [("before-replace", "old", 91), ("after-replace", "new", 92)],
)
def test_atomic_crash_leaves_old_or_new_valid_json(
    tmp_path: Path,
    phase: str,
    expected_state: str,
    exit_code: int,
) -> None:
    target = tmp_path / "record.json"
    atomic_write_json(target, {"state": "old"})
    context = multiprocessing.get_context("spawn")
    worker = context.Process(target=_crash_atomic_write, args=(str(target), phase))

    worker.start()
    worker.join(timeout=10)

    assert worker.exitcode == exit_code
    assert json.loads(target.read_text()) == {"state": expected_state}


def test_replay_after_manifest_replacement_finishes_original_operation_once(
    tmp_path: Path,
) -> None:
    repository = ApplicationRepository(tmp_path)
    repository.create(
        ApplicationManifest(
            application_id="APP-2026-0001",
            opportunity_id="OPP-2026-0001",
        ),
        OperationRecord(
            run_id="RUN-0001",
            operation="application.create",
            idempotency_key="create-1",
            status=OperationStatus.STARTED,
        ),
    )
    context = multiprocessing.get_context("spawn")
    worker = context.Process(target=_crash_before_repository_commit, args=(str(tmp_path),))
    worker.start()
    worker.join(timeout=10)
    assert worker.exitcode == 93
    assert [event.event_id for event in repository.load("APP-2026-0001").events] == ["EVT-0001"]
    assert OperationJournal(tmp_path).recover("RUN-0002").status is OperationStatus.STARTED

    def must_not_reapply(current: ApplicationManifest | None) -> ApplicationManifest:
        raise AssertionError("the prepared checkpoint must be replayed instead")

    recovered = repository.mutate(
        "APP-2026-0001",
        _operation("RUN-0003", "update-1"),
        must_not_reapply,
    )

    assert [event.event_id for event in recovered.events] == ["EVT-0001"]
    journal = OperationJournal(tmp_path)
    assert journal.recover("RUN-0002").status is OperationStatus.COMMITTED
    assert journal.operation_for_key("update-1") is not None
    assert journal.operation_for_key("update-1").run_id == "RUN-0002"  # type: ignore[union-attr]
