from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_platform_matrix_initializes_and_asserts_doctor_release_readiness() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "os: [ubuntu-latest, macos-latest, windows-latest]" in workflow
    assert "uv run career init --json" in workflow
    assert 'echo "/Library/TeX/texbin" >> "$GITHUB_PATH"' in workflow
    assert "Add-Content -Path $env:GITHUB_PATH -Value $texBin" in workflow
    assert "uv run career doctor --json | uv run python scripts/assert_release_ready.py" in workflow


def test_release_ready_assertion_rejects_a_nonready_doctor_report() -> None:
    command = ["uv", "run", "python", "scripts/assert_release_ready.py"]
    rejected = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        input=json.dumps(
            {
                "ok": True,
                "data": {"capability_report": {"release_ready": False}},
                "error": None,
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    accepted = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        input=json.dumps(
            {
                "ok": True,
                "data": {"capability_report": {"release_ready": True}},
                "error": None,
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode == 1
    assert "not release ready" in rejected.stderr
    assert accepted.returncode == 0
