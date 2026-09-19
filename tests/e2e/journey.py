from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from career_agent.approval.authority import ApprovalAttestation, ApprovalSummary
from career_agent.cli import app
from career_agent.documents.pdf_validation import ValidationRequest
from career_agent.documents.release import (
    DocumentService,
    ReleaseArtifactRequest,
    ReleaseRequest,
)
from career_agent.documents.render import RenderResult
from career_agent.models.answer import AnswerRecord, RetentionClass, ReusePolicy
from career_agent.models.application import ApplicationManifest, ApplicationStage
from career_agent.models.release import ArtifactType, ClaimReference, DocumentRelease
from career_agent.models.submission import SubmissionAttempt
from career_agent.services.answers import AnswerService, SetAnswerCommand
from career_agent.services.applications import ApplicationService
from career_agent.services.approvals import ApprovalService
from career_agent.services.evaluation import (
    ConstraintFinding,
    EvaluationDraft,
    EvaluationMode,
    EvidenceReference,
    EvidenceSource,
    FitEvaluation,
    PreferenceFinding,
)
from career_agent.services.payloads import (
    CanonicalSubmissionPayload,
    PayloadField,
    PayloadService,
    PrepareSubmissionRequest,
)
from career_agent.services.submissions import (
    BeginSubmissionRequest,
    EmployerConfirmation,
)
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file

from .fake_portal.app import FakeEmployerPortal

NOW = datetime(2026, 9, 18, 21, 0, tzinfo=UTC)
RUNNER = CliRunner()


def _run_cli(root: Path, *arguments: str) -> object:
    result = RUNNER.invoke(
        app,
        [*arguments, "--json"],
        env={"CAREER_WORKSPACE": str(root)},
    )
    assert result.exit_code == 0, result.stdout
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    return envelope["data"]


def _request_file(root: Path, name: str, value: object) -> Path:
    request_root = root.parent / "synthetic-requests"
    request_root.mkdir(parents=True, exist_ok=True)
    path = request_root / name
    model_dump_json = getattr(value, "model_dump_json", None)
    payload = model_dump_json() if model_dump_json is not None else json.dumps(value)
    path.write_text(payload, encoding="utf-8")
    return path


class SyntheticApprovalAuthority:
    def request(
        self,
        summary: ApprovalSummary,
        payload_digest: str,
        nonce: str,
    ) -> ApprovalAttestation:
        return ApprovalAttestation(
            payload_digest=payload_digest,
            nonce=nonce,
            approving_actor="synthetic-candidate",
            runtime_session="local-release-gate",
            authority="synthetic-test-authority",
            approved_at=datetime.now(UTC),
            provenance_reference=f"test-attestation:{summary.submission_id}",
        )


@dataclass(frozen=True)
class PreparedJourney:
    root: Path
    application_id: str
    submission_id: str
    approval_id: str
    payload_digest: str
    confirmed_fact_count: int
    active_opportunity_count: int
    evaluation: FitEvaluation
    release_id: str
    answer_classes: frozenset[str]


@dataclass(frozen=True)
class JourneyResult:
    confirmed_fact_count: int
    active_opportunity_count: int
    evaluation: FitEvaluation
    release_id: str
    answer_classes: frozenset[str]
    application: ApplicationManifest
    attempt: SubmissionAttempt
    pipeline_first: str
    pipeline_second: str


def _import_profile(root: Path, fixtures: Path) -> tuple[int, str]:
    preview = _run_cli(root, "import", "preview", str(fixtures / "resume.txt"))
    assert isinstance(preview, dict)
    result = _run_cli(root, "import", "apply", str(preview["run_id"]))
    assert isinstance(result, dict)
    fact_ids: dict[str, str] = {}
    proposals = result["proposed_facts"]
    assert isinstance(proposals, list)
    for proposal in proposals:
        assert isinstance(proposal, dict)
        arguments = [
            "profile",
            "confirm",
            str(proposal["fact_id"]),
            "--value",
            json.dumps(proposal["value"]),
        ]
        sources = proposal["sources"]
        assert isinstance(sources, list)
        for source in sources:
            arguments.extend(("--source-id", str(source["source_id"])))
        fact = _run_cli(root, *arguments)
        assert isinstance(fact, dict)
        fact_ids[str(fact["key"])] = str(fact["fact_id"])
    return len(fact_ids), fact_ids["employment.current_title"]


