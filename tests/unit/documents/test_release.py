from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
import pytest

from career_agent.documents.pdf_validation import ValidationRequest
from career_agent.documents.release import (
    DocumentService,
    ReleaseArtifactRequest,
    ReleaseRequest,
)
from career_agent.documents.render import RenderResult
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationStage
from career_agent.models.base import SourceReference
from career_agent.models.operation import OperationStatus
from career_agent.models.opportunity import OpportunityStatus
from career_agent.models.profile import ConfirmationState, ProfileFact
from career_agent.models.release import ArtifactType, ClaimReference
from career_agent.services.applications import ApplicationService
from career_agent.services.opportunities import OpportunityCapture, OpportunityService
from career_agent.services.profile import ProfileState
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def setup_workspace(root: Path) -> tuple[str, Path]:
    opportunity_id = (
        OpportunityService(root)
        .add(
            OpportunityCapture(
                company="Example / Labs",
                title="Senior Product Manager",
                location="Remote",
                url="https://jobs.example.test/roles/42",
                captured_at=NOW,
                posting_text="Lead product measurement.",
                posting_complete=True,
            ),
            idempotency_key="capture-42",
        )
        .opportunity_id
    )
    application = ApplicationService(root).create_from_opportunity(opportunity_id, "pursue-42")
    facts = (
        ProfileFact(
            fact_id="FACT-0001",
            key="identity.first_name",
            value="Avery",
            sources=(SourceReference(source_id="SRC-1", locator="resume.txt#name"),),
            confirmation_state=ConfirmationState.CONFIRMED,
            confirmer="user",
            confirmed_at=NOW,
        ),
        ProfileFact(
            fact_id="FACT-0002",
            key="identity.last_name",
            value="Candidate",
            sources=(SourceReference(source_id="SRC-1", locator="resume.txt#name"),),
            confirmation_state=ConfirmationState.CONFIRMED,
            confirmer="user",
            confirmed_at=NOW,
        ),
        ProfileFact(
            fact_id="FACT-0003",
            key="achievement.measurement",
            value="Led product measurement",
            sources=(SourceReference(source_id="SRC-1", locator="resume.txt#line=3"),),
            confirmation_state=ConfirmationState.CONFIRMED,
            confirmer="user",
            confirmed_at=NOW,
        ),
    )
    atomic_write_json(root / "profile" / "profile.json", ProfileState(facts=facts))
    draft = root / "applications" / application.application_id / "drafts" / "resume.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Avery Candidate | avery@example.test | 555-0100")
    page.insert_text((72, 110), "EXPERIENCE")
    page.insert_text((72, 140), "Led product measurement across several successful launches.")
    page.insert_text((72, 180), "EDUCATION")
    page.insert_text((72, 210), "Example University Bachelor of Science")
    draft.parent.mkdir(parents=True, exist_ok=True)
    document.save(draft)
    document.close()
    source = draft.with_suffix(".tex")
    source.write_text("synthetic canonical LaTeX source")
    atomic_write_json(
        draft.with_suffix(".render.json"),
        RenderResult(
            application_id=application.application_id,
            document_type="resume",
            engine="lualatex",
            source_path=source.relative_to(root).as_posix(),
            source_checksum=sha256_file(source),
            artifact_path=draft.relative_to(root).as_posix(),
            artifact_checksum=sha256_file(draft),
        ),
    )
    return application.application_id, draft


def request() -> ReleaseRequest:
    return ReleaseRequest(
        artifacts=(
            ReleaseArtifactRequest(
                artifact_type=ArtifactType.RESUME_PDF,
                draft_relative_path="drafts/resume.pdf",
                validation=ValidationRequest(
                    required_fields=("avery@example.test", "555-0100"),
                    logical_order=("EXPERIENCE", "EDUCATION"),
                    minimum_text_characters=80,
                ),
            ),
        ),
        claims=(ClaimReference(claim_id="CLAIM-0001", fact_ids=("FACT-0003",)),),
        idempotency_key="release-1",
    )


