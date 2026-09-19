from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.services.cleanup import CleanupService
from career_agent.storage.journal import OperationJournal

NOW = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)


def _run_dir(root: Path, run_id: str, content: bytes) -> Path:
    path = root / "runs" / run_id
    path.mkdir(parents=True)
    (path / "bundle.bin").write_bytes(content)
    return path


def _set_age(path: Path, age: timedelta) -> None:
    timestamp = (NOW - age).timestamp()
    os.utime(path, (timestamp, timestamp))


def test_cleanup_is_digest_bound_and_never_crosses_protected_boundaries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    successful = _run_dir(root, "RUN-9000", b"success")
    young_failed = _run_dir(root, "RUN-0002", b"young")
    old_failed = _run_dir(root, "RUN-0003", b"old")
    future_failed = _run_dir(root, "RUN-0004", b"future")
    _set_age(young_failed, timedelta(days=1))
    _set_age(old_failed, timedelta(days=8))
    _set_age(future_failed, timedelta(days=-1))

    journal = OperationJournal(root)
    operation = OperationRecord(
        run_id="RUN-9000",
        operation="synthetic.success",
        idempotency_key="synthetic-success",
        status=OperationStatus.STARTED,
    )
    journal.begin(operation)
    journal.commit("RUN-9000", {"result_references": []})
    for run_id in ("RUN-0002", "RUN-0003"):
        failed = OperationRecord(
            run_id=run_id,
            operation="synthetic.failed",
            idempotency_key=f"synthetic-failed:{run_id}",
            status=OperationStatus.STARTED,
        )
        journal.begin(failed)
        journal.fail(run_id, {"reason": "synthetic failure"})

    external = tmp_path / "external"
    external.mkdir()
    (external / "keep.txt").write_text("keep")
    symlink = root / "runs" / "RUN-0005"
    symlink.symlink_to(external, target_is_directory=True)

    protected = (
        root / "applications" / "APP-2026-0001" / "releases" / "REL-0001" / "resume.pdf",
        root / "applications" / "APP-2026-0001" / "submissions" / "SUB-0001" / "payload.json",
        root / "resources" / "imports" / "SRC-0001" / "original.pdf",
    )
    for path in protected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"protected")

    service = CleanupService(root)
    plan = service.plan(now=NOW)

    assert {item.relative_path for item in plan.items} == {
        "runs/RUN-9000",
        "runs/RUN-0003",
    }
    with pytest.raises(CareerError) as changed:
        service.apply("0" * 64)
    assert changed.value.code is ErrorCode.CONFLICT

    result = service.apply(plan.plan_digest)

    assert set(result.deleted_paths) == {"runs/RUN-9000", "runs/RUN-0003"}
    assert not successful.exists()
    assert not old_failed.exists()
    assert young_failed.exists()
    assert future_failed.exists()
    assert symlink.is_symlink()
    assert (external / "keep.txt").read_text() == "keep"
    assert all(path.read_bytes() == b"protected" for path in protected)