def _opportunities_and_evaluation(
    root: Path, fixtures: Path, profile_fact_id: str
) -> tuple[str, int, FitEvaluation]:
    posting_a = (fixtures / "posting-a.txt").read_text().strip()
    first = _run_cli(
        root,
        "opportunity",
        "add",
        "--company",
        "Synthetic Measurement Labs",
        "--title",
        "Product Manager",
        "--location",
        "Remote",
        "--url",
        "https://jobs.example.test/roles/100",
        "--posting",
        str(fixtures / "posting-a.txt"),
        "--posting-complete",
        "--requisition-id",
        "SYN-100",
        "--idempotency-key",
        "synthetic-posting-100",
    )
    assert isinstance(first, dict)
    _run_cli(
        root,
        "opportunity",
        "add",
        "--company",
        "Synthetic Measurement Labs",
        "--title",
        "Product Manager",
        "--location",
        "Remote",
        "--url",
        "https://jobs.example.test/roles/101",
        "--posting",
        str(fixtures / "posting-b.txt"),
        "--posting-complete",
        "--requisition-id",
        "SYN-101",
        "--idempotency-key",
        "synthetic-posting-101",
    )
    opposing = "Travel up to 20% required."
    start = posting_a.index(opposing)
    draft = EvaluationDraft(
        mode=EvaluationMode.AUTHORITATIVE,
        hard_constraints=(ConstraintFinding(name="remote", satisfied=True),),
        weighted_preferences=(
            PreferenceFinding(
                name="product-scope",
                weight=Decimal("1"),
                rating=Decimal("1"),
            ),
        ),
        supporting_evidence=(
            EvidenceReference(
                source=EvidenceSource.PROFILE,
                reference_id=profile_fact_id,
                excerpt="Product Manager",
            ),
        ),
        opposing_evidence=(
            EvidenceReference(
                source=EvidenceSource.POSTING,
                reference_id=str(first["opportunity_id"]),
                excerpt=opposing,
                start=start,
                end=start + len(opposing),
            ),
        ),
    )
    evaluation_data = _run_cli(
        root,
        "opportunity",
        "evaluate",
        str(first["opportunity_id"]),
        "--input",
        str(_request_file(root, "evaluation.json", draft)),
        "--idempotency-key",
        "synthetic-authoritative-evaluation",
    )
    active = _run_cli(root, "opportunity", "list")
    assert isinstance(evaluation_data, dict)
    assert isinstance(active, list)
    return (
        str(first["opportunity_id"]),
        len(active),
        FitEvaluation.model_validate(evaluation_data),
    )


def _release_document(
    root: Path, fixtures: Path, application_id: str, profile_fact_id: str
) -> tuple[str, str]:
    draft = root / "applications" / application_id / "drafts" / "resume.pdf"
    draft.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Taylor Example | candidate@example.test | +1 555 010 2000")
    page.insert_text((72, 110), "EXPERIENCE")
    page.insert_text((72, 140), "Led measurement products with engineering and data teams.")
    page.insert_text((72, 180), "EDUCATION")
    page.insert_text((72, 210), "Example Institute Bachelor of Science")
    document.save(draft)
    document.close()
    source = draft.with_suffix(".tex")
    source.write_text((fixtures / "resume.tex").read_text())
    atomic_write_json(
        draft.with_suffix(".render.json"),
        RenderResult(
            application_id=application_id,
            document_type="resume",
            engine="lualatex",
            source_path=source.relative_to(root).as_posix(),
            source_checksum=sha256_file(source),
            artifact_path=draft.relative_to(root).as_posix(),
            artifact_checksum=sha256_file(draft),
        ),
    )
    documents = DocumentService(root)
    request = ReleaseRequest(
        artifacts=(
            ReleaseArtifactRequest(
                artifact_type=ArtifactType.RESUME_PDF,
                draft_relative_path="drafts/resume.pdf",
                validation=ValidationRequest(
                    required_fields=("candidate@example.test", "+1 555 010 2000"),
                    logical_order=("EXPERIENCE", "EDUCATION"),
                    minimum_text_characters=80,
                ),
            ),
        ),
        claims=(
            ClaimReference(
                claim_id="CLAIM-0001",
                fact_ids=(profile_fact_id,),
            ),
        ),
        idempotency_key="synthetic-release",
    )
    release_data = _run_cli(
        root,
        "release",
        "create",
        application_id,
        "--input",
        str(_request_file(root, "release.json", request)),
    )
    assert isinstance(release_data, dict)
    release = DocumentRelease.model_validate(release_data)
    upload = documents.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )
    return release.release_id, upload.record_path


