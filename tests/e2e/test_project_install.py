"""Execute the published install/launcher contract, without skipping verification."""

import json
import os
import shutil
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


def run(project, *args):
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith("CAREER_"):
            environment.pop(key)
    return subprocess.run(
        args, cwd=project, env=environment, capture_output=True, text=True, check=False
    )


def test_archive_install_no_global_cli_and_nested_launcher(tmp_path):
    archive = tmp_path / "Career Agent ü"
    shutil.copytree(
        PROJECT,
        archive,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".career-agent",
            ".claude",
            ".scratch",
            "workspace",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "dist",
        ),
    )
    windows = os.name == "nt"
    install = (
        ["pwsh", "-File", str(archive / "scripts/install.ps1")]
        if windows
        else ["bash", str(archive / "scripts/install.sh")]
    )
    binding = archive / ".career-agent/workspace.json"
    binding.parent.mkdir()
    stale_binding = json.dumps(
        {
            "schema_version": 1,
            "path": "missing-workspace",
            "workspace_id": "54b71f12-9959-477d-b654-238b70926ff2",
        }
    )
    binding.write_text(stale_binding)
    result = run(archive, *install)
    assert result.returncode == 0, result.stdout + result.stderr
    assert binding.read_text() == stale_binding
    launcher = (
        ["pwsh", "-File", str(archive / "scripts/career.ps1")]
        if windows
        else ["bash", str(archive / "scripts/career.sh")]
    )
    doctor = run(archive / "docs", *launcher, "doctor", "--installation-only", "--json")
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert json.loads(doctor.stdout)["data"]["capability_report"]["installation_ready"]
    workspace = archive / "workspace"
    initialized = run(archive, *launcher, "--workspace", str(workspace), "init", "--json")
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    identity = json.loads(initialized.stdout)["data"]["workspace_id"]
    selected = run(archive, *launcher, "workspace", "select", str(workspace), "--json")
    assert selected.returncode == 0, selected.stderr
    resume = workspace / "inbox/resume.txt"
    resume.write_text("Alex Doe builds reliable products.\n", encoding="utf-8")

    def career(*arguments):
        result = run(archive / "docs", *launcher, *arguments, "--json")
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)["data"]

    preview = career("import", "preview", str(resume))
    assert "Alex Doe" not in json.dumps(preview)
    imported = career("import", "apply", preview["run_id"])
    source_id = imported["imported_sources"][0]["source_id"]
    declined = run(archive, *launcher, "import", "inspect", source_id, "--json")
    assert declined.returncode == 6
    privacy = career("privacy", "status")
    career(
        "privacy",
        "acknowledge",
        "--policy-version",
        privacy["policy_version"],
        "--provider",
        "synthetic-test",
    )
    evidence = career("import", "inspect", source_id)
    source = evidence["source"]
    block = source["blocks"][0]
    proposal = {
        "proposals": [
            {
                "key": "name",
                "value": "Alex Doe",
                "source": {
                    "source_id": source_id,
                    "source_checksum": source["checksum"],
                    "normalized_text_checksum": source["normalized_text_checksum"],
                    "extractor": source["extractor"],
                    "extractor_version": source["extractor_version"],
                    "block_id": block["block_id"],
                    "page_number": block["page_number"],
                    "start_offset": 0,
                    "end_offset": 8,
                    "exact_text": evidence["text"][:8],
                },
            }
        ]
    }
    request = workspace / "inbox/proposal.json"
    request.write_text(json.dumps(proposal))
    proposed = career("profile", "propose", "--input", str(request))
    fact_id = proposed[0]["fact_id"]
    career(
        "profile", "confirm", fact_id, "--value", json.dumps("Alex Doe"), "--source-id", source_id
    )
    preferences = workspace / "inbox/preferences.json"
    preferences.write_text(json.dumps({"target_roles": ["Product Manager"]}))
    career("preferences", "set", "--input", str(preferences))
    assert career("onboarding", "status")["onboarding_ready"]
    before = (archive / ".career-agent/active-runtime").read_text()
    failure_args = ["-SimulateValidationFailure"] if windows else ["--simulate-validation-failure"]
    failed = run(archive, *install, *failure_args)
    assert failed.returncode != 0
    assert (archive / ".career-agent/active-runtime").read_text() == before
    moved = tmp_path / "Moved Agent"
    archive.rename(moved)
    moved_launcher = (
        ["pwsh", "-File", str(moved / "scripts/career.ps1")]
        if windows
        else ["bash", str(moved / "scripts/career.sh")]
    )
    assert run(moved, *moved_launcher, "version", "--json").returncode != 0
    moved_install = (
        ["pwsh", "-File", str(moved / "scripts/install.ps1")]
        if windows
        else ["bash", str(moved / "scripts/install.sh")]
    )
    repaired = run(moved, *moved_install)
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    assert json.loads((moved / "workspace/workspace.json").read_text())["workspace_id"] == identity
    resumed = run(moved / "docs", *moved_launcher, "onboarding", "status", "--json")
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert json.loads(resumed.stdout)["data"]["onboarding_ready"]
    uninstall = ["-Uninstall"] if windows else ["--uninstall"]
    removed = run(moved, *moved_install, *uninstall)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert (moved / "workspace/workspace.json").exists()
    assert not (moved / ".career-agent/active-runtime").exists()
