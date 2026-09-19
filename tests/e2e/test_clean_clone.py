from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from career_agent.services.capabilities import CapabilityService

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_clean_source_copy_installs_both_runtimes_and_reports_required_readiness(
    tmp_path: Path,
) -> None:
    clone = tmp_path / "career-agent-clone"
    shutil.copytree(
        REPOSITORY_ROOT,
        clone,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".career",
            ".career-agent",
            ".agents",
            ".claude",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".scratch",
            ".superpowers",
            "__pycache__",
            "README.md",
        ),
    )
    synced = subprocess.run(
        ["uv", "sync", "--frozen", "--project", str(clone)],
        cwd=clone,
        check=False,
        capture_output=True,
        text=True,
    )
    assert synced.returncode == 0, synced.stderr
    result = subprocess.run(
        [
            "bash",
            str(clone / "scripts" / "install.sh"),
            "--skip-python-install",
            "--skip-doctor",
        ],
        cwd=clone,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    latex = tmp_path / "bin" / "lualatex"
    latex.parent.mkdir()
    latex.write_text("#!/bin/sh\nexit 0\n")
    latex.chmod(0o755)

    for runtime, relative in (
        ("claude_code", Path(".claude/skills")),
        ("codex", Path(".agents/skills")),
    ):
        assert (clone / relative / "career-apply").is_symlink()
        report = CapabilityService(clone / ".career", clone).report(
            environment={
                "CAREER_RUNTIME": runtime,
                "CAREER_BROWSER_CAPABILITY": "1",
                "CAREER_APPROVAL_CAPABILITY": "1",
                "PATH": f"{latex.parent}{os.pathsep}{os.environ.get('PATH', '')}",
            }
        )
        assert report.runtime == runtime
        assert report.release_ready is True

    journey = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(clone),
            "pytest",
            "tests/e2e/test_happy_path.py",
            "-q",
        ],
        cwd=clone,
        check=False,
        capture_output=True,
        text=True,
    )
    assert journey.returncode == 0, journey.stdout + journey.stderr
    assert "1 passed" in journey.stdout
