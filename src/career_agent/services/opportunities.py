"""Governed opportunity capture and reversible deduplication."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from pathlib import Path, PurePath
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel, UtcDateTime
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.opportunity import DiscoverySource, Opportunity, OpportunityStatus
from career_agent.security.urls import canonicalize_public_http_url
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry

MergeId = Annotated[str, Field(pattern=r"^MRG-\d{4}$")]


class OpportunityCapture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    url: str = Field(min_length=1)
    captured_at: UtcDateTime
    posting_text: str = Field(min_length=1)
    posting_complete: bool = False
    requisition_id: str | None = None
    deadline: date | None = None


class MergeRecord(PersistedModel):
    merge_id: MergeId
    reason: Literal["exact_requisition_id", "exact_canonical_url", "manual"]
    primary_snapshot: Opportunity
    duplicate_snapshot: Opportunity
    merged_snapshot: Opportunity


class DuplicateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    similarity: float = Field(ge=0, le=1)
    matching_fields: tuple[str, ...]


class OpportunityState(PersistedModel):
    opportunities: tuple[Opportunity, ...] = ()
    merges: tuple[MergeRecord, ...] = ()
    unmerged_merge_ids: tuple[str, ...] = ()
    idempotency_results: dict[str, str] = Field(default_factory=dict)


def _normalized_requisition(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip().casefold()


def _merge_sources(
    primary: Sequence[DiscoverySource], duplicate: Sequence[DiscoverySource]
) -> tuple[DiscoverySource, ...]:
    sources = {source.source_id: source for source in (*primary, *duplicate)}
    return tuple(sources[key] for key in sorted(sources))


class OpportunityService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(self.root, PurePath("opportunities", "state.json"))
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def load_state(self) -> OpportunityState:
        try:
            return OpportunityState.model_validate_json(self.path.read_text())
        except FileNotFoundError:
            return OpportunityState()
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Opportunity state is unreadable or invalid",
                {"path": str(self.path)},
            ) from error

    def _write_state(self, state: OpportunityState) -> None:
        atomic_write_json(self.path, state)

    @staticmethod
    def _replace(
        opportunities: tuple[Opportunity, ...], replacement: Opportunity
    ) -> tuple[Opportunity, ...]:
        return tuple(
            replacement if item.opportunity_id == replacement.opportunity_id else item
            for item in opportunities
        )

    @staticmethod
    def _find(state: OpportunityState, opportunity_id: str) -> Opportunity:
        opportunity = next(
            (item for item in state.opportunities if item.opportunity_id == opportunity_id),
            None,
        )
        if opportunity is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Unknown opportunity",
                {"opportunity_id": opportunity_id},
            )
        return opportunity

    @staticmethod
    def _inactive_duplicate_ids(state: OpportunityState) -> set[str]:
        unmerged = set(state.unmerged_merge_ids)
        return {
            merge.duplicate_snapshot.opportunity_id
            for merge in state.merges
            if merge.merge_id not in unmerged
        }

    def list(self) -> tuple[Opportunity, ...]:
        state = self.load_state()
        inactive = self._inactive_duplicate_ids(state)
        return tuple(item for item in state.opportunities if item.opportunity_id not in inactive)

    def get(self, opportunity_id: str) -> Opportunity:
        return self._find(self.load_state(), opportunity_id)

    def set_status(
        self,
        opportunity_id: str,
        status: OpportunityStatus,
        reason: str,
    ) -> Opportunity:
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="opportunity.status",
            idempotency_key=f"opportunity-status:{opportunity_id}:{status.value}",
            status=OperationStatus.STARTED,
        )
        replay = self.journal.replay(operation.idempotency_key)
        if replay is not None:
            return self.get(opportunity_id)
        active_operation = self.journal.operation_for_key(operation.idempotency_key) or operation
        with WorkspaceLock(self.root, run_id=active_operation.run_id):
            state = self.load_state()
            current = self._find(state, opportunity_id)
            if current.status is status:
                if self.journal.replay(operation.idempotency_key) is None:
                    self._finish(active_operation, [opportunity_id])
                return current
            self.journal.begin(active_operation)
            updated_opportunity = current.model_copy(
                update={"status": status, "updated_at": datetime.now(UTC)}
            )
            updated = state.model_copy(
                update={
                    "opportunities": self._replace(
                        state.opportunities,
                        updated_opportunity,
                    ),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._write_state(updated)
            self.journal.checkpoint(
                active_operation.run_id,
                "status-reason",
                {"reason": reason},
            )
            self._finish(active_operation, [opportunity_id])
            return updated_opportunity

    @staticmethod
    def _exact_match(
        existing: Opportunity, candidate: Opportunity
    ) -> Literal["exact_requisition_id", "exact_canonical_url"] | None:
        existing_req = _normalized_requisition(existing.requisition_id)
        candidate_req = _normalized_requisition(candidate.requisition_id)
        if existing_req is not None and existing_req == candidate_req:
            return "exact_requisition_id"
        if existing.canonical_url is not None and str(existing.canonical_url) == str(
            candidate.canonical_url
        ):
            return "exact_canonical_url"
        return None

    @staticmethod
    def _merged(primary: Opportunity, duplicate: Opportunity) -> Opportunity:
        return primary.model_copy(
            update={
                "sources": _merge_sources(primary.sources, duplicate.sources),
                "updated_at": datetime.now(UTC),
            }
        )

    def _finish(
        self,
        operation: OperationRecord,
        result_references: Sequence[str],
    ) -> None:
        checksum = sha256_file(self.path)
        self.journal.checkpoint(operation.run_id, "opportunities-written", {"checksum": checksum})
        self.journal.commit(
            operation.run_id,
            {"state_checksum": checksum, "result_references": list(result_references)},
        )

    def add(self, capture: OpportunityCapture, idempotency_key: str) -> Opportunity:
        state = self.load_state()
        existing_id = state.idempotency_results.get(idempotency_key)
        if existing_id is not None:
            prior = self.journal.operation_for_key(f"opportunity-add:{idempotency_key}")
            if prior is not None and self.journal.replay(prior.idempotency_key) is None:
                with WorkspaceLock(self.root, run_id=prior.run_id):
                    self._finish(prior, [existing_id])
            return self._find(state, existing_id)

        opportunity_id = self.registry.allocate_opportunity_id(capture.captured_at.year)
        merge_id = self.registry.allocate_merge_id()
        run_id = self.registry.allocate_run_id()
        canonical_url = canonicalize_public_http_url(capture.url)
        validated_url = AnyHttpUrl(canonical_url)
        posting_checksum = hashlib.sha256(capture.posting_text.encode()).hexdigest()
        source_digest = hashlib.sha256(f"{canonical_url}\0{posting_checksum}".encode()).hexdigest()[
            :16
        ]
        candidate = Opportunity(
            opportunity_id=opportunity_id,
            company=capture.company,
            title=capture.title,
            location=capture.location,
            status=(
                OpportunityStatus.EXPIRED
                if capture.deadline is not None and capture.deadline < date.today()
                else OpportunityStatus.DISCOVERED
            ),
            sources=(
                DiscoverySource(
                    source_id=f"SRC-{source_digest}",
                    url=validated_url,
                    captured_at=capture.captured_at,
                    original_url=capture.url,
                ),
            ),
            posting_checksum=posting_checksum,
            requisition_id=capture.requisition_id,
            canonical_url=validated_url,
            posting_text=capture.posting_text,
            posting_complete=capture.posting_complete,
            deadline=capture.deadline,
        )
        operation = OperationRecord(
            run_id=run_id,
            operation="opportunity.add",
            idempotency_key=f"opportunity-add:{idempotency_key}",
            status=OperationStatus.STARTED,
        )
        with WorkspaceLock(self.root, run_id=run_id):
            state = self.load_state()
            existing_id = state.idempotency_results.get(idempotency_key)
            if existing_id is not None:
                prior = self.journal.operation_for_key(operation.idempotency_key)
                if prior is not None and self.journal.replay(prior.idempotency_key) is None:
                    self._finish(prior, [existing_id])
                return self._find(state, existing_id)
            self.journal.begin(operation)
            active = self.list()
            match = next(
                (
                    (item, reason)
                    for item in active
                    if (reason := self._exact_match(item, candidate)) is not None
                ),
                None,
            )
            opportunities = (*state.opportunities, candidate)
            merges = state.merges
            result = candidate
            if match is not None:
                primary, reason = match
                result = self._merged(primary, candidate)
                opportunities = self._replace(opportunities, result)
                merges = (
                    *merges,
                    MergeRecord(
                        merge_id=merge_id,
                        reason=reason,
                        primary_snapshot=primary,
                        duplicate_snapshot=candidate,
                        merged_snapshot=result,
                    ),
                )
            idempotency_results = dict(state.idempotency_results)
            idempotency_results[idempotency_key] = result.opportunity_id
            updated = state.model_copy(
                update={
                    "opportunities": opportunities,
                    "merges": merges,
                    "idempotency_results": idempotency_results,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._write_state(updated)
            self._finish(operation, [result.opportunity_id])
            return result

    def duplicate_candidates(self, opportunity_id: str) -> tuple[DuplicateCandidate, ...]:
        state = self.load_state()
        target = self._find(state, opportunity_id)
        candidates: list[DuplicateCandidate] = []
        for other in self.list():
            if other.opportunity_id == opportunity_id or self._exact_match(target, other):
                continue
            fields = {
                "company": SequenceMatcher(
                    None, target.company.casefold(), other.company.casefold()
                ).ratio(),
                "title": SequenceMatcher(
                    None, target.title.casefold(), other.title.casefold()
                ).ratio(),
                "location": SequenceMatcher(
                    None, target.location.casefold(), other.location.casefold()
                ).ratio(),
            }
            similarity = sum(fields.values()) / len(fields)
            if similarity >= 0.75:
                candidates.append(
                    DuplicateCandidate(
                        opportunity_id=other.opportunity_id,
                        similarity=similarity,
                        matching_fields=tuple(key for key, score in fields.items() if score >= 0.9),
                    )
                )
        return tuple(sorted(candidates, key=lambda item: (-item.similarity, item.opportunity_id)))

    def merge(self, primary_id: str, duplicate_id: str) -> MergeRecord:
        if primary_id == duplicate_id:
            raise CareerError(ErrorCode.INVALID_INPUT, "Cannot merge an opportunity with itself")
        merge_id = self.registry.allocate_merge_id()
        run_id = self.registry.allocate_run_id()
        idempotency_key = f"opportunity-merge:{primary_id}:{duplicate_id}"
        replay = self.journal.replay(idempotency_key)
        if replay is not None:
            references = replay.result.get("result_references", [])
            if not isinstance(references, list):
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Merge replay result is invalid",
                    {"idempotency_key": idempotency_key},
                )
            result_ids = {str(reference) for reference in references}
            return next(item for item in self.load_state().merges if item.merge_id in result_ids)
        operation = OperationRecord(
            run_id=run_id,
            operation="opportunity.merge",
            idempotency_key=idempotency_key,
            status=OperationStatus.STARTED,
        )
        active_operation = self.journal.operation_for_key(idempotency_key) or operation
        with WorkspaceLock(self.root, run_id=active_operation.run_id):
            state = self.load_state()
            existing_record = next(
                (
                    item
                    for item in state.merges
                    if item.merge_id not in state.unmerged_merge_ids
                    and item.primary_snapshot.opportunity_id == primary_id
                    and item.duplicate_snapshot.opportunity_id == duplicate_id
                ),
                None,
            )
            if existing_record is not None:
                self._finish(active_operation, [existing_record.merge_id])
                return existing_record
            inactive = self._inactive_duplicate_ids(state)
            if primary_id in inactive or duplicate_id in inactive:
                raise CareerError(
                    ErrorCode.CONFLICT, "Opportunity is already part of an active merge"
                )
            primary = self._find(state, primary_id)
            duplicate = self._find(state, duplicate_id)
            merged = self._merged(primary, duplicate)
            record = MergeRecord(
                merge_id=merge_id,
                reason="manual",
                primary_snapshot=primary,
                duplicate_snapshot=duplicate,
                merged_snapshot=merged,
            )
            self.journal.begin(active_operation)
            updated = state.model_copy(
                update={
                    "opportunities": self._replace(state.opportunities, merged),
                    "merges": (*state.merges, record),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._write_state(updated)
            self._finish(active_operation, [record.merge_id])
            return record

    def unmerge(self, merge_id: str) -> tuple[Opportunity, Opportunity]:
        run_id = self.registry.allocate_run_id()
        idempotency_key = f"opportunity-unmerge:{merge_id}"
        operation = OperationRecord(
            run_id=run_id,
            operation="opportunity.unmerge",
            idempotency_key=idempotency_key,
            status=OperationStatus.STARTED,
        )
        active_operation = self.journal.operation_for_key(idempotency_key) or operation
        with WorkspaceLock(self.root, run_id=active_operation.run_id):
            state = self.load_state()
            record = next((item for item in state.merges if item.merge_id == merge_id), None)
            if record is None:
                raise CareerError(ErrorCode.INVALID_INPUT, "Unknown merge", {"merge_id": merge_id})
            if merge_id in state.unmerged_merge_ids:
                if self.journal.replay(idempotency_key) is None:
                    self._finish(
                        active_operation,
                        [
                            record.primary_snapshot.opportunity_id,
                            record.duplicate_snapshot.opportunity_id,
                        ],
                    )
                return record.primary_snapshot, record.duplicate_snapshot
            current = self._find(state, record.primary_snapshot.opportunity_id)
            if current != record.merged_snapshot:
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Merged opportunity changed and cannot be restored automatically",
                    {"merge_id": merge_id},
                )
            self.journal.begin(active_operation)
            opportunities = self._replace(state.opportunities, record.primary_snapshot)
            opportunities = self._replace(opportunities, record.duplicate_snapshot)
            updated = state.model_copy(
                update={
                    "opportunities": opportunities,
                    "unmerged_merge_ids": (*state.unmerged_merge_ids, merge_id),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._write_state(updated)
            self._finish(
                active_operation,
                [
                    record.primary_snapshot.opportunity_id,
                    record.duplicate_snapshot.opportunity_id,
                ],
            )
            return record.primary_snapshot, record.duplicate_snapshot
