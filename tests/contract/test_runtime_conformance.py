from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from career_agent.cli import app
from career_agent.config import initialize_workspace
from career_agent.services.capabilities import (
    CapabilityService,
    CapabilityStatus,
    SkillInstallManifest,
    hash_skill_tree,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "runtime" / "capability-matrix.json"
runner = CliRunner()


def _install_link_manifest(root: Path, runtime: str) -> dict[str, str]:
    assert runtime == "codex"
    target = REPOSITORY_ROOT / ".agents" / "skills"
    now = datetime.now(UTC).isoformat()
    manifest = SkillInstallManifest(
        created_at=now,
        updated_at=now,
        product_version="0.1.0",
        skill_bundle_version="0.1.0",
        skill_api_version="1.0",
        supported_cli_range=">=0.1.0,<0.2.0",
        source_revision="git:synthetic",
        canonical_source=str(target),
        source_checksum=hash_skill_tree(target),
        installed_targets={runtime: str(target)},
        installed_modes={runtime: "canonical"},
        managed_paths=(),
    )
    path = root / ".career-agent" / "install-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json())
    return {
        "CAREER_RUNTIME": runtime,
        "CAREER_BROWSER_CAPABILITY": "1",
        "CAREER_APPROVAL_CAPABILITY": "1",
        "CAREER_INSTALL_MANIFEST": str(path),
    }


def test_capability_matrix_required_and_optional_degradation(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    matrix = json.loads(MATRIX_PATH.read_text())
    assert matrix["schema_version"] == 1
    assert matrix["runtimes"] == ["claude_code", "codex"]
    expected_capabilities = matrix["capabilities"]
    environment = _install_link_manifest(root, "codex")
    executable = tmp_path / "bin" / "lualatex"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    environment["PATH"] = f"{executable.parent}{os.pathsep}{os.environ.get('PATH', '')}"

    report = CapabilityService(root, REPOSITORY_ROOT).report(environment=environment)

    assert report.runtime == "codex"
    assert report.core_ready is True
    assert report.document_ready is True
    assert report.submission_ready is True
    assert {check.name for check in report.capabilities} == {
        item["name"] for item in expected_capabilities
    }
    assert all(set(item["providers"]) == {"claude_code", "codex"} for item in expected_capabilities)
    assert report.release_ready is True
    assert {"automated_discovery", "gmail_sync", "notion_sync", "delegation"} <= set(
        report.degraded_workflows
    )
    assert all(
        check.status is CapabilityStatus.READY for check in report.capabilities if check.required
    )

    missing_browser = dict(environment)
    missing_browser.pop("CAREER_BROWSER_CAPABILITY")
    blocked = CapabilityService(root, REPOSITORY_ROOT).report(environment=missing_browser)

    browser = next(check for check in blocked.capabilities if check.name == "browser_control")
    assert browser.status is CapabilityStatus.MISSING_REQUIRED
    assert blocked.core_ready is True
    assert blocked.document_ready is True
    assert blocked.submission_ready is False
    assert blocked.release_ready is False

    missing_approval = dict(environment)
    missing_approval.pop("CAREER_APPROVAL_CAPABILITY")
    blocked = CapabilityService(root, REPOSITORY_ROOT).report(environment=missing_approval)

    approval = next(check for check in blocked.capabilities if check.name == "approval_authority")
    assert approval.status is CapabilityStatus.MISSING_REQUIRED
    assert blocked.core_ready is True
    assert blocked.submission_ready is False
    assert blocked.release_ready is False


def _normalized_state(root: Path) -> object:
    state = json.loads((root / "opportunities" / "state.json").read_text())

    def strip_timestamps(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: strip_timestamps(item)
                for key, item in value.items()
                if key not in {"captured_at", "created_at", "updated_at"}
            }
        if isinstance(value, list):
            return [strip_timestamps(item) for item in value]
        return value

    return strip_timestamps(state)


def test_runtime_adapters_produce_equivalent_governed_state(tmp_path: Path) -> None:
    posting = tmp_path / "posting.txt"
    posting.write_text("Build reliable product systems.")
    roots = {runtime: tmp_path / runtime for runtime in ("claude_code", "codex")}
    for runtime, root in roots.items():
        initialize_workspace(root)
        environment = {
            "CAREER_WORKSPACE": str(root),
            "CAREER_RUNTIME": runtime,
        }
        result = runner.invoke(
            app,
            [
                "opportunity",
                "add",
                "--company",
                "Example Labs",
                "--title",
                "Product Manager",
                "--location",
                "Remote",
                "--url",
                "https://jobs.example.test/roles/42",
                "--posting",
                str(posting),
                "--posting-complete",
                "--idempotency-key",
                "runtime-conformance-42",
                "--json",
            ],
            env=environment,
        )
        assert result.exit_code == 0, result.output

    assert _normalized_state(roots["claude_code"]) == _normalized_state(roots["codex"])
