from __future__ import annotations

from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.services.reset import ResetScope, ResetService
from career_agent.storage.journal import OperationJournal


def test_generated_drafts_reset_cannot_piggyback_on_protected_or_remote_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    draft = root / "applications" / "APP-2026-0001" / "drafts" / "resume.tex"
    release = root / "applications" / "APP-2026-0001" / "releases" / "REL-0001" / "resume.pdf"
    evidence = root / "applications" / "APP-2026-0001" / "submissions" / "SUB-0001" / "payload.json"
    imported = root / "resources" / "imports" / "SRC-0001" / "original.pdf"
    for path in (draft, release, evidence, imported):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    (root / "pipeline.md").write_text("generated")

    service = ResetService(root)
    plan = service.plan(frozenset({ResetScope.GENERATED_DRAFTS}))

    assert plan.scopes == (ResetScope.GENERATED_DRAFTS,)
    assert {item.relative_path for item in plan.items} == {
        "applications/APP-2026-0001/drafts",
        "pipeline.md",
    }
    assert not any(
        protected in item.relative_path
        for item in plan.items
        for protected in ("releases", "submissions", "resources/imports")
    )
    with pytest.raises(CareerError) as changed:
        service.apply("f" * 64)
    assert changed.value.code is ErrorCode.CONFLICT
    with pytest.raises(CareerError) as widened:
        service.plan(
            frozenset(
                {
                    ResetScope.GENERATED_DRAFTS,
                    ResetScope.SUBMISSION_EVIDENCE,
                }
            )
        )
    assert widened.value.code is ErrorCode.INVALID_INPUT
    with pytest.raises(CareerError) as remote:
        service.plan(frozenset({ResetScope.REMOTE_DATA}))
    assert remote.value.code is ErrorCode.APPROVAL_REQUIRED

    result = service.apply(plan.plan_digest)

    assert set(result.deleted_paths) == {
        "applications/APP-2026-0001/drafts",
        "pipeline.md",
    }
    assert not draft.exists()
    assert release.exists()
    assert evidence.exists()
    assert imported.exists()


def test_reset_aborts_when_previewed_scope_changes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    drafts = root / "applications" / "APP-2026-0001" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "resume.tex").write_text("first")
    service = ResetService(root)
    plan = service.plan(frozenset({ResetScope.GENERATED_DRAFTS}))
    (drafts / "cover-letter.tex").write_text("added after preview")

    with pytest.raises(CareerError) as changed:
        service.apply(plan.plan_digest)

    assert changed.value.code is ErrorCode.CONFLICT
    assert drafts.exists()


@pytest.mark.parametrize(
    ("scope", "relative_path"),
    [
        (ResetScope.IMPORTED_SOURCES, "resources/imports"),
        (ResetScope.RELEASES, "applications/APP-2026-0001/releases"),
        (
            ResetScope.SUBMISSION_EVIDENCE,
            "applications/APP-2026-0001/submissions",
        ),
    ],
)
def test_each_protected_history_class_requires_its_own_plan(
    tmp_path: Path,
    scope: ResetScope,
    relative_path: str,
) -> None:
    root = tmp_path / "workspace"
    protected = root / relative_path / "record.json"
    protected.parent.mkdir(parents=True)
    protected.write_text("protected")
    service = ResetService(root)

    plan = service.plan(frozenset({scope}))

    assert plan.scopes == (scope,)
    assert tuple(item.relative_path for item in plan.items) == (relative_path,)
    with pytest.raises(CareerError) as combined:
        service.plan(frozenset({scope, ResetScope.GENERATED_DRAFTS}))
    assert combined.value.code is ErrorCode.INVALID_INPUT


def test_all_personal_data_reset_removes_content_and_its_journal(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    profile = root / "profile" / "profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"schema_version":1}')
    journal = OperationJournal(root)
    journal.begin(
        OperationRecord(
            run_id="RUN-9000",
            operation="synthetic.personal-data",
            idempotency_key="synthetic-personal-data",
            status=OperationStatus.STARTED,
        )
    )
    journal.commit("RUN-9000", {"result_references": []})
    service = ResetService(root)
    plan = service.plan(frozenset({ResetScope.ALL_PERSONAL_WORKSPACE_DATA}))

    result = service.apply(plan.plan_digest)

    assert "profile" in result.deleted_paths
    assert "journals" in result.deleted_paths
    assert not profile.exists()
    assert not (root / "journals").exists()
    assert (root / "maintenance" / "reset-results" / f"{plan.plan_digest}.json").is_file()
