from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import (
    ApplicationManifest,
    RecruitingEvent,
    RecruitingEventKind,
)
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.journal import OperationJournal
from career_agent.storage.repository import ApplicationRepository


def _operation(run_id: str, key: str, name: str = "application.update") -> OperationRecord:
    return OperationRecord(
        run_id=run_id,
        operation=name,
        idempotency_key=key,
        status=OperationStatus.STARTED,
    )


def _append_event(
    root: str,
    run_id: str,
    event_id: str,
    output: multiprocessing.Queue[str],
) -> None:
    repository = ApplicationRepository(Path(root))

    def transform(current: ApplicationManifest | None) -> ApplicationManifest:
        assert current is not None
        event = RecruitingEvent(
            event_id=event_id,
            kind=RecruitingEventKind.STATUS,
            occurred_at=datetime.now(UTC),
            source_reference=f"worker-{event_id}",
        )
        return current.model_copy(update={"events": (*current.events, event)})

    saved = repository.mutate(
        "APP-2026-0001",
        _operation(run_id, f"append-{event_id}"),
        transform,
    )
    output.put(saved.application_id)


def test_repository_creates_and_loads_validated_manifest(tmp_path: Path) -> None:
    repository = ApplicationRepository(tmp_path)
    manifest = ApplicationManifest(
        application_id="APP-2026-0001",
        opportunity_id="OPP-2026-0001",
    )

    saved = repository.create(manifest, _operation("RUN-0001", "create-1", "application.create"))

    assert saved == manifest
    assert repository.load(manifest.application_id) == manifest
    assert OperationJournal(tmp_path).recover("RUN-0001").status is OperationStatus.COMMITTED


def test_concurrent_application_writers_preserve_both_updates_and_journals(
    tmp_path: Path,
) -> None:
    repository = ApplicationRepository(tmp_path)
    repository.create(
        ApplicationManifest(
            application_id="APP-2026-0001",
            opportunity_id="OPP-2026-0001",
        ),
        _operation("RUN-0001", "create-1", "application.create"),
    )
    context = multiprocessing.get_context("spawn")
    output: multiprocessing.Queue[str] = context.Queue()
    workers = [
        context.Process(
            target=_append_event,
            args=(str(tmp_path), "RUN-0002", "EVT-0001", output),
        ),
        context.Process(
            target=_append_event,
            args=(str(tmp_path), "RUN-0003", "EVT-0002", output),
        ),
    ]

    for worker in workers:
        worker.start()
    # Drain before join so child queue feeder threads cannot deadlock on a full pipe.
    results = [output.get(timeout=10) for _ in workers]
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0

    assert results == ["APP-2026-0001"] * 2
    saved = repository.load("APP-2026-0001")
    assert {event.event_id for event in saved.events} == {"EVT-0001", "EVT-0002"}
    journal = OperationJournal(tmp_path)
    assert journal.recover("RUN-0002").status is OperationStatus.COMMITTED
    assert journal.recover("RUN-0003").status is OperationStatus.COMMITTED


def test_committed_idempotency_key_returns_existing_result_without_new_events(
    tmp_path: Path,
) -> None:
    repository = ApplicationRepository(tmp_path)
    manifest = ApplicationManifest(
        application_id="APP-2026-0001",
        opportunity_id="OPP-2026-0001",
    )
    operation = _operation("RUN-0001", "create-1", "application.create")
    repository.create(manifest, operation)
    event_count = len(OperationJournal(tmp_path).path.read_text().splitlines())

    replayed = repository.create(manifest, operation)

    assert replayed == manifest
    assert len(OperationJournal(tmp_path).path.read_text().splitlines()) == event_count


def test_interrupted_idempotency_key_cannot_resume_against_another_application(
    tmp_path: Path,
) -> None:
    repository = ApplicationRepository(tmp_path)
    journal = OperationJournal(tmp_path)
    operation = _operation("RUN-0001", "update-1")
    prepared = ApplicationManifest(
        application_id="APP-2026-0001",
        opportunity_id="OPP-2026-0001",
    )
    journal.begin(operation)
    journal.checkpoint(
        operation.run_id,
        "manifest-prepared",
        {"manifest": prepared.model_dump(mode="json")},
    )

    with pytest.raises(CareerError) as error:
        repository.mutate(
            "APP-2026-0002",
            _operation("RUN-0002", "update-1"),
            lambda current: prepared,
        )

    assert error.value.code is ErrorCode.CONFLICT
    assert not (tmp_path / "applications" / "APP-2026-0002" / "manifest.json").exists()
