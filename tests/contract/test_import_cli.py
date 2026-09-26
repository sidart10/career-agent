from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.config import initialize_workspace

runner = CliRunner()
FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"


def test_import_preview_and_apply_use_json_envelopes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
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
    assert not (workspace / "resources" / "imports").exists()

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
    initialize_workspace(workspace)
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
    initialize_workspace(tmp_path / "workspace")
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


def test_import_apply_can_select_only_successful_sources(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
    good = tmp_path / "resume.txt"
    bad = tmp_path / "scan.bin"
    good.write_text("Avery Example\nProduct Manager\n")
    bad.write_bytes(b"\x00\x01\x02")
    environment = {"CAREER_WORKSPACE": str(workspace)}

    preview_result = runner.invoke(
        app,
        ["import", "preview", str(good), str(bad), "--json"],
        env=environment,
    )
    preview = json.loads(preview_result.stdout)["data"]
    good_source = next(
        source for source in preview["source_files"] if source["extraction_status"] == "extracted"
    )
    bad_source = next(
        source
        for source in preview["source_files"]
        if source["source_id"] != good_source["source_id"]
    )

    applied_result = runner.invoke(
        app,
        [
            "import",
            "apply",
            preview["run_id"],
            "--source-id",
            good_source["source_id"],
            "--json",
        ],
        env=environment,
    )

    assert applied_result.exit_code == 0, applied_result.output
    applied = json.loads(applied_result.stdout)["data"]
    assert [item["source_id"] for item in applied["imported_sources"]] == [good_source["source_id"]]
    assert not (workspace / "resources" / "imports" / bad_source["source_id"]).exists()


def test_selective_import_can_be_completed_incrementally(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace)
    first_source = tmp_path / "resume.txt"
    second_source = tmp_path / "portfolio.txt"
    first_source.write_text("Name: Avery Example\nCurrent Title: Product Manager\n")
    second_source.write_text("Name: Avery Example\nCurrent Company: Example Labs\n")
    environment = {"CAREER_WORKSPACE": str(workspace)}

    preview_result = runner.invoke(
        app,
        ["import", "preview", str(first_source), str(second_source), "--json"],
        env=environment,
    )
    preview = json.loads(preview_result.stdout)["data"]
    source_ids = [source["source_id"] for source in preview["source_files"]]

    first_apply = runner.invoke(
        app,
        [
            "import",
            "apply",
            preview["run_id"],
            "--source-id",
            source_ids[0],
            "--json",
        ],
        env=environment,
    )
    assert first_apply.exit_code == 0, first_apply.output
    first_result = json.loads(first_apply.stdout)["data"]
    assert {source["source_id"] for source in first_result["imported_sources"]} == {source_ids[0]}

    pending = runner.invoke(app, ["onboarding", "status", "--json"], env=environment)
    assert pending.exit_code == 0, pending.output
    assert json.loads(pending.stdout)["data"]["pending_imports"] == 1

    second_apply = runner.invoke(
        app,
        [
            "import",
            "apply",
            preview["run_id"],
            "--source-id",
            source_ids[1],
            "--json",
        ],
        env=environment,
    )
    assert second_apply.exit_code == 0, second_apply.output
    second_result = json.loads(second_apply.stdout)["data"]
    assert {source["source_id"] for source in second_result["imported_sources"]} == set(source_ids)

    complete = runner.invoke(app, ["onboarding", "status", "--json"], env=environment)
    assert complete.exit_code == 0, complete.output
    assert json.loads(complete.stdout)["data"]["pending_imports"] == 0
