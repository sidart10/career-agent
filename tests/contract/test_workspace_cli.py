from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _data(result: Result) -> dict[str, object]:
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    return payload["data"]


def _init(workspace: Path, *, home: Path) -> dict[str, object]:
    result = runner.invoke(
        app,
        ["--workspace", str(workspace), "init", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )
    assert result.exit_code == 0, result.output
    return _data(result)


def test_init_creates_stable_workspace_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    home = tmp_path / "home"

    first = _init(workspace, home=home)
    second = _init(workspace, home=home)

    assert first["workspace_id"] == second["workspace_id"]
    assert uuid.UUID(str(first["workspace_id"]))
    marker = json.loads((workspace / "workspace.json").read_text())
    assert marker == {
        "schema_version": 1,
        "workspace_id": first["workspace_id"],
        "workspace_kind": "single_candidate",
    }
    shown = runner.invoke(
        app,
        ["--workspace", str(workspace), "workspace", "show", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )
    assert json.loads(shown.stdout)["workspace"] == {
        "schema_version": 1,
        "workspace_id": first["workspace_id"],
        "workspace_path": str(workspace.resolve()),
    }


def test_init_rejects_workspace_symlink_and_checkout_overlap(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    symlinked = runner.invoke(
        app,
        ["--workspace", str(alias), "init", "--json"],
        env={"HOME": str(tmp_path / "home"), "CAREER_WORKSPACE": ""},
    )
    assert symlinked.exit_code != 0
    assert json.loads(symlinked.stdout)["error"]["code"] == "unsafe_path"

    overlap = REPOSITORY_ROOT / ".test-workspace-overlap"
    overlapping = runner.invoke(
        app,
        ["--workspace", str(overlap), "init", "--json"],
        env={"HOME": str(tmp_path / "home"), "CAREER_WORKSPACE": ""},
    )
    assert overlapping.exit_code != 0
    assert json.loads(overlapping.stdout)["error"]["code"] == "unsafe_path"
    assert not overlap.exists()


def test_workspace_selection_is_stable_across_current_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "candidate"
    home = tmp_path / "home"
    _init(workspace, home=home)

    selected = runner.invoke(
        app,
        ["workspace", "select", str(workspace), "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )
    assert selected.exit_code == 0, selected.output

    first_directory = tmp_path / "first-directory"
    first_directory.mkdir()
    monkeypatch.chdir(first_directory)
    first = runner.invoke(
        app,
        ["workspace", "show", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    second = runner.invoke(
        app,
        ["workspace", "show", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
        catch_exceptions=False,
    )

    assert first.exit_code == second.exit_code == 0
    assert _data(first) == _data(second)
    assert _data(first)["workspace_path"] == str(workspace.resolve())
    assert _data(first)["source"] == "user_config"


def test_selected_workspace_identity_cannot_silently_change(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    home = tmp_path / "home"
    _init(workspace, home=home)
    selected = runner.invoke(
        app,
        ["workspace", "select", str(workspace), "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )
    assert selected.exit_code == 0, selected.output
    marker = json.loads((workspace / "workspace.json").read_text())
    marker["workspace_id"] = str(uuid.uuid4())
    (workspace / "workspace.json").write_text(json.dumps(marker))

    shown = runner.invoke(
        app,
        ["workspace", "show", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )

    assert shown.exit_code == 4
    assert json.loads(shown.stdout)["error"]["code"] == "conflict"


def test_workspace_precedence_is_cli_then_environment_then_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    configured = tmp_path / "configured"
    environment_workspace = tmp_path / "environment"
    explicit = tmp_path / "explicit"
    for workspace in (configured, environment_workspace, explicit):
        _init(workspace, home=home)
    selected = runner.invoke(
        app,
        ["workspace", "select", str(configured), "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": ""},
    )
    assert selected.exit_code == 0, selected.output

    from_environment = runner.invoke(
        app,
        ["workspace", "show", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": str(environment_workspace)},
    )
    from_cli = runner.invoke(
        app,
        ["--workspace", str(explicit), "workspace", "show", "--json"],
        env={"HOME": str(home), "CAREER_WORKSPACE": str(environment_workspace)},
    )

    assert _data(from_environment)["workspace_path"] == str(environment_workspace.resolve())
    assert _data(from_environment)["source"] == "environment"
    assert _data(from_cli)["workspace_path"] == str(explicit.resolve())
    assert _data(from_cli)["source"] == "cli"
