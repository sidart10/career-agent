from __future__ import annotations

import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock

import pytest

import career_agent.storage.locks as locks_module
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


def test_workspace_lock_serializes_threads_when_platform_lock_is_process_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ProcessScopedLock:
        def acquire(self) -> None:
            return None

        def release(self) -> None:
            return None

    monkeypatch.setattr(
        locks_module.portalocker,
        "Lock",
        lambda *args, **kwargs: ProcessScopedLock(),
    )
    real_write = locks_module.atomic_write_json
    observation_lock = Lock()
    active_writes = 0
    maximum_active_writes = 0

    def observed_write(path: Path, value: object) -> None:
        nonlocal active_writes, maximum_active_writes
        with observation_lock:
            active_writes += 1
            maximum_active_writes = max(maximum_active_writes, active_writes)
        try:
            time.sleep(0.01)
            real_write(path, value)  # type: ignore[arg-type]
        finally:
            with observation_lock:
                active_writes -= 1

    monkeypatch.setattr(locks_module, "atomic_write_json", observed_write)
    barrier = Barrier(4)
    workspace_locks = [WorkspaceLock(tmp_path, run_id=f"RUN-{index:04d}") for index in range(4)]

    def hold_lock(index: int) -> None:
        barrier.wait()
        with workspace_locks[index]:
            time.sleep(0.01)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(hold_lock, range(4)))

    assert maximum_active_writes == 1


def test_process_lock_identity_does_not_depend_on_path_existence(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    before_creation = WorkspaceLock(root, run_id="RUN-0001")
    before_creation.path.parent.mkdir(parents=True)
    after_creation = WorkspaceLock(root, run_id="RUN-0002")

    assert before_creation._process_lock is after_creation._process_lock


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
