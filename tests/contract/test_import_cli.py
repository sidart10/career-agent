from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"


def test_import_preview_and_apply_use_json_envelopes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "resume.txt"
    source.write_text("Name: Avery Example\nCurrent Title: Product Manager\n")
    environment = {"CAREER_WORKSPACE": str(workspace)}

    preview_result = runner.invoke(
        app,
        ["import", "preview", str(source), "--json"],
        env=environment,
    )
    assert preview_result.exit_code == 0
    preview = json.loads(preview_result.stdout)
    assert preview["ok"] is True
    assert preview["data"]["run_id"] == "RUN-0001"
    assert not (workspace / "resources").exists()

    apply_result = runner.invoke(
        app,
        ["import", "apply", preview["data"]["run_id"], "--json"],
        env=environment,
    )
    assert apply_result.exit_code == 0
    applied = json.loads(apply_result.stdout)
    assert applied["ok"] is True
    stored = Path(applied["data"]["imported_sources"][0]["stored_path"])
    assert stored.read_bytes() == source.read_bytes()


def test_profile_conflicts_and_confirm_are_exposed_through_cli(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    environment = {"CAREER_WORKSPACE": str(workspace)}
    preview_result = runner.invoke(
        app,
        [
            "import",
            "preview",
            str(FIXTURES / "consistent.txt"),
            str(FIXTURES / "conflicting-title.txt"),
            "--json",
        ],
        env=environment,
    )
    preview = json.loads(preview_result.stdout)
    apply_result = runner.invoke(
        app,
        ["import", "apply", preview["data"]["run_id"], "--json"],
        env=environment,
    )
    applied = json.loads(apply_result.stdout)
    selected = next(
        proposal
        for proposal in applied["data"]["proposed_facts"]
        if proposal["key"] == "employment.current_title"
        and proposal["value"] == "Senior Product Manager"
    )

    conflicts_result = runner.invoke(
        app,
        ["profile", "conflicts", "--json"],
        env=environment,
    )
    conflicts = json.loads(conflicts_result.stdout)
    assert conflicts_result.exit_code == 0
    assert {item["key"] for item in conflicts["data"]} == {
        "employment.current_start_date",
        "employment.current_title",
    }

    confirm_result = runner.invoke(
        app,
        [
            "profile",
            "confirm",
            selected["fact_id"],
            "--value",
            json.dumps(selected["value"]),
            "--source-id",
            selected["sources"][0]["source_id"],
            "--json",
        ],
        env=environment,
    )
    confirmed = json.loads(confirm_result.stdout)
    assert confirm_result.exit_code == 0
    assert confirmed["data"]["confirmation_state"] == "confirmed"


def test_import_cli_returns_typed_error_without_traceback(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["import", "apply", "RUN-9999", "--json"],
        env={"CAREER_WORKSPACE": str(tmp_path / "workspace")},
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"
    assert "Traceback" not in result.output
