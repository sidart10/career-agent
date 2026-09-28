"""Read-only onboarding projection derived from authoritative workspace state."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from career_agent.config import workspace_identity
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.answer import RetentionClass
from career_agent.services.answers import AnswerService
from career_agent.services.capabilities import CapabilityService, CapabilityStatus
from career_agent.services.imports import ImportPreview
from career_agent.services.preferences import PreferenceService
from career_agent.services.privacy import PrivacyService
from career_agent.services.profile import ProfileService

OnboardingPhase = Literal[
    "workspace",
    "evidence",
    "privacy",
    "interpretation",
    "profile_review",
    "preferences",
    "installation",
    "migration",
]


class OnboardingStatus(BaseModel):
    profile_review_complete: bool = False
    onboarding_ready: bool = False
    evidence_coverage: str = "Incomplete; readiness is not a comprehensive profile assessment."
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_path: str
    workspace_id: str | None
    first_incomplete_phase: OnboardingPhase | None
    next_action: str
    imported_sources: int
    pending_imports: int
    pending_proposals: int
    unresolved_conflicts: int
    confirmed_facts: int
    preference_missing_fields: tuple[str, ...]
    preference_defaulted_fields: tuple[str, ...]
    redacted_answer_counts: dict[str, int]
    core_ready: bool
    document_ready: bool
    submission_ready: bool
    core_blockers: tuple[str, ...]


class OnboardingService:
    def __init__(self, root: Path, repository_root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.repository_root = repository_root.resolve(strict=False)

    def status(self) -> OnboardingStatus:
        try:
            identity = workspace_identity(self.root)
        except CareerError as error:
            if error.code is not ErrorCode.NOT_READY:
                raise
            return OnboardingStatus(
                workspace_path=str(self.root),
                workspace_id=None,
                first_incomplete_phase="workspace",
                next_action="career init",
                imported_sources=0,
                pending_imports=0,
                pending_proposals=0,
                unresolved_conflicts=0,
                confirmed_facts=0,
                preference_missing_fields=("target_roles",),
                preference_defaulted_fields=(),
                redacted_answer_counts={},
                core_ready=False,
                document_ready=False,
                submission_ready=False,
                core_blockers=("workspace",),
            )

        profile = ProfileService(self.root).load_state()
        privacy = PrivacyService(self.root).status()
        preferences = PreferenceService(self.root).load()
        answers = AnswerService(self.root).load_state()
        capabilities = CapabilityService(self.root, self.repository_root).report()

        pending_proposals = len(ProfileService(self.root).pending_proposals())
        unresolved_conflicts = len(ProfileService(self.root).unresolved_conflicts())
        imported_source_ids = {source.source_id for source in profile.imported_sources}
        interpreted_source_ids = {
            source.source_id for proposal in profile.proposals for source in proposal.sources
        }
        uninterpreted_sources = imported_source_ids - interpreted_source_ids
        pending_source_ids: set[str] = set()
        for path in self.root.glob("runs/RUN-*/import-preview.json"):
            try:
                preview = ImportPreview.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as error:
                raise CareerError(
                    ErrorCode.INTEGRITY_ERROR,
                    "Import preview is unreadable or invalid",
                    {"path": str(path)},
                ) from error
            pending_source_ids.update(
                source.source_id
                for source in preview.source_files
                if source.source_id not in imported_source_ids
            )
        pending_imports = len(pending_source_ids)
        answer_counts = {
            retention.value: sum(answer.retention_class is retention for answer in answers.answers)
            for retention in RetentionClass
            if retention is not RetentionClass.PROHIBITED
        }
        blockers = tuple(
            check.name
            for check in capabilities.capabilities
            if check.readiness_layer == "core" and check.status is not CapabilityStatus.READY
        )

        phase: OnboardingPhase | None = None
        next_action = "career opportunity add --help"
        if not profile.imported_sources:
            phase = "evidence"
            next_action = (
                "Add a resume or career-history text file to inbox/ and ask the agent to import it."
            )
        elif not privacy.acknowledged:
            phase = "privacy"
            next_action = "career privacy status"
        elif uninterpreted_sources:
            phase = "interpretation"
            next_action = (
                "Ask the agent to inspect imported evidence and propose supported profile facts."
            )
        elif not profile.facts and not pending_proposals:
            phase = "evidence"
            next_action = (
                "Provide additional career evidence; all suggestions have been reviewed "
                "without confirming a fact."
            )
        elif (
            not profile.proposals or not profile.facts or pending_proposals or unresolved_conflicts
        ):
            phase = "profile_review"
            next_action = "career profile list"
        elif preferences is None:
            phase = "preferences"
            next_action = "Tell the agent your target roles and preferences so it can save them."

        review_complete = (
            bool(profile.facts)
            and not pending_proposals
            and not unresolved_conflicts
            and not uninterpreted_sources
        )
        if identity.schema_version == 1:
            phase = "migration"
            next_action = (
                "Ask the agent to preview migration to workspace format 2; "
                "after approval, apply will back up affected files before replacement."
            )
        elif phase is None and not capabilities.core_ready:
            phase = "installation"
            next_action = "Run diagnostics and repair the reported core blockers."

        return OnboardingStatus(
            profile_review_complete=review_complete,
            onboarding_ready=phase is None and capabilities.core_ready,
            workspace_path=str(identity.path),
            workspace_id=identity.workspace_id,
            first_incomplete_phase=phase,
            next_action=next_action,
            imported_sources=len(profile.imported_sources),
            pending_imports=pending_imports,
            pending_proposals=pending_proposals,
            unresolved_conflicts=unresolved_conflicts,
            confirmed_facts=len(profile.facts),
            preference_missing_fields=("target_roles",) if preferences is None else (),
            preference_defaulted_fields=(
                preferences.defaulted_fields if preferences is not None else ()
            ),
            redacted_answer_counts=answer_counts,
            core_ready=capabilities.core_ready,
            document_ready=capabilities.document_ready,
            submission_ready=capabilities.submission_ready,
            core_blockers=blockers,
        )
