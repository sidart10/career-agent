from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.services.migrations import MigrationService

from .documents.test_release import setup_workspace as setup_current_workspace


def setup_workspace(root):
    result = setup_current_workspace(root)
    for path in (root / "workspace.json", root / "profile/profile.json"):
        if path.exists():
            payload = json.loads(path.read_text())
            payload["schema_version"] = 1
            payload.pop("rejected_proposals", None)
            path.write_text(json.dumps(payload))
    return result


def test_migration_is_copy_first_and_preserves_legacy_ambiguity(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    setup_workspace(root)
    index_path = root / "applications" / "index.json"
    legacy_index = json.loads(index_path.read_text())
    legacy_index["schema_version"] = 0
    index_path.write_text(json.dumps(legacy_index, sort_keys=True))

    legacy = root / "legacy"
    (legacy / "shared-resumes").mkdir(parents=True)
    (legacy / "shared-resumes" / "resume-final.pdf").write_bytes(b"first")
    (legacy / "shared-resumes" / "resume-final-copy.pdf").write_bytes(b"second")
    (legacy / "2025-01-02" / "application").mkdir(parents=True)
    (legacy / "2025-01-02" / "application" / "resume.aux").write_text("temporary")
    (legacy / "tracker.csv").write_text("status,company\nuncertain,Example\n")
    (legacy / "tracker.json").write_text('{"submission_status":"uncertain"}')
    (legacy / "google-sheet-metadata.json").write_text('{"sheet_id":"remote"}')

    service = MigrationService(root)
    plan = service.plan(target_version=1)

    classifications = {finding.classification for finding in plan.findings}
    assert {
        "shared_resume_folder",
        "duplicate_final_candidate",
        "date_based_application",
        "missing_manifest",
        "temporary_latex",
        "competing_csv_json",
        "uncertain_submission",
        "google_sheet_metadata",
    } <= classifications
    result = service.apply(plan.plan_digest)

    assert json.loads(index_path.read_text())["schema_version"] == 1
    backup = root / result.backup_relative_path / "applications" / "index.json"
    assert json.loads(backup.read_text())["schema_version"] == 0
    backup_manifest = json.loads(
        (root / result.backup_relative_path / "backup-manifest.json").read_text()
    )
    assert backup_manifest["plan_digest"] == plan.plan_digest
    assert any(
        item["relative_path"] == "applications/index.json" for item in backup_manifest["files"]
    )
    assert "applications/index.json" in result.migrated_paths
    assert "legacy/tracker.json" in result.preserved_legacy_paths


def test_migration_aborts_if_plan_changes_or_staged_validation_fails(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    setup_workspace(root)
    index_path = root / "applications" / "index.json"
    original = index_path.read_bytes()
    service = MigrationService(root)
    plan = service.plan(target_version=1)
    index_path.write_bytes(original + b"\n")

    with pytest.raises(CareerError) as changed:
        service.apply(plan.plan_digest)

    assert changed.value.code is ErrorCode.CONFLICT
    assert index_path.read_bytes() == original + b"\n"

    index_path.write_bytes(original)
    malformed = json.loads((root / "opportunities" / "state.json").read_text())
    malformed["schema_version"] = 0
    malformed["opportunities"] = "not-a-list"
    opportunities_path = root / "opportunities" / "state.json"
    opportunities_path.write_text(json.dumps(malformed, sort_keys=True))
    invalid_original = opportunities_path.read_bytes()
    invalid_plan = service.plan(target_version=1)

    with pytest.raises(CareerError) as invalid:
        service.apply(invalid_plan.plan_digest)

    assert invalid.value.code is ErrorCode.INTEGRITY_ERROR
    assert opportunities_path.read_bytes() == invalid_original
