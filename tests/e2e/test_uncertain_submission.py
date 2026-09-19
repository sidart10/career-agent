from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.models.application import ApplicationStage
from career_agent.models.submission import SubmissionStatus
from career_agent.services.applications import ApplicationService
from career_agent.services.submissions import ObservedEvidence, SubmissionService

from .fake_portal.app import FakeEmployerPortal
from .fake_portal.scenarios import PortalScenario
from .journey import NOW, begin_prepared_journey, portal_payload, prepare_journey

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "candidate"


def test_network_loss_after_acceptance_stays_uncertain_without_automatic_retry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    prepared = prepare_journey(root, FIXTURES)
    attempt = begin_prepared_journey(prepared)
    portal = FakeEmployerPortal(PortalScenario.NETWORK_FAIL_AFTER_SUBMIT)

    with pytest.raises(RuntimeError, match="connection lost after acceptance"):
        TestClient(portal.app).post(
            "/apply",
            json=portal_payload(prepared),
            headers={
                "x-test-account": "synthetic-candidate",
                "x-test-attestation": "local-release-gate",
            },
        )
    uncertain = SubmissionService(root).observe(
        prepared.application_id,
        prepared.submission_id,
        ObservedEvidence(
            claim_id="network-loss-after-submit",
            source_reference="fake-portal:attempt-0001",
            observed_at=NOW,
            confidence=0.5,
            limitations=("connection ended before confirmation was received",),
            result="uncertain",
        ),
    )

    replayed = begin_prepared_journey(prepared)
    application = ApplicationService(root).load(prepared.application_id)
    assert replayed.submission_id == attempt.submission_id
    assert uncertain.status is SubmissionStatus.UNCERTAIN
    assert application.stage is ApplicationStage.APPLYING
    assert application.submission_status is SubmissionStatus.UNCERTAIN
    assert len(application.attempts) == 1
    assert portal.submission_count == 1
    assert portal.receipt("attempt-0001").receipt_id == "RCP-attempt-0001"
