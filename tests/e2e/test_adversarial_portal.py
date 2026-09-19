from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationStage
from career_agent.services.applications import ApplicationService
from career_agent.services.submissions import SubmissionService

from .fake_portal.app import FakeEmployerPortal
from .fake_portal.scenarios import PortalScenario
from .journey import NOW, portal_payload, prepare_journey

HEADERS = {
    "x-test-account": "synthetic-candidate",
    "x-test-attestation": "local-release-gate",
}
PAYLOAD = {
    "idempotency_token": "attempt-0001",
    "fields": {
        "contact.email": "candidate@example.test",
        "contact.phone": "+1 (555) 010-2000",
    },
    "uploads": {"resume.pdf": "synthetic resume bytes"},
}


def test_portal_requires_synthetic_account_and_attestation() -> None:
    portal = FakeEmployerPortal(PortalScenario.HAPPY_PATH)
    client = TestClient(portal.app)

    assert client.post("/apply", json=PAYLOAD).status_code == 401
    assert (
        client.post(
            "/apply", json=PAYLOAD, headers={"x-test-account": "synthetic-candidate"}
        ).status_code
        == 403
    )
    assert portal.submission_count == 0


@pytest.mark.parametrize(
    ("scenario", "status_code"),
    [
        (PortalScenario.HAPPY_PATH, 201),
        (PortalScenario.CONDITIONAL_AFTER_APPROVAL, 409),
        (PortalScenario.NORMALIZE_VALUE, 201),
        (PortalScenario.REJECT_UPLOAD, 422),
        (PortalScenario.SESSION_EXPIRES, 401),
        (PortalScenario.DELAYED_SUBMIT, 202),
        (PortalScenario.PARTIAL_SUCCESS, 201),
        (PortalScenario.NO_CONFIRMATION, 202),
    ],
)
def test_each_adversarial_scenario_has_an_observable_contract(
    scenario: PortalScenario, status_code: int
) -> None:
    portal = FakeEmployerPortal(scenario)
    response = TestClient(portal.app).post("/apply", json=PAYLOAD, headers=HEADERS)

    assert response.status_code == status_code
    body = response.json()
    if scenario is PortalScenario.CONDITIONAL_AFTER_APPROVAL:
        assert body["detail"]["required_fields"] == ["portfolio.url"]
        assert portal.submission_count == 0
    elif scenario is PortalScenario.NORMALIZE_VALUE:
        assert body["echoed_fields"]["contact.phone"] == "+15550102000"
        assert body["anomalies"] == ["contact.phone normalized"]
    elif scenario is PortalScenario.REJECT_UPLOAD:
        assert body["detail"] == "resume.pdf rejected"
        assert portal.submission_count == 0
    elif scenario is PortalScenario.SESSION_EXPIRES:
        assert body["detail"] == "session expired"
        assert portal.submission_count == 0
    elif scenario is PortalScenario.DELAYED_SUBMIT:
        assert body == {"status": "processing", "token": "attempt-0001"}
        assert portal.submission_count == 1
    elif scenario is PortalScenario.PARTIAL_SUCCESS:
        assert body["echoed_fields"] == {"contact.email": "candidate@example.test"}
        assert body["evidence_limitations"] == ["phone and upload were not echoed"]
    elif scenario is PortalScenario.NO_CONFIRMATION:
        assert body == {"status": "accepted_without_confirmation"}
        assert portal.submission_count == 1
    else:
        assert body["receipt_id"] == "RCP-attempt-0001"
        assert body["received_file_digests"] == {
            "resume.pdf": hashlib.sha256(b"synthetic resume bytes").hexdigest()
        }


def test_duplicate_click_is_idempotent() -> None:
    portal = FakeEmployerPortal(PortalScenario.DUPLICATE_CLICK)
    client = TestClient(portal.app)

    first = client.post("/apply", json=PAYLOAD, headers=HEADERS)
    second = client.post("/apply", json=PAYLOAD, headers=HEADERS)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert portal.submission_count == 1


def test_network_failure_occurs_after_exactly_one_external_acceptance() -> None:
    portal = FakeEmployerPortal(PortalScenario.NETWORK_FAIL_AFTER_SUBMIT)

    with pytest.raises(RuntimeError, match="connection lost after acceptance"):
        TestClient(portal.app).post("/apply", json=PAYLOAD, headers=HEADERS)

    assert portal.submission_count == 1
    assert portal.receipt("attempt-0001").receipt_id == "RCP-attempt-0001"


def test_conditional_field_after_approval_invalidates_before_external_action(
    tmp_path: Path,
) -> None:
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "candidate"
    root = tmp_path / "workspace"
    prepared = prepare_journey(root, fixtures)
    portal = FakeEmployerPortal(PortalScenario.CONDITIONAL_AFTER_APPROVAL)
    response = TestClient(portal.app).post(
        "/apply",
        json=portal_payload(prepared),
        headers=HEADERS,
    )
    assert response.status_code == 409

    with pytest.raises(CareerError) as changed:
        SubmissionService(root).begin(
            prepared.application_id,
            prepared.submission_id,
            prepared.approval_id,
            observed_payload_digest="f" * 64,
            browser_state_verified=True,
            browser_state_reference="fake-portal#conditional-field",
            now=NOW,
        )

    assert changed.value.code is ErrorCode.NOT_READY
    assert ApplicationService(root).load(prepared.application_id).stage is (
        ApplicationStage.READY_FOR_REVIEW
    )
    assert portal.submission_count == 0
