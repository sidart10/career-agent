from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.opportunity import OpportunityStatus
from career_agent.services.applications import ApplicationService
from career_agent.services.opportunities import OpportunityCapture, OpportunityService
from career_agent.storage.registry import SequenceRegistry

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def add_opportunity(root: Path, *, key: str = "capture-42") -> str:
    return (
        OpportunityService(root)
        .add(
            OpportunityCapture(
                company="Example Labs",
                title="Senior Product Manager",
                location="Remote",
                url="https://jobs.example.test/roles/42",
                captured_at=NOW,
                posting_text="Lead measurement products.",
                posting_complete=True,
                requisition_id="REQ-42",
            ),
            idempotency_key=key,
        )
        .opportunity_id
    )


def test_pursue_creates_one_application_with_owned_initial_posting(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    service = ApplicationService(root)

    application = service.create_from_opportunity(opportunity_id, "pursue-42")

    assert application.application_id == "APP-2026-0001"
    assert application.opportunity_id == opportunity_id
    assert application.display_slug == "example-labs-senior-product-manager"
    assert application.posting_snapshot_ids == ("PST-0001",)
    assert service.load(application.application_id) == application
    assert (root / "applications" / application.application_id / "manifest.json").is_file()
    assert (
        root / "applications" / application.application_id / "postings" / "PST-0001.json"
    ).is_file()
    assert OpportunityService(root).get(opportunity_id).status is OpportunityStatus.PURSUED


def test_pursuit_is_idempotent_and_one_opportunity_has_one_application(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    service = ApplicationService(root)
    first = service.create_from_opportunity(opportunity_id, "pursue-42")

    replayed = service.create_from_opportunity(opportunity_id, "pursue-42")
    same_opportunity = service.create_from_opportunity(opportunity_id, "another-key")

    assert replayed == first
    assert same_opportunity == first
    assert service.list() == (first,)


def test_display_slug_can_change_without_changing_identity_or_path(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    service = ApplicationService(root)
    original = service.create_from_opportunity(opportunity_id, "pursue-42")

    renamed = service.rename_display(
        original.application_id,
        company="Example Incorporated",
        role="Principal Product Lead",
    )

    assert renamed.application_id == original.application_id
    assert renamed.display_slug == "example-incorporated-principal-product-lead"
    assert (root / "applications" / original.application_id / "manifest.json").is_file()


def test_expired_opportunity_cannot_create_new_application(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    OpportunityService(root).set_status(opportunity_id, OpportunityStatus.EXPIRED, "posting closed")

    with pytest.raises(CareerError) as error:
        ApplicationService(root).create_from_opportunity(opportunity_id, "pursue-expired")

    assert error.value.code is ErrorCode.CONFLICT


def test_application_local_release_and_submission_sequences_are_independent(
    tmp_path: Path,
) -> None:
    registry = SequenceRegistry(tmp_path)

    assert registry.allocate_local_id("APP-2026-0001", "release") == "REL-0001"
    assert registry.allocate_local_id("APP-2026-0001", "submission") == "SUB-0001"
    assert registry.allocate_local_id("APP-2026-0002", "release") == "REL-0001"


def test_pursuit_recovers_when_manifest_commits_before_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    service = ApplicationService(root)
    from career_agent.services import applications as application_module

    real_write = application_module.atomic_write_json
    interrupted = False

    def interrupt_index_once(path: Path, value: object) -> None:
        nonlocal interrupted
        if path.name == "index.json" and not interrupted:
            interrupted = True
            raise OSError("simulated interruption before application index")
        real_write(path, value)

    monkeypatch.setattr(application_module, "atomic_write_json", interrupt_index_once)
    with pytest.raises(OSError, match="simulated interruption"):
        service.create_from_opportunity(opportunity_id, "pursue-42")

    recovered = service.create_from_opportunity(opportunity_id, "pursue-42")

    assert recovered.application_id == "APP-2026-0001"
    assert service.list() == (recovered,)
    assert not (root / "applications" / "APP-2026-0002").exists()


def test_pursuit_idempotency_key_cannot_cross_opportunities(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    first_opportunity = add_opportunity(root, key="capture-1")
    second_opportunity = (
        OpportunityService(root)
        .add(
            OpportunityCapture(
                company="Other Labs",
                title="Product Director",
                location="New York",
                url="https://jobs.example.test/roles/99",
                captured_at=NOW,
                posting_text="Own the roadmap.",
                posting_complete=True,
                requisition_id="REQ-99",
            ),
            idempotency_key="capture-2",
        )
        .opportunity_id
    )
    service = ApplicationService(root)
    service.create_from_opportunity(first_opportunity, "shared-key")

    with pytest.raises(CareerError) as error:
        service.create_from_opportunity(second_opportunity, "shared-key")

    assert error.value.code is ErrorCode.CONFLICT


def test_concurrent_pursuit_keeps_one_application_per_opportunity(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    barrier = Barrier(6)

    def pursue(index: int) -> str:
        barrier.wait()
        return (
            ApplicationService(root)
            .create_from_opportunity(
                opportunity_id,
                f"pursue-{index}",
            )
            .application_id
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        application_ids = list(pool.map(pursue, range(6)))

    assert len(set(application_ids)) == 1
    assert application_ids[0].startswith("APP-2026-")
    assert len(list((root / "applications").glob("APP-*/manifest.json"))) == 1


def test_pursuit_recovers_when_index_commits_before_opportunity_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    opportunity_id = add_opportunity(root)
    service = ApplicationService(root)
    real_set_status = service.opportunities.set_status
    interrupted = False

    def interrupt_status_once(
        target_id: str,
        status: OpportunityStatus,
        reason: str,
    ) -> object:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise OSError("simulated interruption before opportunity status")
        return real_set_status(target_id, status, reason)

    monkeypatch.setattr(service.opportunities, "set_status", interrupt_status_once)
    with pytest.raises(OSError, match="simulated interruption"):
        service.create_from_opportunity(opportunity_id, "pursue-42")

    recovered = service.create_from_opportunity(opportunity_id, "pursue-42")

    assert recovered.application_id == "APP-2026-0001"
    assert OpportunityService(root).get(opportunity_id).status is OpportunityStatus.PURSUED
