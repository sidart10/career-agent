"""Canonical confirmed profile and explicit conflict resolution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from career_agent.errors import CareerError, ErrorCode
from career_agent.models.base import PersistedModel, SourceReference
from career_agent.models.operation import OperationRecord, OperationStatus
from career_agent.models.profile import ConfirmationState, ProfileFact
from career_agent.services.imports import (
    FactConflict,
    ImportedSource,
    ImportPreview,
    ImportResult,
    ImportService,
    ProposedFact,
    build_conflicts,
)
from career_agent.services.privacy import PrivacyService
from career_agent.storage.atomic import atomic_write_json
from career_agent.storage.checksums import sha256_file
from career_agent.storage.journal import OperationJournal
from career_agent.storage.locks import WorkspaceLock
from career_agent.storage.paths import safe_resolve
from career_agent.storage.registry import SequenceRegistry


class ProfileState(PersistedModel):
    schema_version: Literal[1, 2] = 2  # type: ignore[assignment]  # Explicit legacy reader.
    rejected_proposals: dict[str, str] = Field(default_factory=dict)
    facts: tuple[ProfileFact, ...] = ()
    proposals: tuple[ProposedFact, ...] = ()
    conflicts: tuple[FactConflict, ...] = ()
    imported_sources: tuple[ImportedSource, ...] = ()
    applied_runs: tuple[str, ...] = ()


class ExactEvidenceInput(BaseModel):
    """One exact span emitted by the model-assisted interpretation step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    source_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_text_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    extractor: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    exact_text: str = Field(min_length=1)


class ProfileProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    value: JsonValue
    source: ExactEvidenceInput


class ProfileProposalBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposals: tuple[ProfileProposalInput, ...] = Field(min_length=1)