def test_release_is_application_owned_grounded_and_append_only(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, draft = setup_workspace(root)
    service = DocumentService(root)

    release = service.create_release(application_id, request())
    replayed = service.create_release(application_id, request())

    assert release.release_id == "REL-0001"
    assert replayed == release
    assert release.artifacts[0].relative_path == (
        f"applications/{application_id}/releases/REL-0001/resume.pdf"
    )
    assert release.artifacts[0].checksum == sha256_file(draft)
    assert release.validation_reports[0].passed is True
    assert service.list(application_id) == (release,)
    application = ApplicationService(root).load(application_id)
    assert application.release_ids == ("REL-0001",)
    assert application.current_release_id == "REL-0001"


def test_failed_validation_and_unconfirmed_claim_cannot_release(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, draft = setup_workspace(root)
    service = DocumentService(root)
    bad_text = request().model_copy(
        update={
            "artifacts": (
                ReleaseArtifactRequest(
                    artifact_type=ArtifactType.RESUME_PDF,
                    draft_relative_path="drafts/resume.pdf",
                    validation=ValidationRequest(required_fields=("wrong@example.test",)),
                ),
            ),
            "idempotency_key": "bad-validation",
        }
    )

    with pytest.raises(CareerError) as validation_error:
        service.create_release(application_id, bad_text)
    draft.write_bytes(draft.read_bytes())
    unsupported = request().model_copy(
        update={
            "claims": (ClaimReference(claim_id="CLAIM-0002", fact_ids=("FACT-9999",)),),
            "idempotency_key": "bad-claim",
        }
    )
    with pytest.raises(CareerError) as claim_error:
        service.create_release(application_id, unsupported)

    assert validation_error.value.code is ErrorCode.INVALID_INPUT
    assert claim_error.value.code is ErrorCode.INVALID_INPUT
    assert not (root / "applications" / application_id / "releases").exists()


def test_pdf_without_canonical_render_provenance_cannot_release(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, draft = setup_workspace(root)
    draft.with_suffix(".render.json").unlink()

    with pytest.raises(CareerError) as error:
        DocumentService(root).create_release(application_id, request())

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_optional_docx_release_requires_an_ooxml_document(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    draft = root / "applications" / application_id / "drafts" / "resume.docx"
    with zipfile.ZipFile(draft, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    service = DocumentService(root)
    docx_request = ReleaseRequest(
        artifacts=(
            ReleaseArtifactRequest(
                artifact_type=ArtifactType.RESUME_DOCX,
                draft_relative_path="drafts/resume.docx",
            ),
        ),
        claims=(ClaimReference(claim_id="CLAIM-0001", fact_ids=("FACT-0003",)),),
        idempotency_key="docx-release",
    )

    release = service.create_release(application_id, docx_request)

    assert release.artifacts[0].relative_path.endswith("/resume.docx")
    assert release.validation_reports[0].passed is True


def test_upload_copy_is_sanitized_traceable_and_not_employer_receipt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    service = DocumentService(root)
    release = service.create_release(application_id, request())

    upload = service.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )

    assert upload.filename.startswith("Avery_Candidate_Example_Labs_Senior_Product_Manager_Resume_")
    assert upload.filename.endswith(".pdf")
    assert upload.source_checksum == release.artifacts[0].checksum
    assert upload.employer_receipt_confirmed is False
    assert upload.valid is True
    assert (root / upload.relative_path).read_bytes() == (
        root / release.artifacts[0].relative_path
    ).read_bytes()


def test_tampered_release_is_quarantined_and_invalidates_upload_and_readiness(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    applications = ApplicationService(root)
    applications.transition(application_id, ApplicationStage.READY_FOR_REVIEW, "documents ready")
    service = DocumentService(root)
    release = service.create_release(application_id, request())
    upload = service.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )
    artifact = root / release.artifacts[0].relative_path
    artifact.write_bytes(artifact.read_bytes() + b"tamper")

    with pytest.raises(CareerError) as error:
        service.verify_release(application_id, release.release_id)

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
    assert not artifact.exists()
    assert list((root / "applications" / application_id / "quarantine").glob("*resume.pdf"))
    invalidated_upload = json.loads((root / upload.record_path).read_text())
    assert invalidated_upload["valid"] is False
    application = applications.load(application_id)
    assert application.stage is ApplicationStage.PREPARING
    assert application.approval_invalidated_at is not None
    assert (
        OpportunityService(root).get(application.opportunity_id).status is OpportunityStatus.PURSUED
    )


def test_listing_releases_verifies_artifact_bytes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    service = DocumentService(root)
    release = service.create_release(application_id, request())
    artifact = root / release.artifacts[0].relative_path
    artifact.write_bytes(artifact.read_bytes() + b"tamper")

    with pytest.raises(CareerError) as error:
        service.list(application_id)

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
    assert not artifact.exists()


def test_tampered_validation_report_invalidates_derived_upload(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    applications = ApplicationService(root)
    applications.transition(application_id, ApplicationStage.READY_FOR_REVIEW, "documents ready")
    service = DocumentService(root)
    release = service.create_release(application_id, request())
    upload = service.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )
    report = root / release.validation_reports[0].report_path
    report.write_text("{}")

    with pytest.raises(CareerError) as error:
        service.verify_release(application_id, release.release_id)

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
    assert not report.exists()
    assert json.loads((root / upload.record_path).read_text())["valid"] is False
    assert applications.load(application_id).stage is ApplicationStage.PREPARING


def test_release_manifest_tampering_is_detected_by_journal_seal(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    service = DocumentService(root)
    release = service.create_release(application_id, request())
    manifest_path = (
        root / "applications" / application_id / "releases" / "REL-0001" / "release.json"
    )
    payload = json.loads(manifest_path.read_text())
    payload["request_digest"] = "f" * 64
    manifest_path.write_text(json.dumps(payload))

    with pytest.raises(CareerError) as error:
        service.verify_release(application_id, release.release_id)

    assert error.value.code is ErrorCode.INTEGRITY_ERROR


def test_unreadable_release_manifest_is_quarantined(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    service = DocumentService(root)
    release = service.create_release(application_id, request())
    manifest_path = (
        root / "applications" / application_id / "releases" / release.release_id / "release.json"
    )
    manifest_path.write_text("{")

    with pytest.raises(CareerError) as error:
        service.verify_release(application_id, release.release_id)

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
    assert not manifest_path.exists()
    assert list((root / "applications" / application_id / "quarantine").glob("*release.json"))


def test_release_repairs_journal_after_manifest_and_application_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    service = DocumentService(root)
    real_commit = service.journal.commit
    interrupted = False

    def interrupt_commit(run_id: str, result: object) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise OSError("simulated release journal interruption")
        real_commit(run_id, result)  # type: ignore[arg-type]

    monkeypatch.setattr(service.journal, "commit", interrupt_commit)
    with pytest.raises(OSError, match="release journal interruption"):
        service.create_release(application_id, request())
    run_id = service.journal.operation_for_key(
        f"release-create:{application_id}:{hashlib.sha256(b'release-1').hexdigest()}"
    ).run_id

    recovered = service.create_release(application_id, request())

    assert recovered.release_id == "REL-0001"
    assert service.journal.recover(run_id).status is OperationStatus.COMMITTED


def test_interrupted_release_cannot_rebind_idempotency_key_to_changed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    application_id, draft = setup_workspace(root)
    service = DocumentService(root)

    def interrupt_manifest(path: Path, value: object) -> None:
        if path.name == "release.json":
            raise OSError("simulated manifest interruption")
        atomic_write_json(path, value)

    monkeypatch.setattr(
        "career_agent.documents.release.atomic_write_json",
        interrupt_manifest,
    )
    with pytest.raises(OSError, match="manifest interruption"):
        service.create_release(application_id, request())

    monkeypatch.undo()
    updated = pymupdf.open(draft)
    updated[0].insert_text((72, 240), "Additional confirmed detail")
    replacement = draft.with_suffix(".replacement.pdf")
    updated.save(replacement)
    updated.close()
    replacement.replace(draft)
    render_record_path = draft.with_suffix(".render.json")
    render_record = RenderResult.model_validate_json(render_record_path.read_text())
    atomic_write_json(
        render_record_path,
        render_record.model_copy(update={"artifact_checksum": sha256_file(draft)}),
    )

    with pytest.raises(CareerError) as error:
        service.create_release(application_id, request())

    assert error.value.code is ErrorCode.CONFLICT
