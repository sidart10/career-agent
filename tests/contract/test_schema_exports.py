from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "export_schemas.py"
EXPECTED_SCHEMAS = {
    "answer-record.schema.json",
    "application-manifest.schema.json",
    "approval-record.schema.json",
    "document-release.schema.json",
    "import-preview.schema.json",
    "import-result.schema.json",
    "operation-record.schema.json",
    "opportunity.schema.json",
    "profile-fact.schema.json",
    "profile-state.schema.json",
    "submission-attempt.schema.json",
}


def run_export(output_dir: Path, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT), "--output-dir", str(output_dir)]
    if check:
        command.append("--check")
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_schema_export_is_complete_and_deterministic(tmp_path: Path) -> None:
    first = run_export(tmp_path)
    assert first.returncode == 0, first.stderr
    first_bytes = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}

    second = run_export(tmp_path)
    assert second.returncode == 0, second.stderr
    second_bytes = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}

    assert set(first_bytes) == EXPECTED_SCHEMAS
    assert second_bytes == first_bytes
    for encoded in first_bytes.values():
        schema = json.loads(encoded)
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schema_version"]["const"] == 1


def test_check_mode_reports_schema_drift(tmp_path: Path) -> None:
    generated = run_export(tmp_path)
    assert generated.returncode == 0, generated.stderr
    drifted = tmp_path / "application-manifest.schema.json"
    drifted.write_text("{}\n", encoding="utf-8")

    checked = run_export(tmp_path, check=True)

    assert checked.returncode == 1
    assert "application-manifest.schema.json" in checked.stderr
    assert "schema drift" in checked.stderr.lower()
