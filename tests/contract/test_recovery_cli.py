from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal

from ..unit.documents.test_release import setup_workspace

runner = CliRunner()


def test_doctor_is_read_only_and_recovery_requires_preview_then_apply(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    manifest_path = root / "applications" / application_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    journal = OperationJournal(root)

    safe = OperationRecord(
        run_id="RUN-9000",
        operation="application.transition",
        idempotency_key=f"application-transition:{application_id}:synthetic",
        status=OperationStatus.STARTED,
    )
    journal.begin(safe)
    journal.checkpoint("RUN-9000", "manifest-prepared", {"manifest": manifest})
    journal.checkpoint(
        "RUN-9000",
        "manifest-written",
        {"checksum": sha256_file(manifest_path)},
    )
    ambiguous = OperationRecord(
        run_id="RUN-9001",
        operation="external.synthetic-side-effect",
        idempotency_key="synthetic-ambiguous-recovery",
        status=OperationStatus.STARTED,
    )
    journal.begin(ambiguous)

    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }

    result = runner.invoke(
        app,
        ["doctor", "--json"],
        env={"CAREER_WORKSPACE": str(root)},
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["recovery"]["recoverable_run_ids"] == ["RUN-9000"]
    assert data["recovery"]["quarantine_run_ids"] == ["RUN-9001"]
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert journal.recover("RUN-9000").status is OperationStatus.STARTED
    assert journal.recover("RUN-9001").status is OperationStatus.STARTED
    assert not (root / "maintenance").exists()

    preview = runner.invoke(
        app,
        ["recover", "plan", "--json"],
        env={"CAREER_WORKSPACE": str(root)},
    )
    assert preview.exit_code == 0, preview.output
    plan = json.loads(preview.stdout)["data"]
    assert plan["recoverable_run_ids"] == ["RUN-9000"]
    assert plan["quarantine_run_ids"] == ["RUN-9001"]

    applied = runner.invoke(
        app,
        ["recover", "apply", plan["plan_digest"], "--json"],
        env={"CAREER_WORKSPACE": str(root)},
    )
    assert applied.exit_code == 0, applied.output
    recovery = json.loads(applied.stdout)["data"]
    assert recovery["recovered_run_ids"] == ["RUN-9000"]
    assert recovery["quarantined_run_ids"] == ["RUN-9001"]
    assert journal.recover("RUN-9000").status is OperationStatus.COMMITTED
    assert journal.recover("RUN-9001").status is OperationStatus.FAILED
    assert (root / "maintenance" / "recovery" / "RUN-9001.json").is_file()
