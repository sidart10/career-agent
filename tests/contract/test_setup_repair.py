"""Regression tests for the actual first-run and path failures."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from career_agent.cli import app

runner = CliRunner()
PROJECT = Path(__file__).resolve().parents[2]


def legacy_plan(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.layout_migration import LayoutMigrationService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    marker = root / "workspace.json"
    data = json.loads(marker.read_text())
    data["schema_version"] = 1
    marker.write_text(json.dumps(data))
    service = LayoutMigrationService(root)
    plan = service.plan()
    return root, service, plan


def test_migration_rejects_symlinked_plan_directory(tmp_path):
    import pytest

    from career_agent.errors import CareerError

    root, service, plan = legacy_plan(tmp_path)
    directory = root / "maintenance/layout-migrations" / plan["plan_digest"]
    outside = tmp_path / "outside"
    directory.rename(outside)
    directory.symlink_to(outside, target_is_directory=True)
    with pytest.raises(CareerError):
        service.apply(plan["plan_digest"])
    assert not (outside / "backup").exists()
    assert json.loads((root / "workspace.json").read_text())["schema_version"] == 1


@pytest.mark.parametrize("payload", ["[]", "null", "{}", '{"files": [null]}', "not-json"])
def test_malformed_migration_plan_returns_error_envelope(tmp_path, payload):
    root, _, plan = legacy_plan(tmp_path)
    path = root / "maintenance/layout-migrations" / plan["plan_digest"] / "plan.json"
    path.write_text(payload)
    result = runner.invoke(
        app, ["--workspace", str(root), "migrate", "apply", plan["plan_digest"], "--json"]
    )
    assert result.exit_code == 5, result.output
    assert json.loads(result.output)["error"]["code"] == "integrity_error"


@pytest.mark.parametrize(
    "relative", ["plan.json", "result.json", "backup/workspace.json", "staged/workspace.json"]
)
def test_migration_rejects_symlinked_record_before_mutation(tmp_path, relative):
    from career_agent.errors import CareerError

    root, service, plan = legacy_plan(tmp_path)
    directory = root / "maintenance/layout-migrations" / plan["plan_digest"]
    path = directory / relative
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes() if path.exists() else b"untouched")
    before = outside.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    path.symlink_to(outside)
    with pytest.raises(CareerError):
        service.apply(plan["plan_digest"])
    assert outside.read_bytes() == before
    assert json.loads((root / "workspace.json").read_text())["schema_version"] == 1


def test_layout_migration_records_are_versioned(tmp_path):
    _, service, plan = legacy_plan(tmp_path)
    assert plan["schema_version"] == 1
    assert service.apply(plan["plan_digest"])["schema_version"] == 1


def test_corrected_evidence_is_interpreted_after_rejections(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.onboarding import OnboardingService
    from career_agent.services.privacy import PRIVACY_POLICY_VERSION, PrivacyService
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    service.apply_import(
        service.preview_import([PROJECT / "tests/fixtures/imports/consistent.txt"]).run_id
    )
    PrivacyService(root).acknowledge(PRIVACY_POLICY_VERSION, "test")
    for proposal in service.pending_proposals():
        service.reject_fact(proposal.fact_id, "Incorrect")
    corrected = tmp_path / "corrected.txt"
    corrected.write_text("Alex built reliable products at Acme for five years.")
    service.apply_import(service.preview_import([corrected]).run_id)
    assert OnboardingService(root, PROJECT).status().first_incomplete_phase == "interpretation"


def test_rejected_conflicts_agree_across_public_commands(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.onboarding import OnboardingService
    from career_agent.services.privacy import PRIVACY_POLICY_VERSION, PrivacyService
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    service.apply_import(
        service.preview_import(
            [
                PROJECT / "tests/fixtures/imports/consistent.txt",
                PROJECT / "tests/fixtures/imports/conflicting-title.txt",
            ]
        ).run_id
    )
    PrivacyService(root).acknowledge(PRIVACY_POLICY_VERSION, "test")
    for proposal in service.pending_proposals():
        service.reject_fact(proposal.fact_id, "Incorrect")
    result = runner.invoke(app, ["--workspace", str(root), "profile", "conflicts", "--json"])
    assert result.exit_code == 0, result.output
    assert (
        len(json.loads(result.output)["data"])
        == OnboardingService(root, PROJECT).status().unresolved_conflicts
        == 0
    )


def test_explicit_project_allows_visible_workspace(tmp_path, monkeypatch):
    project = tmp_path / "Career Agent ü"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "career-agent"\n')
    (project / ".agents/skills").mkdir(parents=True)
    monkeypatch.setenv("CAREER_WORKSPACE", "")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr("career_agent.config._configured_workspace", lambda: None)
    result = runner.invoke(app, ["--project", str(project), "init", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["workspace_path"] == str(project / "workspace")
    assert data["schema_version"] == 2
    assert (project / "workspace/inbox").is_dir()
    assert (project / "workspace/README.md").is_file()


def test_doctor_from_subfolder_finds_same_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_WORKSPACE", str(tmp_path / "candidate"))
    monkeypatch.setenv("CAREER_RUNTIME", "codex")
    monkeypatch.chdir(PROJECT)
    first = runner.invoke(app, ["doctor", "--json"])
    monkeypatch.chdir(PROJECT / "docs")
    second = runner.invoke(app, ["doctor", "--json"])

    def installation(result):
        assert result.exit_code == 0, result.output
        checks = json.loads(result.output)["data"]["capability_report"]["capabilities"]
        return next(item for item in checks if item["name"] == "skill_installation")

    assert installation(first) == installation(second)


def test_relocated_import_paths_stay_inside_workspace(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    preview = service.preview_import([PROJECT / "tests/fixtures/imports/consistent.txt"])
    service.apply_import(preview.run_id)
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    imported = ProfileService(moved).load_state().imported_sources[0]
    assert not Path(imported.stored_path).is_absolute()
    assert (moved / imported.stored_path).is_file()
    assert (moved / imported.extracted_text_path).is_file()


def test_rejected_and_resolved_proposals_do_not_block_review(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.onboarding import OnboardingService
    from career_agent.services.privacy import PRIVACY_POLICY_VERSION, PrivacyService
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    preview = service.preview_import(
        [
            PROJECT / "tests/fixtures/imports/consistent.txt",
            PROJECT / "tests/fixtures/imports/conflicting-title.txt",
        ]
    )
    service.apply_import(preview.run_id)
    PrivacyService(root).acknowledge(PRIVACY_POLICY_VERSION, "test")
    seen = set()
    for proposal in service.load_state().proposals:
        if proposal.key not in seen and proposal.supported:
            service.confirm_fact(proposal.fact_id, proposal.value, [proposal.sources[0].source_id])
            seen.add(proposal.key)
    for proposal in service.pending_proposals():
        service.reject_fact(proposal.fact_id, "Not relevant")
    status = OnboardingService(root, PROJECT).status()
    assert status.pending_proposals == 0
    assert status.profile_review_complete


def test_import_preview_does_not_disclose_text_before_consent(tmp_path):
    root = tmp_path / "workspace"
    assert runner.invoke(app, ["--workspace", str(root), "init", "--json"]).exit_code == 0
    result = runner.invoke(
        app,
        [
            "--workspace",
            str(root),
            "import",
            "preview",
            str(PROJECT / "tests/fixtures/imports/consistent.txt"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert all("extracted_text" not in source for source in data["source_files"])
    assert not data.get("proposed_facts")


def test_legacy_workspace_migration_is_explicit_and_portable(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    service.apply_import(
        service.preview_import([PROJECT / "tests/fixtures/imports/consistent.txt"]).run_id
    )
    marker = root / "workspace.json"
    payload = json.loads(marker.read_text())
    payload["schema_version"] = 1
    marker.write_text(json.dumps(payload))
    path = root / "profile/profile.json"
    legacy = json.loads(path.read_text())
    legacy["schema_version"] = 1
    legacy.pop("rejected_proposals", None)
    for source in legacy["imported_sources"]:
        for key in ("stored_path", "extracted_text_path"):
            source[key] = str(root / source[key])
    path.write_text(json.dumps(legacy))
    before = path.read_bytes()
    blocked = runner.invoke(
        app,
        [
            "--workspace",
            str(root),
            "profile",
            "reject",
            "FACT-0001",
            "--reason",
            "not relevant",
            "--json",
        ],
    )
    assert blocked.exit_code == 3, blocked.output
    assert path.read_bytes() == before
    result = runner.invoke(
        app, ["--workspace", str(root), "migrate", "plan", "--target-version", "2", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert path.read_bytes() == before
    digest = json.loads(result.output)["data"]["plan_digest"]
    applied = runner.invoke(app, ["--workspace", str(root), "migrate", "apply", digest, "--json"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(marker.read_text())["schema_version"] == 2
    assert not Path(
        json.loads(path.read_text())["imported_sources"][0]["stored_path"]
    ).is_absolute()
    repeated = runner.invoke(app, ["--workspace", str(root), "migrate", "apply", digest, "--json"])
    assert repeated.exit_code == 0, repeated.output


def test_provider_change_requires_new_acknowledgement(tmp_path, monkeypatch):
    import pytest

    from career_agent.errors import CareerError
    from career_agent.services.privacy import PRIVACY_POLICY_VERSION, PrivacyService

    service = PrivacyService(tmp_path / "workspace")
    service.acknowledge(PRIVACY_POLICY_VERSION, "provider-a")
    monkeypatch.setenv("CAREER_MODEL_PROVIDER", "provider-b")
    assert not service.status().acknowledged
    with pytest.raises(CareerError):
        service.require_acknowledgement()


def test_provider_can_switch_back_and_recover_commit(tmp_path, monkeypatch):
    import pytest

    from career_agent.services.privacy import PRIVACY_POLICY_VERSION, PrivacyService

    service = PrivacyService(tmp_path / "workspace")
    service.acknowledge(PRIVACY_POLICY_VERSION, "provider-a")
    service.acknowledge(PRIVACY_POLICY_VERSION, "provider-b")
    service.acknowledge(PRIVACY_POLICY_VERSION, "provider-a")
    original = service.journal.commit

    def interrupted(*args, **kwargs):
        raise OSError("interrupted consent")

    monkeypatch.setattr(service.journal, "commit", interrupted)
    with pytest.raises(OSError):
        service.acknowledge(PRIVACY_POLICY_VERSION, "provider-c")
    monkeypatch.setattr(service.journal, "commit", original)
    service.acknowledge(PRIVACY_POLICY_VERSION, "provider-c")
    assert service.status().provider == "provider-c"
    assert all(op.status.value == "committed" for op in service.journal.operations())


def test_initialization_rejects_symlinked_governed_directory(tmp_path):
    import pytest

    from career_agent.config import initialize_workspace
    from career_agent.errors import CareerError

    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "profile").symlink_to(outside, target_is_directory=True)
    with pytest.raises(CareerError):
        initialize_workspace(root)
    assert not (root / "workspace.json").exists()


def test_project_binding_rejects_relative_escape(tmp_path, monkeypatch):
    from career_agent.config import initialize_workspace

    project = tmp_path / "project"
    (project / ".agents/skills").mkdir(parents=True)
    (project / "pyproject.toml").write_text('[project]\nname = "career-agent"\n')
    (project / ".career-agent").mkdir()
    identity = initialize_workspace(tmp_path / "outside")
    (project / ".career-agent/workspace.json").write_text(
        json.dumps(
            {"schema_version": 1, "path": "../outside", "workspace_id": identity["workspace_id"]}
        )
    )
    monkeypatch.delenv("CAREER_WORKSPACE", raising=False)
    result = runner.invoke(app, ["--project", str(project), "workspace", "show", "--json"])
    assert result.exit_code == 7, result.output


def test_missing_extracted_text_returns_error_envelope(tmp_path):
    from career_agent.config import initialize_workspace
    from career_agent.services.privacy import PRIVACY_POLICY_VERSION, PrivacyService
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    service.apply_import(
        service.preview_import([PROJECT / "tests/fixtures/imports/consistent.txt"]).run_id
    )
    source = service.load_state().imported_sources[0]
    (root / source.extracted_text_path).unlink()
    PrivacyService(root).acknowledge(PRIVACY_POLICY_VERSION, "test")
    result = runner.invoke(
        app, ["--workspace", str(root), "import", "inspect", source.source_id, "--json"]
    )
    assert result.exit_code == 5, result.output
    assert not json.loads(result.output)["ok"]


def test_rejected_proposal_recovers_interrupted_commit(tmp_path, monkeypatch):
    import pytest

    from career_agent.config import initialize_workspace
    from career_agent.services.profile import ProfileService

    root = tmp_path / "workspace"
    initialize_workspace(root)
    service = ProfileService(root)
    service.apply_import(
        service.preview_import([PROJECT / "tests/fixtures/imports/consistent.txt"]).run_id
    )
    fact_id = service.pending_proposals()[0].fact_id
    real_commit = service.journal.commit

    def interrupted(*args, **kwargs):
        raise OSError("simulated interrupted commit")

    monkeypatch.setattr(service.journal, "commit", interrupted)
    with pytest.raises(OSError):
        service.reject_fact(fact_id, "Not relevant")
    monkeypatch.setattr(service.journal, "commit", real_commit)
    service.reject_fact(fact_id, "Not relevant")
    assert service.journal.replay(f"profile-reject:{fact_id}") is not None


def test_installation_ready_does_not_imply_initialized_workspace(tmp_path):
    from career_agent.services.capabilities import CapabilityService
    from tests.contract.test_runtime_conformance import _install_link_manifest

    root = tmp_path / "workspace"
    environment = _install_link_manifest(root, "codex")
    report = CapabilityService(root, PROJECT).report(environment=environment)
    assert report.installation_ready
    assert not report.core_ready


def test_tracked_internal_workspace_blocks_initialization(tmp_path, monkeypatch):
    import subprocess

    project = tmp_path / "project"
    (project / ".agents/skills").mkdir(parents=True)
    (project / "pyproject.toml").write_text('[project]\nname = "career-agent"\n')
    (project / "workspace").mkdir()
    (project / "workspace/private.txt").write_text("private")
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "add", "workspace/private.txt"], check=True)
    monkeypatch.delenv("CAREER_WORKSPACE", raising=False)
    monkeypatch.setattr("career_agent.config._configured_workspace", lambda: None)
    result = runner.invoke(app, ["--project", str(project), "init", "--json"])
    assert result.exit_code == 7, result.output
    assert not (project / "workspace/workspace.json").exists()


def test_moved_legacy_migration_resumes_without_rewriting_history(tmp_path, monkeypatch):
    import pytest

    from career_agent.config import initialize_workspace
    from career_agent.errors import CareerError
    from career_agent.services import layout_migration
    from career_agent.services.profile import ProfileService

    old_root = tmp_path / "old workspace"
    initialize_workspace(old_root)
    profile = ProfileService(old_root)
    profile.apply_import(
        profile.preview_import([PROJECT / "tests/fixtures/imports/consistent.txt"]).run_id
    )
    paths = [old_root / "profile/profile.json", *old_root.glob("runs/RUN-*/import-result.json")]
    for path in paths:
        record = json.loads(path.read_text())
        record["schema_version"] = 1
        record.pop("rejected_proposals", None)
        for source in record["imported_sources"]:
            for key in ("stored_path", "extracted_text_path"):
                source[key] = str(old_root / source[key])
        path.write_text(json.dumps(record))
    marker = old_root / "workspace.json"
    identity = json.loads(marker.read_text())
    identity["schema_version"] = 1
    marker.write_text(json.dumps(identity))
    original_profile = (old_root / "profile/profile.json").read_bytes()
    history = (old_root / "journals/operations.ndjson").read_bytes()
    moved = tmp_path / "new workspace"
    old_root.rename(moved)
    migration = layout_migration.LayoutMigrationService(moved)
    with pytest.raises(CareerError):
        migration.plan()
    plan = migration.plan(old_root)
    write = layout_migration.atomic_write_bytes

    def interrupt_at_marker(path, data):
        if path == moved / "workspace.json":
            raise OSError("simulated interruption before final marker")
        return write(path, data)

    monkeypatch.setattr(layout_migration, "atomic_write_bytes", interrupt_at_marker)
    with pytest.raises(OSError):
        migration.apply(plan["plan_digest"])
    assert json.loads((moved / "workspace.json").read_text())["schema_version"] == 1
    assert json.loads((moved / "profile/profile.json").read_text())["schema_version"] == 2
    monkeypatch.setattr(layout_migration, "atomic_write_bytes", write)
    result = migration.apply(plan["plan_digest"])
    assert (
        json.loads((moved / "workspace.json").read_text())["workspace_id"]
        == identity["workspace_id"]
    )
    assert (moved / "journals/operations.ndjson").read_bytes() == history
    assert (
        moved / result["backup_relative_path"] / "profile/profile.json"
    ).read_bytes() == original_profile
    assert migration.apply(plan["plan_digest"]) == result
