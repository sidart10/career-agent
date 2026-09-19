from __future__ import annotations

from pathlib import Path

from career_agent.models.application import ApplicationStage
from career_agent.models.submission import EvidenceLevel, SubmissionStatus
from career_agent.services.reset import ResetScope, ResetService

from .fake_portal.app import FakeEmployerPortal
from .fake_portal.scenarios import PortalScenario
from .journey import execute_confirmed_journey

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "candidate"


def test_complete_synthetic_journey_ends_confirmed_with_reproducible_pipeline(
    tmp_path: Path,
) -> None:
    portal = FakeEmployerPortal(PortalScenario.HAPPY_PATH)

    result = execute_confirmed_journey(tmp_path / "workspace", FIXTURES, portal)

    assert result.confirmed_fact_count == 3
    assert result.active_opportunity_count == 2
    assert result.evaluation.mode.value == "authoritative"
    assert result.evaluation.recommendation == "pursue"
    assert result.release_id == "REL-0001"
    assert result.answer_classes == {"ordinary", "high_risk"}
    assert result.application.stage is ApplicationStage.SUBMITTED
    assert result.application.submission_status is SubmissionStatus.CONFIRMED
    assert result.attempt.status is SubmissionStatus.CONFIRMED
    assert result.attempt.evidence[-1].level is EvidenceLevel.EMPLOYER_CONFIRMED
    assert portal.submission_count == 1
    assert result.pipeline_first == result.pipeline_second
    assert result.application.application_id in result.pipeline_first
    assert "confirmed" in result.pipeline_first

    reset = ResetService(tmp_path / "workspace")
    plan = reset.plan(frozenset({ResetScope.ALL_PERSONAL_WORKSPACE_DATA}))
    deleted = reset.apply(plan.plan_digest)
    assert "applications" in deleted.deleted_paths
    assert not (tmp_path / "workspace" / "applications").exists()
