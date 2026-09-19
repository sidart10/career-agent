from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.locks import ApplicationLock, WorkspaceLock


def test_workspace_lock_records_owner_and_heartbeat(tmp_path: Path) -> None:
    lock = WorkspaceLock(tmp_path, run_id="RUN-0001", timeout=0.1)

    with lock:
        initial = json.loads(lock.path.read_text())
        lock.heartbeat()
        refreshed = json.loads(lock.path.read_text())

    assert initial["pid"] == os.getpid()
    assert initial["host"] == socket.gethostname()
    assert initial["run_id"] == "RUN-0001"
    assert initial["scope"] == "workspace"
    assert datetime.fromisoformat(refreshed["heartbeat_at"]) >= datetime.fromisoformat(
        initial["heartbeat_at"]
    )


def test_second_workspace_lock_fails_with_stable_conflict(tmp_path: Path) -> None:
    with (
        WorkspaceLock(tmp_path, run_id="RUN-0001", timeout=0.1),
        pytest.raises(CareerError) as error,
        WorkspaceLock(tmp_path, run_id="RUN-0002", timeout=0.01),
    ):
        pytest.fail("a contending lock must not enter")

    assert error.value.code is ErrorCode.CONFLICT
    assert error.value.details["owner_run_id"] == "RUN-0001"


def test_application_locks_isolate_different_applications(tmp_path: Path) -> None:
    with (
        ApplicationLock(tmp_path, "APP-2026-0001", run_id="RUN-0001", timeout=0.1),
        ApplicationLock(tmp_path, "APP-2026-0002", run_id="RUN-0002", timeout=0.1),
    ):
        pass


def test_application_lock_rejects_same_application_contention(tmp_path: Path) -> None:
    with (
        ApplicationLock(tmp_path, "APP-2026-0001", run_id="RUN-0001", timeout=0.1),
        pytest.raises(CareerError) as error,
        ApplicationLock(
            tmp_path,
            "APP-2026-0001",
            run_id="RUN-0002",
            timeout=0.01,
        ),
    ):
        pytest.fail("a contending lock must not enter")

    assert error.value.code is ErrorCode.CONFLICT


def test_lock_marks_recovery_only_for_expired_absent_local_owner(tmp_path: Path) -> None:
    path = tmp_path / ".locks" / "workspace.lock"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "host": socket.gethostname(),
                "run_id": "RUN-0001",
                "scope": "workspace",
                "acquired_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                "heartbeat_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            }
        )
    )
    lock = WorkspaceLock(
        tmp_path,
        run_id="RUN-0002",
        timeout=0.1,
        stale_after=timedelta(minutes=5),
    )

    with lock:
        metadata = json.loads(path.read_text())

    assert lock.recovered_stale is True
    assert metadata["recovered_owner"]["run_id"] == "RUN-0001"


def test_lock_does_not_mark_live_local_owner_metadata_as_recovered(tmp_path: Path) -> None:
    path = tmp_path / ".locks" / "workspace.lock"
    path.parent.mkdir(parents=True)
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "run_id": "RUN-0001",
                "scope": "workspace",
                "acquired_at": old,
                "heartbeat_at": old,
            }
        )
    )
    lock = WorkspaceLock(
        tmp_path,
        run_id="RUN-0002",
        timeout=0.1,
        stale_after=timedelta(minutes=5),
    )

    with lock:
        metadata = json.loads(path.read_text())

    assert lock.recovered_stale is False
    assert "recovered_owner" not in metadata