class ProfileService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.path = safe_resolve(self.root, PurePath("profile", "profile.json"))
        self.imports = ImportService(self.root)
        self.registry = SequenceRegistry(self.root)
        self.journal = OperationJournal(self.root)

    def preview_import(self, sources: Sequence[Path]) -> ImportPreview:
        return self.imports.preview(sources)

    def load_state(self) -> ProfileState:
        try:
            return ProfileState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ProfileState()
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Canonical profile is unreadable or invalid",
                {"path": str(self.path)},
            ) from error

    def _write_state(self, state: ProfileState) -> None:
        atomic_write_json(self.path, state)

    def pending_proposals(self) -> tuple[ProposedFact, ...]:
        state = self.load_state()
        reviewed = {fact.fact_id for fact in state.facts} | set(state.rejected_proposals)
        for conflict in state.conflicts:
            if conflict.resolved_fact_id is not None:
                reviewed.update(p.fact_id for p in conflict.alternatives if p.fact_id is not None)
        return tuple(p for p in state.proposals if p.fact_id not in reviewed)

    def unresolved_conflicts(self) -> tuple[FactConflict, ...]:
        state = self.load_state()
        return tuple(
            conflict
            for conflict in state.conflicts
            if conflict.resolved_fact_id is None
            and any(p.fact_id not in state.rejected_proposals for p in conflict.alternatives)
        )

    def reject_fact(self, fact_id: str, reason: str) -> ProfileState:
        if not reason.strip():
            raise CareerError(ErrorCode.INVALID_INPUT, "Explain why this proposal is rejected")
        key = f"profile-reject:{fact_id}"
        existing_operation = self.journal.operation_for_key(key)
        run_id = (
            existing_operation.run_id
            if existing_operation is not None
            else self.registry.allocate_run_id()
        )
        with WorkspaceLock(self.root, run_id=run_id):
            state = self.load_state()
            if fact_id in {f.fact_id for f in state.facts}:
                raise CareerError(ErrorCode.CONFLICT, "A confirmed fact cannot be rejected")
            if fact_id not in {p.fact_id for p in state.proposals}:
                raise CareerError(ErrorCode.INVALID_INPUT, "Unknown proposal")
            if fact_id in state.rejected_proposals:
                if state.rejected_proposals[fact_id] != reason.strip():
                    raise CareerError(
                        ErrorCode.CONFLICT, "Proposal already rejected with another reason"
                    )
                if existing_operation is not None and self.journal.replay(key) is None:
                    self.journal.commit(
                        run_id, {"fact_id": fact_id, "result_references": ["profile/profile.json"]}
                    )
                return state
            operation = OperationRecord(
                run_id=run_id,
                operation="profile.fact.reject",
                idempotency_key=key,
                status=OperationStatus.STARTED,
            )
            self.journal.begin(existing_operation or operation)
            updated = state.model_copy(
                update={
                    "rejected_proposals": {**state.rejected_proposals, fact_id: reason.strip()},
                    "updated_at": datetime.now(UTC),
                }
            )
            self._write_state(updated)
            self.journal.commit(
                run_id, {"fact_id": fact_id, "result_references": ["profile/profile.json"]}
            )
            return updated

    @staticmethod
    def _proposal_id(proposal: ProfileProposalInput) -> str:
        payload = json.dumps(
            proposal.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"PROPOSAL-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"

    def _validate_evidence(
        self,
        evidence: ExactEvidenceInput,
        sources: dict[str, ImportedSource],
    ) -> SourceReference:
        imported = sources.get(evidence.source_id)
        if imported is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal references an unknown imported source",
                {"source_id": evidence.source_id},
            )
        expected = (
            imported.checksum,
            imported.normalized_text_checksum,
            imported.extractor,
            imported.extractor_version,
        )
        supplied = (
            evidence.source_checksum,
            evidence.normalized_text_checksum,
            evidence.extractor,
            evidence.extractor_version,
        )
        if supplied != expected:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal extraction provenance does not match the imported source",
                {"source_id": evidence.source_id},
            )
        if imported.extracted_text_path is None:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal source has no extracted text",
                {"source_id": evidence.source_id},
            )
        if imported.warnings:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal source has unresolved extraction warnings",
                {"source_id": evidence.source_id, "warnings": list(imported.warnings)},
            )
        recorded_path = Path(imported.extracted_text_path)
        text_path = (
            recorded_path.resolve(strict=False)
            if recorded_path.is_absolute()
            else safe_resolve(self.root, PurePath(recorded_path))
        )
        if not text_path.is_relative_to(self.root):
            raise CareerError(ErrorCode.INTEGRITY_ERROR, "Extracted text path left the workspace")
        try:
            text = text_path.read_text(encoding="utf-8")
        except OSError as error:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Extracted text is unavailable",
                {"source_id": evidence.source_id},
            ) from error
        if hashlib.sha256(text.encode()).hexdigest() != evidence.normalized_text_checksum:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Extracted text checksum no longer matches its import record",
                {"source_id": evidence.source_id},
            )
        block = next((item for item in imported.blocks if item.block_id == evidence.block_id), None)
        if block is None or block.page_number != evidence.page_number:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal references an unknown extraction block",
                {"source_id": evidence.source_id, "block_id": evidence.block_id},
            )
        if not (
            block.start_offset <= evidence.start_offset < evidence.end_offset <= block.end_offset
        ):
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal evidence span falls outside its extraction block",
                {"source_id": evidence.source_id, "block_id": evidence.block_id},
            )
        if text[evidence.start_offset : evidence.end_offset] != evidence.exact_text:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Proposal exact text does not match the imported evidence span",
                {"source_id": evidence.source_id, "block_id": evidence.block_id},
            )
        return SourceReference(
            source_id=evidence.source_id,
            locator=f"{Path(imported.stored_path).name}#{evidence.block_id}",
            checksum=evidence.source_checksum,
            normalized_text_checksum=evidence.normalized_text_checksum,
            extractor=evidence.extractor,
            extractor_version=evidence.extractor_version,
            block_id=evidence.block_id,
            page_number=evidence.page_number,
            start_offset=evidence.start_offset,
            end_offset=evidence.end_offset,
            exact_text=evidence.exact_text,
        )

    def propose(self, batch: ProfileProposalBatch) -> tuple[ProposedFact, ...]:
        """Validate and persist model suggestions without confirming any fact."""

        PrivacyService(self.root).require_acknowledgement()
        state = self.load_state()
        sources = {source.source_id: source for source in state.imported_sources}
        incoming: list[tuple[str, ProfileProposalInput, SourceReference]] = []
        for proposal in batch.proposals:
            incoming.append(
                (
                    self._proposal_id(proposal),
                    proposal,
                    self._validate_evidence(proposal.source, sources),
                )
            )
        existing = {proposal.proposal_id: proposal for proposal in state.proposals}
        idempotency_key = (
            "profile-propose:"
            + hashlib.sha256(
                json.dumps(batch.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest()
        )
        replay = self.journal.replay(idempotency_key)
        if replay is not None:
            try:
                return tuple(existing[proposal_id] for proposal_id, _, _ in incoming)
            except KeyError as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Committed proposal operation is missing profile state",
                ) from error
        new_ids = [proposal_id for proposal_id, _, _ in incoming if proposal_id not in existing]
        allocated = {proposal_id: self.registry.allocate_fact_id() for proposal_id in new_ids}
        active_operation = self.journal.operation_for_key(idempotency_key)
        operation = active_operation or OperationRecord(
            run_id=self.registry.allocate_run_id(),
            operation="profile.propose",
            idempotency_key=idempotency_key,
            status=OperationStatus.STARTED,
        )
        with WorkspaceLock(self.root, run_id=operation.run_id):
            self.journal.begin(operation)
            state = self.load_state()
            proposals = {proposal.proposal_id: proposal for proposal in state.proposals}
            result: list[ProposedFact] = []
            for proposal_id, request, reference in incoming:
                proposed_fact = proposals.get(proposal_id)
                if proposed_fact is None:
                    proposed_fact = ProposedFact(
                        proposal_id=proposal_id,
                        fact_id=allocated[proposal_id],
                        key=request.key,
                        value=request.value,
                        sources=(reference,),
                    )
                    proposals[proposal_id] = proposed_fact
                result.append(proposed_fact)
            previous = {conflict.conflict_id: conflict for conflict in state.conflicts}
            conflicts = tuple(
                conflict.model_copy(
                    update={
                        "resolved_fact_id": (
                            previous[conflict.conflict_id].resolved_fact_id
                            if conflict.conflict_id in previous
                            else None
                        )
                    }
                )
                for conflict in build_conflicts(tuple(proposals.values()))
            )
            updated = state.model_copy(
                update={
                    "proposals": tuple(proposals[key] for key in sorted(proposals)),
                    "conflicts": conflicts,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._write_state(updated)
            checksum = sha256_file(self.path)
            self.journal.commit(
                operation.run_id,
                {
                    "profile_checksum": checksum,
                    "proposal_ids": [item.proposal_id for item in result],
                    "result_references": [str(self.path)],
                },
            )
        return tuple(result)

    @staticmethod
    def _canonicalize_result(
        state: ProfileState,
        result: ImportResult,
    ) -> tuple[ImportResult, dict[str, ProposedFact], dict[str, FactConflict]]:
        proposals = {proposal.proposal_id: proposal for proposal in state.proposals}
        canonical_incoming: list[ProposedFact] = []
        for proposal in result.proposed_facts:
            canonical = proposals.get(proposal.proposal_id, proposal)
            proposals[proposal.proposal_id] = canonical
            canonical_incoming.append(canonical)
        previous_conflicts = {conflict.conflict_id: conflict for conflict in state.conflicts}
        conflicts: dict[str, FactConflict] = {}
        for conflict in build_conflicts(tuple(proposals.values())):
            previous = previous_conflicts.get(conflict.conflict_id)
            conflicts[conflict.conflict_id] = conflict.model_copy(
                update={
                    "resolved_fact_id": (
                        previous.resolved_fact_id if previous is not None else None
                    )
                }
            )
        normalized = result.model_copy(
            update={
                "proposed_facts": tuple(canonical_incoming),
                "conflicts": tuple(conflicts[key] for key in sorted(conflicts)),
            }
        )
        return normalized, proposals, conflicts

    @staticmethod
    def _merge_sources(
        existing: tuple[ImportedSource, ...],
        incoming: tuple[ImportedSource, ...],
    ) -> tuple[ImportedSource, ...]:
        by_id = {source.source_id: source for source in existing}
        for source in incoming:
            previous = by_id.get(source.source_id)
            if previous is None:
                by_id[source.source_id] = source
                continue
            paths = tuple(dict.fromkeys((*previous.source_paths, *source.source_paths)))
            by_id[source.source_id] = previous.model_copy(update={"source_paths": paths})
        return tuple(by_id[key] for key in sorted(by_id))

    def apply_import(
        self,
        run_id: str,
        source_ids: Sequence[str] | None = None,
    ) -> ImportResult:
        result = self.imports.apply(run_id, source_ids)
        selection = "all" if source_ids is None else ",".join(sorted(set(source_ids)))
        selection_digest = hashlib.sha256(selection.encode()).hexdigest()[:16]
        idempotency_key = f"profile-import:{run_id}:{selection_digest}"
        active_operation = self.journal.operation_for_key(idempotency_key)
        operation_run_id = (
            active_operation.run_id
            if active_operation is not None
            else (
                run_id
                if not any(item.run_id == run_id for item in self.journal.operations())
                else self.registry.allocate_run_id()
            )
        )
        operation = active_operation or OperationRecord(
            run_id=operation_run_id,
            operation="profile.import.apply",
            idempotency_key=idempotency_key,
            status=OperationStatus.STARTED,
        )
        replay = self.journal.replay(operation.idempotency_key)
        if replay is not None:
            return result
        active_operation = operation
        self.journal.begin(active_operation)
        with WorkspaceLock(self.root, run_id=active_operation.run_id):
            state = self.load_state()
            normalized_result, proposals, conflicts = self._canonicalize_result(state, result)
            merged_proposals = tuple(proposals[key] for key in sorted(proposals))
            merged_conflicts = tuple(conflicts[key] for key in sorted(conflicts))
            merged_sources = self._merge_sources(
                state.imported_sources,
                result.imported_sources,
            )
            applied_runs = (
                state.applied_runs
                if run_id in state.applied_runs
                else (*state.applied_runs, run_id)
            )
            if (
                merged_proposals != state.proposals
                or merged_conflicts != state.conflicts
                or merged_sources != state.imported_sources
                or applied_runs != state.applied_runs
            ):
                updated = state.model_copy(
                    update={
                        "proposals": merged_proposals,
                        "conflicts": merged_conflicts,
                        "imported_sources": merged_sources,
                        "applied_runs": applied_runs,
                        "updated_at": datetime.now(UTC),
                    }
                )
                self._write_state(updated)
            self.imports.persist_result(normalized_result)
            checksum = sha256_file(self.path)
            self.journal.checkpoint(
                active_operation.run_id,
                "profile-written",
                {"checksum": checksum},
            )
            self.journal.commit(
                active_operation.run_id,
                {
                    "profile_checksum": checksum,
                    "result_references": [str(self.path)],
                },
            )
        return normalized_result

    def confirm_fact(
        self,
        fact_id: str,
        value: JsonValue,
        source_ids: Sequence[str],
    ) -> ProfileFact:
        state = self.load_state()
        if fact_id in state.rejected_proposals:
            raise CareerError(ErrorCode.CONFLICT, "Rejected proposal cannot be confirmed")
        existing = next((fact for fact in state.facts if fact.fact_id == fact_id), None)
        requested_sources = set(source_ids)
        if existing is not None:
            if (
                existing.value != value
                or {item.source_id for item in existing.sources} != requested_sources
            ):
                raise CareerError(
                    ErrorCode.CONFLICT,
                    "Confirmed fact already exists with different arguments",
                    {"fact_id": fact_id},
                )
            idempotency_key = f"profile-confirm:{fact_id}"
            active_operation = self.journal.operation_for_key(idempotency_key)
            if active_operation is not None and self.journal.replay(idempotency_key) is None:
                with WorkspaceLock(self.root, run_id=active_operation.run_id):
                    checksum = sha256_file(self.path)
                    self.journal.checkpoint(
                        active_operation.run_id,
                        "profile-written",
                        {"checksum": checksum},
                    )
                    self.journal.commit(
                        active_operation.run_id,
                        {
                            "fact_id": existing.fact_id,
                            "profile_checksum": checksum,
                            "result_references": [existing.fact_id],
                        },
                    )
            return existing
        run_id = self.registry.allocate_run_id()
        operation = OperationRecord(
            run_id=run_id,
            operation="profile.fact.confirm",
            idempotency_key=f"profile-confirm:{fact_id}",
            status=OperationStatus.STARTED,
        )
        active_operation = self.journal.operation_for_key(operation.idempotency_key) or operation
        self.journal.begin(active_operation)
        with WorkspaceLock(self.root, run_id=active_operation.run_id):
            state = self.load_state()
            if fact_id in state.rejected_proposals:
                raise CareerError(ErrorCode.CONFLICT, "Rejected proposal cannot be confirmed")
            existing = next((fact for fact in state.facts if fact.fact_id == fact_id), None)
            if existing is not None:
                if (
                    existing.value != value
                    or {item.source_id for item in existing.sources} != requested_sources
                ):
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "Confirmed fact already exists with different arguments",
                        {"fact_id": fact_id},
                    )
                return existing
            proposal = next(
                (item for item in state.proposals if item.fact_id == fact_id),
                None,
            )
            if proposal is None:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Unknown proposed fact",
                    {"fact_id": fact_id},
                )
            if not proposal.supported:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Unsupported suggestions cannot become confirmed facts",
                    {"fact_id": fact_id},
                )
            if proposal.value != value:
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Confirmed value must match the evidence-backed proposal",
                    {"fact_id": fact_id},
                )
            available_sources = {source.source_id for source in proposal.sources}
            if not requested_sources or not requested_sources.issubset(available_sources):
                raise CareerError(
                    ErrorCode.INVALID_INPUT,
                    "Confirmed sources must belong to the proposal",
                    {"fact_id": fact_id},
                )
            for conflict in state.conflicts:
                if any(
                    item.fact_id == fact_id for item in conflict.alternatives
                ) and conflict.resolved_fact_id not in {None, fact_id}:
                    raise CareerError(
                        ErrorCode.CONFLICT,
                        "This fact conflict was already resolved differently",
                        {"conflict_id": conflict.conflict_id},
                    )
            now = datetime.now(UTC)
            fact = ProfileFact(
                fact_id=fact_id,
                key=proposal.key,
                value=value,
                sources=tuple(
                    source for source in proposal.sources if source.source_id in requested_sources
                ),
                confirmation_state=ConfirmationState.CONFIRMED,
                confirmer="user",
                confirmed_at=now,
            )
            conflicts = tuple(
                conflict.model_copy(update={"resolved_fact_id": fact_id})
                if any(item.fact_id == fact_id for item in conflict.alternatives)
                else conflict
                for conflict in state.conflicts
            )
            updated = state.model_copy(
                update={
                    "facts": (*state.facts, fact),
                    "conflicts": conflicts,
                    "updated_at": now,
                }
            )
            self._write_state(updated)
            checksum = sha256_file(self.path)
            self.journal.checkpoint(
                active_operation.run_id,
                "profile-written",
                {"checksum": checksum},
            )
            self.journal.commit(
                active_operation.run_id,
                {
                    "fact_id": fact.fact_id,
                    "profile_checksum": checksum,
                    "result_references": [fact.fact_id],
                },
            )
            return fact

    def get_confirmed_fact(self, fact_id: str) -> ProfileFact:
        fact = next(
            (item for item in self.load_state().facts if item.fact_id == fact_id),
            None,
        )
        if fact is None or fact.confirmation_state is not ConfirmationState.CONFIRMED:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Fact is not confirmed evidence",
                {"fact_id": fact_id},
            )
        return fact
