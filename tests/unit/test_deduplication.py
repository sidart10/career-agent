from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.security.urls import canonicalize_public_http_url
from career_agent.services.opportunities import OpportunityCapture, OpportunityService

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=UTC)


def capture(
    requisition_id: str | None,
    url: str,
    *,
    company: str = "Example Labs",
    title: str = "Product Manager",
    location: str = "Remote",
) -> OpportunityCapture:
    return OpportunityCapture(
        company=company,
        title=title,
        location=location,
        url=url,
        captured_at=NOW,
        posting_text="Own product strategy and delivery.",
        posting_complete=True,
        requisition_id=requisition_id,
    )


def test_canonical_url_removes_tracking_without_changing_role_identity() -> None:
    assert (
        canonicalize_public_http_url(
            "HTTPS://Jobs.Example.test:443/roles/42?department=product&utm_source=email&gclid=abc#apply"
        )
        == "https://jobs.example.test/roles/42?department=product"
    )
    assert (
        canonicalize_public_http_url("https://jobs.example.test/roles/42/")
        == "https://jobs.example.test/roles/42/"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/posting",
        "http://127.0.0.1/jobs/1",
        "https://localhost/jobs/1",
        "https://user:secret@jobs.example.test/roles/42",
        "https://jobs.example.test/out?redirect=http://192.168.1.2/internal",
    ],
)
def test_url_canonicalization_rejects_non_public_or_credentialed_targets(url: str) -> None:
    with pytest.raises(CareerError) as error:
        canonicalize_public_http_url(url)

    assert error.value.code is ErrorCode.INVALID_INPUT


def test_exact_requisition_id_auto_merges_and_preserves_both_sources(tmp_path: Path) -> None:
    service = OpportunityService(tmp_path / "workspace")
    first = service.add(
        capture("REQ-42", "https://jobs.example.test/roles/42?utm_source=board-a"),
        idempotency_key="source-a",
    )
    merged = service.add(
        capture("req-42", "https://boards.example.test/jobs/987"),
        idempotency_key="source-b",
    )

    assert merged.opportunity_id == first.opportunity_id
    assert {str(source.url) for source in merged.sources} == {
        "https://jobs.example.test/roles/42",
        "https://boards.example.test/jobs/987",
    }
    assert {source.original_url for source in merged.sources} == {
        "https://jobs.example.test/roles/42?utm_source=board-a",
        "https://boards.example.test/jobs/987",
    }
    assert len(service.load_state().merges) == 1
    assert len(service.list()) == 1


def test_tracking_variants_of_same_canonical_url_auto_merge(tmp_path: Path) -> None:
    service = OpportunityService(tmp_path / "workspace")
    first = service.add(
        capture(None, "https://jobs.example.test/roles/42?utm_campaign=fall"),
        idempotency_key="source-a",
    )
    merged = service.add(
        capture(None, "https://jobs.example.test/roles/42?fbclid=tracking"),
        idempotency_key="source-b",
    )

    assert merged.opportunity_id == first.opportunity_id
    assert len(service.load_state().merges) == 1


def test_distinct_requisitions_with_same_metadata_never_auto_merge(tmp_path: Path) -> None:
    service = OpportunityService(tmp_path / "workspace")
    first = service.add(
        capture("REQ-100", "https://jobs.example.test/roles/100"),
        idempotency_key="capture-100",
    )
    second = service.add(
        capture("REQ-101", "https://jobs.example.test/roles/101"),
        idempotency_key="capture-101",
    )

    assert len(service.list()) == 2
    candidates = service.duplicate_candidates(first.opportunity_id)
    assert [candidate.opportunity_id for candidate in candidates] == [second.opportunity_id]
    assert service.load_state().merges == ()


def test_manual_merge_and_unmerge_restore_original_snapshots(tmp_path: Path) -> None:
    service = OpportunityService(tmp_path / "workspace")
    first = service.add(
        capture("REQ-100", "https://jobs.example.test/roles/100"),
        idempotency_key="capture-100",
    )
    second = service.add(
        capture("REQ-101", "https://jobs.example.test/roles/101"),
        idempotency_key="capture-101",
    )

    merge = service.merge(first.opportunity_id, second.opportunity_id)
    assert len(service.list()) == 1
    restored = service.unmerge(merge.merge_id)

    assert restored == (first, second)
    assert service.list() == (first, second)
    persisted = service.load_state().merges[0]
    assert persisted.primary_snapshot == first
    assert persisted.duplicate_snapshot == second
    journal_text = service.journal.path.read_text()
    assert '"operation":"opportunity.merge"' in journal_text
    assert '"operation":"opportunity.unmerge"' in journal_text
