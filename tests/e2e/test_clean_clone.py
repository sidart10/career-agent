from __future__ import annotations

import json
import os
import platform
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
    if platform.system() == "Windows":
        install_command = [
            "pwsh",
            "-File",
            str(clone / "scripts" / "install.ps1"),
            "-SkipPythonInstall",
            "-SkipDoctor",
        ]
    else:
        install_command = [
            "bash",
            str(clone / "scripts" / "install.sh"),
            "--skip-python-install",
            "--skip-doctor",
        ]
    result = subprocess.run(
        install_command,
        cwd=clone,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    workspace = tmp_path / "synthetic-workspace"
    initialized = subprocess.run(
        ["uv", "run", "--project", str(clone), "career", "init", "--json"],
        cwd=clone,
        env={**os.environ, "CAREER_WORKSPACE": str(workspace)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert initialized.returncode == 0, initialized.stderr
    assert (workspace / "workspace.json").is_file()
    latex_name = "lualatex.bat" if platform.system() == "Windows" else "lualatex"
    latex = tmp_path / "bin" / latex_name
    latex.parent.mkdir()
    latex.write_text(
        "@exit /b 0\n" if platform.system() == "Windows" else "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )
    latex.chmod(0o755)

    manifest = json.loads(
        (clone / ".career-agent" / "install-manifest.json").read_text(encoding="utf-8")
    )

    for runtime, relative in (
        ("claude_code", Path(".claude/skills")),
        ("codex", Path(".agents/skills")),
    ):
        installed_skill = clone / relative / "career-apply"
        assert installed_skill.is_dir()
        if manifest["installed_modes"][runtime] == "link":
            assert installed_skill.is_symlink()
        else:
            assert (installed_skill / "SKILL.md").is_file()
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
