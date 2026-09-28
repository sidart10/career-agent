from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_platform_matrix_initializes_and_asserts_each_readiness_layer() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "os: [ubuntu-latest, macos-latest, windows-latest]" in workflow
    assert "bash scripts/career.sh init --json" in workflow
    assert "pwsh -File scripts/career.ps1 init --json" in workflow
    assert "uv run career" not in workflow
    assert "brew install --cask basictex" in workflow
    assert "mactex-no-gui" not in workflow
    assert 'echo "/Library/TeX/texbin" >> "$GITHUB_PATH"' in workflow
    assert "Add-Content -Path $env:GITHUB_PATH -Value $texBin" in workflow
    assert "scripts/assert_readiness.py --layer core" in workflow
    assert "scripts/assert_readiness.py --layer document" in workflow
    assert "scripts/assert_readiness.py --layer submission" in workflow
    assert 'CAREER_BROWSER_CAPABILITY: "1"' in workflow
    assert 'CAREER_APPROVAL_CAPABILITY: "1"' in workflow
    assert 'skills-ref validate "$skill"' in workflow
    assert "69ef37e9424c0a7ea9dd2293b559e43ec8176379" in workflow


def test_layered_readiness_assertion_rejects_only_the_requested_layer() -> None:
    command = ["uv", "run", "python", "scripts/assert_readiness.py", "--layer", "core"]
    rejected = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        input=json.dumps(
            {
                "ok": True,
                "data": {
                    "capability_report": {
                        "core_ready": False,
                        "document_ready": False,
                        "submission_ready": False,
                    }
                },
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
                "data": {
                    "capability_report": {
                        "core_ready": True,
                        "document_ready": False,
                        "submission_ready": False,
                    }
                },
                "error": None,
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert rejected.returncode == 1
    assert "core readiness failed" in rejected.stderr
    assert accepted.returncode == 0
