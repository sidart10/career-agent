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


def test_doctor_recovers_safe_checkpoint_and_quarantines_ambiguity(tmp_path: Path) -> None:
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

    result = runner.invoke(
        app,
        ["doctor", "--json"],
        env={"CAREER_WORKSPACE": str(root)},
    )

    assert result.exit_code == 0, result.output
    recovery = json.loads(result.stdout)["data"]["recovery"]
    assert recovery["recovered_run_ids"] == ["RUN-9000"]
    assert recovery["quarantined_run_ids"] == ["RUN-9001"]
    assert journal.recover("RUN-9000").status is OperationStatus.COMMITTED
    assert journal.recover("RUN-9001").status is OperationStatus.FAILED
    assert (root / "maintenance" / "recovery" / "RUN-9001.json").is_file()