def _answers(root: Path, application_id: str) -> tuple[PayloadField, ...]:
    email_data = _run_cli(
        root,
        "answer",
        "set",
        "--input",
        str(
            _request_file(
                root,
                "email-answer.json",
                SetAnswerCommand(
                    question_id="contact.email",
                    value="candidate@example.test",
                    exact_user_response="candidate@example.test",
                    source_reference="synthetic-user:email",
                    retention_class=RetentionClass.ORDINARY,
                    reuse_policy=ReusePolicy.STABLE,
                    confirmed_at=NOW,
                    idempotency_key="synthetic-email",
                ),
            )
        ),
    )
    sponsorship_data = _run_cli(
        root,
        "answer",
        "set",
        "--input",
        str(
            _request_file(
                root,
                "sponsorship-answer.json",
                SetAnswerCommand(
                    question_id="sponsorship.future_us",
                    value=False,
                    exact_user_response=False,
                    source_reference="synthetic-user:sponsorship",
                    retention_class=RetentionClass.HIGH_RISK,
                    reuse_policy=ReusePolicy.VERIFY_PER_APPLICATION,
                    confirmed_at=NOW,
                    scope={"application_id": application_id},
                    idempotency_key="synthetic-sponsorship",
                ),
            )
        ),
    )
    assert isinstance(email_data, dict)
    assert isinstance(sponsorship_data, dict)
    email = AnswerRecord.model_validate(email_data)
    sponsorship = AnswerRecord.model_validate(sponsorship_data)
    return (
        PayloadField(
            field_id=email.question_id,
            value=email.value,
            answer_id=email.answer_id,
            retention_class=email.retention_class,
        ),
        PayloadField(
            field_id=sponsorship.question_id,
            value=sponsorship.value,
            answer_id=sponsorship.answer_id,
            retention_class=sponsorship.retention_class,
            requires_final_review=True,
        ),
    )


def prepare_journey(root: Path, fixtures: Path) -> PreparedJourney:
    _run_cli(root, "init")
    confirmed_fact_count, profile_fact_id = _import_profile(root, fixtures)
    opportunity_id, active_count, evaluation = _opportunities_and_evaluation(
        root, fixtures, profile_fact_id
    )
    application_data = _run_cli(
        root,
        "opportunity",
        "pursue",
        opportunity_id,
        "--idempotency-key",
        "synthetic-pursuit",
    )
    assert isinstance(application_data, dict)
    application = ApplicationManifest.model_validate(application_data)
    release_id, upload_record = _release_document(
        root, fixtures, application.application_id, profile_fact_id
    )
    fields = _answers(root, application.application_id)
    _run_cli(
        root,
        "application",
        "transition",
        application.application_id,
        ApplicationStage.READY_FOR_REVIEW.value,
        "--reason",
        "synthetic application assembled",
    )
    preparation = PrepareSubmissionRequest(
        release_id=release_id,
        upload_record_paths=(upload_record,),
        fields=fields,
        destination="https://jobs.example.test/apply/100",
        irreversible_action="Submit synthetic application",
        idempotency_key="synthetic-submission-payload",
    )
    payload_result = _run_cli(
        root,
        "submission",
        "prepare",
        application.application_id,
        "--input",
        str(_request_file(root, "submission.json", preparation)),
    )
    assert isinstance(payload_result, dict)
    payload_value = payload_result["payload"]
    assert isinstance(payload_value, dict)
    payload = CanonicalSubmissionPayload.model_validate(payload_value)
    approval = ApprovalService(root).approve(
        application.application_id,
        payload.submission_id,
        SyntheticApprovalAuthority(),
    )
    return PreparedJourney(
        root=root,
        application_id=application.application_id,
        submission_id=payload.submission_id,
        approval_id=approval.approval_id,
        payload_digest=PayloadService.digest(payload),
        confirmed_fact_count=confirmed_fact_count,
        active_opportunity_count=active_count,
        evaluation=evaluation,
        release_id=release_id,
        answer_classes=frozenset(
            item.retention_class.value for item in AnswerService(root).load_state().answers
        ),
    )


