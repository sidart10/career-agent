from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from career_agent.models.answer import RetentionClass
from career_agent.models.application import ApplicationStage
from career_agent.models.release import ArtifactType
from career_agent.services.applications import ApplicationService
from career_agent.services.payloads import (
    AttachmentCategory,
    AttachmentRequest,
    CanonicalSubmissionPayload,
    PayloadArtifact,
    PayloadAttachment,
    PayloadAttestation,
    PayloadField,
    PayloadPosting,
    PayloadService,
    PrepareSubmissionRequest,
)
from career_agent.storage.checksums import sha256_file

from .documents.test_release import request as release_request
from .documents.test_release import setup_workspace

NOW = datetime(2026, 9, 18, 20, 0, tzinfo=UTC)
CHECKSUM_A = "a" * 64
CHECKSUM_B = "b" * 64


def payload() -> CanonicalSubmissionPayload:
    return CanonicalSubmissionPayload(
        created_at=NOW,
        updated_at=NOW,
        payload_version=1,
        digest_algorithm="sha256-v1",
        application_id="APP-2026-0001",
        submission_id="SUB-0001",
        posting=PayloadPosting(
            snapshot_id="PST-0001",
            checksum=CHECKSUM_A,
            freshness="current",
        ),
        release_id="REL-0001",
        artifacts=(
            PayloadArtifact(
                artifact_type="resume_pdf",
                filename="Avery_Candidate_Resume_abcd1234.pdf",
                relative_path=(
                    "applications/APP-2026-0001/uploads/Avery_Candidate_Resume_abcd1234.pdf"
                ),
                checksum=CHECKSUM_A,
                source_release_checksum=CHECKSUM_A,
            ),
            PayloadArtifact(
                artifact_type="cover_letter_pdf",
                filename="Avery_Candidate_Cover_Letter_dcba4321.pdf",
                relative_path=(
                    "applications/APP-2026-0001/uploads/Avery_Candidate_Cover_Letter_dcba4321.pdf"
                ),
                checksum=CHECKSUM_B,
                source_release_checksum=CHECKSUM_B,
            ),
        ),
        attachments=(
            PayloadAttachment(
                attachment_id="portfolio-main",
                category=AttachmentCategory.PORTFOLIO,
                filename="Portfolio_abcd1234.pdf",
                relative_path=(
                    "applications/APP-2026-0001/submissions/SUB-0001/attachments/"
                    "Portfolio_abcd1234.pdf"
                ),
                checksum=CHECKSUM_A,
                source_relative_path="resources/portfolio.pdf",
            ),
        ),
        fields=(
            PayloadField(
                field_id="contact.email",
                value="avery@example.test",
                retention_class=RetentionClass.ORDINARY,
            ),
            PayloadField(
                field_id="authorization.sponsorship_future",
                value=False,
                retention_class=RetentionClass.HIGH_RISK,
                requires_final_review=True,
            ),
        ),
        attestations=(
            PayloadAttestation(
                attestation_id="terms-of-service",
                label="Portal terms accepted",
                completed_by_human=True,
                source_reference="browser-session-1",
            ),
        ),
        anomalies=("salary field normalized by portal",),
        evidence_limitations=("portal does not echo uploaded bytes",),
        destination="https://jobs.example.test/apply/42",
        irreversible_action="Submit application",
        request_digest=CHECKSUM_A,
        idempotency_digest=CHECKSUM_B,
    )


def test_equivalent_payload_order_and_audit_timestamps_serialize_identically() -> None:
    first = payload()
    equivalent = first.model_copy(
        update={
            "updated_at": NOW + timedelta(minutes=5),
            "artifacts": tuple(reversed(first.artifacts)),
            "fields": tuple(reversed(first.fields)),
        }
    )

    assert PayloadService.serialize(first) == PayloadService.serialize(equivalent)
    assert PayloadService.digest(first) == PayloadService.digest(equivalent)


