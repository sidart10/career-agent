from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.config import initialize_workspace

from ..unit.documents.test_release import setup_workspace

runner = CliRunner()
NOW = datetime(2026, 9, 18, 20, 30, tzinfo=UTC)


class _CliResult(Protocol):
    stdout: str


def _data(result: _CliResult) -> dict[str, object]:
    return json.loads(result.stdout)["data"]


def test_maintenance_cli_preview_apply_contracts(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    initialize_workspace(root)
    application_id, _ = setup_workspace(root)
    old_run = root / "runs" / "RUN-9000"
    old_run.mkdir(parents=True)
    (old_run / "failed.log").write_text("failed")
    timestamp = (NOW - timedelta(days=8)).timestamp()
    os.utime(old_run, (timestamp, timestamp))
    environment = {"CAREER_WORKSPACE": str(root)}

    cleanup_plan = runner.invoke(app, ["cleanup", "--json"], env=environment)
    assert cleanup_plan.exit_code == 0, cleanup_plan.output
    cleanup_digest = _data(cleanup_plan)["plan_digest"]
    cleaned = runner.invoke(
        app,
        ["cleanup", "--apply", str(cleanup_digest), "--json"],
        env=environment,
    )
    assert cleaned.exit_code == 0, cleaned.output
    assert not old_run.exists()

    # Exercise the legacy record migration on a legacy workspace fixture.
    for path in (root / "workspace.json", root / "profile/profile.json"):
        if path.exists():
            payload = json.loads(path.read_text())
            payload["schema_version"] = 1
            payload.pop("rejected_proposals", None)
            path.write_text(json.dumps(payload))
    migration_plan = runner.invoke(
        app,
        ["migrate", "plan", "--target-version", "1", "--json"],
        env=environment,
    )
    assert migration_plan.exit_code == 0, migration_plan.output
    migration_digest = _data(migration_plan)["plan_digest"]
    migrated = runner.invoke(
        app,
        ["migrate", "apply", str(migration_digest), "--json"],
        env=environment,
    )
    assert migrated.exit_code == 0, migrated.output

    # Legacy record migration does not upgrade the workspace layout. Explicitly
    # approve format 2 before exercising governed reset writes.
    layout_plan = runner.invoke(
        app, ["migrate", "plan", "--target-version", "2", "--json"], env=environment
    )
    assert layout_plan.exit_code == 0, layout_plan.output
    layout_applied = runner.invoke(
        app, ["migrate", "apply", _data(layout_plan)["plan_digest"], "--json"], env=environment
    )
    assert layout_applied.exit_code == 0, layout_applied.output

    reset_plan = runner.invoke(
        app,
        ["reset", "preview", "--scope", "generated_drafts", "--json"],
        env=environment,
    )
    assert reset_plan.exit_code == 0, reset_plan.output
    reset_digest = _data(reset_plan)["plan_digest"]
    reset = runner.invoke(
        app,
        ["reset", "apply", str(reset_digest), "--json"],
        env=environment,
    )
    assert reset.exit_code == 0, reset.output
    assert not (root / "applications" / application_id / "drafts").exists()
