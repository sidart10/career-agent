from __future__ import annotations

from pathlib import Path

import pytest

from career_agent.models.submission import SubmissionStatus
from career_agent.services.applications import ApplicationService
from career_agent.services.submissions import SubmissionService

from .journey import NOW, prepare_journey

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "candidate"


@pytest.mark.parametrize("boundary", ["attempt-commit", "approval-consumption-commit"])
def test_restart_at_submission_boundaries_preserves_one_identity_per_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = tmp_path / "workspace"
    prepared = prepare_journey(root, FIXTURES)
    service = SubmissionService(root)
    interrupted = False
    journal = (
        service.repository.journal if boundary == "attempt-commit" else service.approvals.journal
    )
    real_commit = journal.commit

    def interrupt_once(run_id: str, result: object) -> None:
        nonlocal interrupted
        is_target = boundary == "attempt-commit" or (
            isinstance(result, dict) and "consumption_checksum" in result
        )
        if not interrupted and is_target:
            interrupted = True
            raise OSError(f"synthetic crash at {boundary}")
        real_commit(run_id, result)  # type: ignore[arg-type]

    monkeypatch.setattr(journal, "commit", interrupt_once)
    with pytest.raises(OSError, match=boundary):
        service.begin(
            prepared.application_id,
            prepared.submission_id,
            prepared.approval_id,
            observed_payload_digest=prepared.payload_digest,
            browser_state_verified=True,
            browser_state_reference="fake-portal#final-review",
            now=NOW,
        )

    recovered = service.begin(
        prepared.application_id,
        prepared.submission_id,
        prepared.approval_id,
        observed_payload_digest=prepared.payload_digest,
        browser_state_verified=True,
        browser_state_reference="fake-portal#final-review",
        now=NOW,
    )
    application = ApplicationService(root).load(prepared.application_id)

    assert recovered.status is SubmissionStatus.IN_PROGRESS
    assert len(application.attempts) == 1
    assert len(list((root / "applications").glob("APP-*"))) == 1
    assert (
        len(list((root / "applications" / prepared.application_id / "releases").glob("REL-*"))) == 1
    )
    approval_files = list(
        (
            root
            / "applications"
            / prepared.application_id
            / "submissions"
            / prepared.submission_id
            / "approvals"
        ).glob("APR-*.json")
    )
    assert [path.name for path in approval_files if ".consumed." not in path.name] == [
        "APR-0001.json"
    ]