def begin_prepared_journey(prepared: PreparedJourney) -> SubmissionAttempt:
    request = BeginSubmissionRequest(
        approval_id=prepared.approval_id,
        observed_payload_digest=prepared.payload_digest,
        browser_state_verified=True,
        browser_state_reference="fake-portal#final-review",
    )
    result = _run_cli(
        prepared.root,
        "submission",
        "begin",
        prepared.application_id,
        prepared.submission_id,
        "--input",
        str(_request_file(prepared.root, "submission-begin.json", request)),
    )
    assert isinstance(result, dict)
    return SubmissionAttempt.model_validate(result)


def portal_payload(prepared: PreparedJourney) -> dict[str, object]:
    payload = PayloadService(prepared.root).load(prepared.application_id, prepared.submission_id)
    return {
        "idempotency_token": "attempt-0001",
        "fields": {
            field.field_id: (
                json.dumps(field.value) if not isinstance(field.value, str) else field.value
            )
            for field in payload.fields
        },
        "uploads": {artifact.filename: artifact.checksum for artifact in payload.artifacts},
    }


def execute_confirmed_journey(
    root: Path, fixtures: Path, portal: FakeEmployerPortal
) -> JourneyResult:
    prepared = prepare_journey(root, fixtures)
    begin_prepared_journey(prepared)
    response = TestClient(portal.app).post(
        "/apply",
        json=portal_payload(prepared),
        headers={
            "x-test-account": "synthetic-candidate",
            "x-test-attestation": "local-release-gate",
        },
    )
    response.raise_for_status()
    receipt = response.json()
    confirmation = EmployerConfirmation(
        claim_id="synthetic-employer-receipt",
        source_reference=f"fake-portal:{receipt['receipt_id']}",
        observed_at=NOW,
        confidence=1,
        receipt_id=receipt["receipt_id"],
        echoed_field_ids=tuple(sorted(receipt["echoed_fields"])),
        limitations=tuple(receipt["evidence_limitations"]),
    )
    attempt_data = _run_cli(
        root,
        "submission",
        "confirm",
        prepared.application_id,
        prepared.submission_id,
        "--input",
        str(_request_file(root, "submission-confirm.json", confirmation)),
    )
    assert isinstance(attempt_data, dict)
    attempt = SubmissionAttempt.model_validate(attempt_data)
    first_result = _run_cli(root, "pipeline", "build")
    assert isinstance(first_result, dict)
    first_path = root / str(first_result["path"])
    first = first_path.read_text()
    second_result = _run_cli(root, "pipeline", "build")
    assert isinstance(second_result, dict)
    second_path = root / str(second_result["path"])
    second = second_path.read_text()
    return JourneyResult(
        confirmed_fact_count=prepared.confirmed_fact_count,
        active_opportunity_count=prepared.active_opportunity_count,
        evaluation=prepared.evaluation,
        release_id=prepared.release_id,
        answer_classes=prepared.answer_classes,
        application=ApplicationService(root).load(prepared.application_id),
        attempt=attempt,
        pipeline_first=first,
        pipeline_second=second,
    )