@pytest.mark.parametrize(
    "mutation",
    [
        {"posting": payload().posting.model_copy(update={"checksum": CHECKSUM_B})},
        {
            "artifacts": (
                payload().artifacts[0].model_copy(update={"checksum": CHECKSUM_B}),
                payload().artifacts[1],
            )
        },
        {"attachments": (payload().attachments[0].model_copy(update={"checksum": CHECKSUM_B}),)},
        {
            "fields": (
                payload().fields[0].model_copy(update={"value": "changed@example.test"}),
                payload().fields[1],
            )
        },
        {"destination": "https://jobs.example.test/apply/43"},
        {
            "attestations": (
                payload()
                .attestations[0]
                .model_copy(update={"source_reference": "browser-session-2"}),
            )
        },
        {"anomalies": ("new conditional question",)},
        {"evidence_limitations": ("employer echoed no fields",)},
        {"irreversible_action": "Submit and certify application"},
    ],
)
def test_every_material_mutation_changes_the_digest(mutation: dict[str, object]) -> None:
    original = payload()

    assert PayloadService.digest(original.model_copy(update=mutation)) != PayloadService.digest(
        original
    )


def test_prepare_builds_payload_from_verified_application_state(tmp_path) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    from career_agent.documents.release import DocumentService

    documents = DocumentService(root)
    release = documents.create_release(application_id, release_request())
    upload = documents.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )
    ApplicationService(root).transition(
        application_id,
        ApplicationStage.READY_FOR_REVIEW,
        "final review assembled",
    )
    command = PrepareSubmissionRequest(
        release_id=release.release_id,
        upload_record_paths=(upload.record_path,),
        fields=payload().fields,
        attestations=payload().attestations,
        anomalies=payload().anomalies,
        evidence_limitations=payload().evidence_limitations,
        destination="https://jobs.example.test/apply/42",
        irreversible_action="Submit application",
        idempotency_key="prepare-42",
    )
    service = PayloadService(root)

    prepared = service.prepare(application_id, command)
    replayed = service.prepare(application_id, command)

    assert prepared == replayed
    assert prepared.submission_id == "SUB-0001"
    assert prepared.release_id == release.release_id
    assert prepared.posting.snapshot_id == "PST-0001"
    assert prepared.artifacts[0].filename == upload.filename
    assert prepared.artifacts[0].checksum == upload.source_checksum
    assert service.load(application_id, prepared.submission_id) == prepared


def test_prepare_snapshots_typed_attachment_with_checksum_and_permission(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    application_id, _ = setup_workspace(root)
    from career_agent.documents.release import DocumentService

    documents = DocumentService(root)
    release = documents.create_release(application_id, release_request())
    upload = documents.prepare_upload_copy(
        application_id,
        release.release_id,
        ArtifactType.RESUME_PDF,
    )
    ApplicationService(root).transition(
        application_id,
        ApplicationStage.READY_FOR_REVIEW,
        "final review assembled",
    )
    reference = root / "resources" / "references" / "avery-reference.pdf"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"synthetic reference letter")

    prepared = PayloadService(root).prepare(
        application_id,
        PrepareSubmissionRequest(
            release_id=release.release_id,
            upload_record_paths=(upload.record_path,),
            attachments=(
                AttachmentRequest(
                    attachment_id="reference-1",
                    category=AttachmentCategory.REFERENCE,
                    source_relative_path=reference.relative_to(root).as_posix(),
                    upload_filename="Avery Reference.pdf",
                    checksum=sha256_file(reference),
                    permission_reference="permission-confirmed-2026-09-18",
                ),
            ),
            destination="https://jobs.example.test/apply/42",
            irreversible_action="Submit application",
            idempotency_key="prepare-with-reference",
        ),
    )

    attachment = prepared.attachments[0]
    assert attachment.filename.startswith("Avery_Reference_")
    assert attachment.permission_reference == "permission-confirmed-2026-09-18"
    assert (root / attachment.relative_path).read_bytes() == reference.read_bytes()
