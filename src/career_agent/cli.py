"""Command-line entry point for governed career workspace operations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Never

import typer
from pydantic import ValidationError

from career_agent.approval.interactive import InteractiveApprovalAuthority
from career_agent.config import doctor_report, workspace_root
from career_agent.documents.release import DocumentService, ReleaseRequest
from career_agent.errors import CareerError, ErrorCode
from career_agent.models.application import ApplicationStage
from career_agent.models.submission import SubmissionResolution
from career_agent.projections.pipeline import write_pipeline
from career_agent.security.redaction import redact_text, sanitize
from career_agent.services.answers import (
    AnswerService,
    DeletionPreview,
    DeletionResult,
    QuestionContext,
    SetAnswerCommand,
)
from career_agent.services.applications import ApplicationService
from career_agent.services.approvals import ApprovalService
from career_agent.services.cleanup import CleanupService
from career_agent.services.evaluation import EvaluationDraft, EvaluationService
from career_agent.services.migrations import MigrationService
from career_agent.services.opportunities import OpportunityCapture, OpportunityService
from career_agent.services.payloads import PayloadService, PrepareSubmissionRequest
from career_agent.services.postings import PostingCapture, PostingService
from career_agent.services.profile import ProfileService
from career_agent.services.recovery import RecoveryService
from career_agent.services.reset import ResetScope, ResetService
from career_agent.services.submissions import (
    BeginSubmissionRequest,
    EmployerConfirmation,
    ObservedEvidence,
    SubmissionService,
)

app = typer.Typer(
    name="career",
    help="Manage a local-first career application workspace.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
import_commands = typer.Typer(help="Preview and apply copy-first career evidence imports.")
profile_commands = typer.Typer(help="Review and confirm canonical profile facts.")
opportunity_commands = typer.Typer(help="Capture, deduplicate, and evaluate opportunities.")
application_commands = typer.Typer(help="Manage pursued applications and posting freshness.")
answer_commands = typer.Typer(help="Resolve and govern reusable application answers.")
release_commands = typer.Typer(help="Create and verify tamper-evident document releases.")
submission_commands = typer.Typer(help="Prepare, approve, and record submission attempts.")
pipeline_commands = typer.Typer(help="Build disposable views from authoritative state.")
migrate_commands = typer.Typer(help="Preview and apply copy-first schema migrations.")
reset_commands = typer.Typer(help="Preview and apply exact local reset scopes.")
app.add_typer(import_commands, name="import")
app.add_typer(profile_commands, name="profile")
app.add_typer(opportunity_commands, name="opportunity")
app.add_typer(application_commands, name="application")
app.add_typer(answer_commands, name="answer")
app.add_typer(release_commands, name="release")
app.add_typer(submission_commands, name="submission")
app.add_typer(pipeline_commands, name="pipeline")
app.add_typer(migrate_commands, name="migrate")
app.add_typer(reset_commands, name="reset")

_EXIT_CODES = {
    ErrorCode.INVALID_INPUT: 2,
    ErrorCode.NOT_READY: 3,
    ErrorCode.CONFLICT: 4,
    ErrorCode.INTEGRITY_ERROR: 5,
    ErrorCode.APPROVAL_REQUIRED: 6,
    ErrorCode.UNSAFE_PATH: 7,
}


def _emit(data: Any, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps({"ok": True, "data": data, "error": None}, sort_keys=True))
    else:
        typer.echo(json.dumps(data, indent=2, sort_keys=True))


def _fail(error: CareerError, *, json_output: bool) -> Never:
    payload = {
        "code": error.code.value,
        "message": redact_text(error.message),
        "details": sanitize(error.details),
    }
    if json_output:
        typer.echo(json.dumps({"ok": False, "data": None, "error": payload}, sort_keys=True))
    else:
        typer.echo(f"Error [{error.code.value}]: {redact_text(error.message)}", err=True)
    raise typer.Exit(_EXIT_CODES[error.code])


@app.callback()
def main(context: typer.Context) -> None:
    """Manage a local-first career application workspace."""

    root = workspace_root()
    recovery = RecoveryService(root).recover()
    cleanup_data: dict[str, object] = {"plan_digest": None, "deleted_paths": []}
    if context.invoked_subcommand != "cleanup":
        cleanup_service = CleanupService(root)
        cleanup_plan = cleanup_service.plan()
        cleanup_result = (
            cleanup_service.apply(cleanup_plan.plan_digest) if cleanup_plan.items else None
        )
        cleanup_data = {
            "plan_digest": cleanup_plan.plan_digest,
            "deleted_paths": (
                list(cleanup_result.deleted_paths) if cleanup_result is not None else []
            ),
        }
    context.obj = {"recovery": recovery, "cleanup": cleanup_data}


@app.command()
def doctor(
    context: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Report local runtime and capability readiness."""

    try:
        data = doctor_report()
        startup = context.obj
        data["recovery"] = startup["recovery"].model_dump(mode="json")
        data["cleanup"] = startup["cleanup"]
    except CareerError as error:
        _fail(error, json_output=json_output)
    if json_output:
        typer.echo(json.dumps({"ok": True, "data": data, "error": None}, sort_keys=True))
        return

    typer.echo(f"Workspace: {data['workspace_path']}")
    typer.echo(f"Python: {data['python_version']}")
    typer.echo(f"Platform: {data['platform']}")


@pipeline_commands.command("build")
def pipeline_build(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Regenerate the disposable Markdown pipeline from governed state."""

    try:
        root = workspace_root()
        path = write_pipeline(root)
        result = {"path": path.relative_to(root).as_posix()}
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result, json_output=json_output)


@app.command("cleanup")
def cleanup_workspace(
    apply_digest: Annotated[
        str | None,
        typer.Option("--apply", help="Apply one previously previewed cleanup digest."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Preview disposable-run cleanup, or apply an unchanged preview."""

    try:
        service = CleanupService(workspace_root())
        result = service.apply(apply_digest) if apply_digest else service.plan()
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result.model_dump(mode="json"), json_output=json_output)


@migrate_commands.command("plan")
def migrate_plan(
    target_version: Annotated[int, typer.Option("--target-version")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Preview a copy-first schema migration and legacy ambiguity inventory."""

    try:
        plan = MigrationService(workspace_root()).plan(target_version=target_version)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(plan.model_dump(mode="json"), json_output=json_output)


@migrate_commands.command("apply")
def migrate_apply(
    plan_digest: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Apply one unchanged migration plan with a recoverable backup."""

    try:
        result = MigrationService(workspace_root()).apply(plan_digest)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result.model_dump(mode="json"), json_output=json_output)


@reset_commands.command("preview")
def reset_preview(
    scopes: Annotated[
        list[ResetScope],
        typer.Option("--scope", help="Exact reset scope; repeat only for compatible scopes."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Preview exact local deletion targets without deleting anything."""

    try:
        plan = ResetService(workspace_root()).plan(frozenset(scopes))
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(plan.model_dump(mode="json"), json_output=json_output)


@reset_commands.command("apply")
def reset_apply(
    plan_digest: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Apply one unchanged reset preview digest."""

    try:
        result = ResetService(workspace_root()).apply(plan_digest)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result.model_dump(mode="json"), json_output=json_output)


@import_commands.command("preview")
def import_preview(
    sources: Annotated[list[Path], typer.Argument(help="Files or directories to inspect.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Stage a non-governed import plan without changing profile or resources."""

    try:
        preview = ProfileService(workspace_root()).preview_import(sources)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(preview.model_dump(mode="json"), json_output=json_output)


@import_commands.command("apply")
def import_apply(
    run_id: Annotated[str, typer.Argument(help="Preview run ID to apply.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Preserve previewed originals and add their proposals to the profile."""

    try:
        result = ProfileService(workspace_root()).apply_import(run_id)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result.model_dump(mode="json"), json_output=json_output)


@profile_commands.command("conflicts")
def profile_conflicts(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """List unresolved profile fact conflicts."""

    try:
        conflicts = [
            conflict.model_dump(mode="json")
            for conflict in ProfileService(workspace_root()).load_state().conflicts
            if conflict.resolved_fact_id is None
        ]
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(conflicts, json_output=json_output)


@profile_commands.command("confirm")
def profile_confirm(
    fact_id: Annotated[str, typer.Argument(help="Proposed stable fact ID.")],
    value_text: Annotated[str, typer.Option("--value", help="JSON value to confirm.")],
    source_ids: Annotated[
        list[str],
        typer.Option("--source-id", help="Evidence source ID; repeat for multiple sources."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Confirm one exact proposal and its evidence references."""

    try:
        try:
            value = json.loads(value_text)
        except json.JSONDecodeError as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "--value must be valid JSON",
            ) from error
        fact = ProfileService(workspace_root()).confirm_fact(fact_id, value, source_ids)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(fact.model_dump(mode="json"), json_output=json_output)


@opportunity_commands.command("add")
def opportunity_add(
    company: Annotated[str, typer.Option("--company")],
    title: Annotated[str, typer.Option("--title")],
    location: Annotated[str, typer.Option("--location")],
    url: Annotated[str, typer.Option("--url")],
    posting: Annotated[Path, typer.Option("--posting")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    posting_complete: Annotated[bool, typer.Option("--posting-complete")] = False,
    requisition_id: Annotated[str | None, typer.Option("--requisition-id")] = None,
    deadline_text: Annotated[str | None, typer.Option("--deadline")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Capture a lightweight opportunity without creating an application."""

    try:
        try:
            posting_text = posting.read_text()
            deadline = date.fromisoformat(deadline_text) if deadline_text else None
            capture = OpportunityCapture(
                company=company,
                title=title,
                location=location,
                url=url,
                captured_at=datetime.now(UTC),
                posting_text=posting_text,
                posting_complete=posting_complete,
                requisition_id=requisition_id,
                deadline=deadline,
            )
        except (OSError, ValueError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Opportunity capture input is invalid",
                {"posting": str(posting)},
            ) from error
        opportunity = OpportunityService(workspace_root()).add(
            capture,
            idempotency_key=idempotency_key,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(opportunity.model_dump(mode="json"), json_output=json_output)


@opportunity_commands.command("list")
def opportunity_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """List active lightweight opportunities."""

    try:
        opportunities = [
            item.model_dump(mode="json") for item in OpportunityService(workspace_root()).list()
        ]
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(opportunities, json_output=json_output)


@opportunity_commands.command("merge")
def opportunity_merge(
    primary_id: Annotated[str, typer.Argument()],
    duplicate_id: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Merge two reviewed duplicate candidates while preserving snapshots."""

    try:
        record = OpportunityService(workspace_root()).merge(primary_id, duplicate_id)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(record.model_dump(mode="json"), json_output=json_output)


@opportunity_commands.command("unmerge")
def opportunity_unmerge(
    merge_id: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Restore both immutable opportunity snapshots from a merge record."""

    try:
        restored = OpportunityService(workspace_root()).unmerge(merge_id)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit([item.model_dump(mode="json") for item in restored], json_output=json_output)


@opportunity_commands.command("evaluate")
def opportunity_evaluate(
    opportunity_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Validate evidence findings and compute the governed fit score."""

    try:
        try:
            draft = EvaluationDraft.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Evaluation input is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        evaluation = EvaluationService(workspace_root()).evaluate(
            opportunity_id,
            draft,
            idempotency_key=idempotency_key,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(evaluation.model_dump(mode="json"), json_output=json_output)


@opportunity_commands.command("pursue")
def opportunity_pursue(
    opportunity_id: Annotated[str, typer.Argument()],
    idempotency_key: Annotated[str, typer.Option("--idempotency-key")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Create or return the single application owned by an opportunity."""

    try:
        application = ApplicationService(workspace_root()).create_from_opportunity(
            opportunity_id,
            idempotency_key,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(application.model_dump(mode="json"), json_output=json_output)


@application_commands.command("show")
def application_show(
    application_id: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Show one application manifest."""

    try:
        application = ApplicationService(workspace_root()).load(application_id)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(application.model_dump(mode="json"), json_output=json_output)


@application_commands.command("transition")
def application_transition(
    application_id: Annotated[str, typer.Argument()],
    target: Annotated[ApplicationStage, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Apply one validated application lifecycle transition."""

    try:
        application = ApplicationService(workspace_root()).transition(
            application_id,
            target,
            reason,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(application.model_dump(mode="json"), json_output=json_output)


@application_commands.command("posting-check")
def application_posting_check(
    application_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Capture a posting, compare it with the prior basis, and apply freshness."""

    try:
        try:
            capture = PostingCapture.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Posting freshness input is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        root = workspace_root()
        applications = ApplicationService(root)
        before = applications.load(application_id)
        previous_id = before.current_posting_snapshot_id
        if previous_id is None:
            raise CareerError(
                ErrorCode.INTEGRITY_ERROR,
                "Application has no current posting snapshot",
                {"application_id": application_id},
            )
        postings = PostingService(root)
        previous = postings.load(application_id, previous_id)
        snapshot = postings.capture(application_id, capture)
        change_set = postings.compare(previous, snapshot)
        application = postings.apply_freshness(application_id, change_set)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(
        {
            "snapshot": snapshot.model_dump(mode="json"),
            "change_set": change_set.model_dump(mode="json"),
            "application": application.model_dump(mode="json"),
        },
        json_output=json_output,
    )


@answer_commands.command("set")
def answer_set(
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Persist one policy-qualified user answer."""

    try:
        try:
            command = SetAnswerCommand.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Answer input is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        answer = AnswerService(workspace_root()).set(command)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(answer.model_dump(mode="json"), json_output=json_output)


@answer_commands.command("resolve")
def answer_resolve(
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Resolve wording to a scope-qualified reusable answer."""

    try:
        try:
            question = QuestionContext.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Question context is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        resolution = AnswerService(workspace_root()).resolve(question)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(resolution.model_dump(mode="json"), json_output=json_output)


@answer_commands.command("list")
def answer_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """List reusable answers with sensitive values redacted."""

    try:
        answers = AnswerService(workspace_root()).list()
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(answers, json_output=json_output)


@answer_commands.command("export")
def answer_export(
    include_sensitive: Annotated[bool, typer.Option("--include-sensitive")] = False,
    owner_confirmed: Annotated[bool, typer.Option("--owner-confirmed")] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Export answers, requiring distinct confirmation for exact sensitive values."""

    try:
        answers = AnswerService(workspace_root()).export(
            include_sensitive=include_sensitive,
            owner_confirmed=owner_confirmed,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(answers, json_output=json_output)


@answer_commands.command("delete")
def answer_delete(
    answer_id: Annotated[str, typer.Argument()],
    preview: Annotated[bool, typer.Option("--preview")] = False,
    preview_digest: Annotated[str | None, typer.Option("--preview-digest")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Preview or execute digest-bound answer deletion."""

    try:
        service = AnswerService(workspace_root())
        result: DeletionPreview | DeletionResult
        if preview and preview_digest is None:
            result = service.delete_preview(answer_id)
        elif not preview and preview_digest is not None:
            result = service.delete(answer_id, preview_digest)
        else:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Choose --preview or provide --preview-digest",
            )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result.model_dump(mode="json"), json_output=json_output)


@release_commands.command("create")
def release_create(
    application_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Create an append-only release from validated application drafts."""

    try:
        try:
            request = ReleaseRequest.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Release request is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        release = DocumentService(workspace_root()).create_release(application_id, request)
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(release.model_dump(mode="json"), json_output=json_output)


@release_commands.command("list")
def release_list(
    application_id: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """List application-owned document releases."""

    try:
        releases = [
            release.model_dump(mode="json")
            for release in DocumentService(workspace_root()).list(application_id)
        ]
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(releases, json_output=json_output)


@release_commands.command("verify")
def release_verify(
    application_id: Annotated[str, typer.Argument()],
    release_id: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Verify release and validation checksums before consequential use."""

    try:
        verification = DocumentService(workspace_root()).verify_release(
            application_id,
            release_id,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(verification.model_dump(mode="json"), json_output=json_output)


@submission_commands.command("prepare")
def submission_prepare(
    application_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Create the canonical, digest-bound final review payload."""

    try:
        try:
            request = PrepareSubmissionRequest.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Submission preparation request is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        service = PayloadService(workspace_root())
        payload = service.prepare(application_id, request)
        result = {
            "payload": payload.model_dump(mode="json"),
            "digest": f"sha256-v1:{service.digest(payload)}",
        }
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(result, json_output=json_output)


@submission_commands.command("approve")
def submission_approve(
    application_id: Annotated[str, typer.Argument()],
    submission_id: Annotated[str, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Request final approval through an attached interactive terminal."""

    try:
        approval = ApprovalService(workspace_root()).approve(
            application_id,
            submission_id,
            InteractiveApprovalAuthority(),
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(approval.model_dump(mode="json"), json_output=json_output)


@submission_commands.command("begin")
def submission_begin(
    application_id: Annotated[str, typer.Argument()],
    submission_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Consume one approval immediately before the irreversible portal action."""

    try:
        try:
            request = BeginSubmissionRequest.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Submission begin request is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        attempt = SubmissionService(workspace_root()).begin(
            application_id,
            submission_id,
            request.approval_id,
            observed_payload_digest=request.observed_payload_digest,
            browser_state_verified=request.browser_state_verified,
            browser_state_reference=request.browser_state_reference,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(attempt.model_dump(mode="json"), json_output=json_output)


@submission_commands.command("observe")
def submission_observe(
    application_id: Annotated[str, typer.Argument()],
    submission_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Record browser-observed evidence without claiming employer confirmation."""

    try:
        try:
            evidence = ObservedEvidence.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Observed evidence is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        attempt = SubmissionService(workspace_root()).observe(
            application_id,
            submission_id,
            evidence,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(attempt.model_dump(mode="json"), json_output=json_output)


@submission_commands.command("confirm")
def submission_confirm(
    application_id: Annotated[str, typer.Argument()],
    submission_id: Annotated[str, typer.Argument()],
    input_path: Annotated[Path, typer.Option("--input")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Record attributable employer confirmation evidence."""

    try:
        try:
            evidence = EmployerConfirmation.model_validate_json(input_path.read_text())
        except (OSError, ValidationError) as error:
            raise CareerError(
                ErrorCode.INVALID_INPUT,
                "Employer confirmation is unreadable or invalid",
                {"input": str(input_path)},
            ) from error
        attempt = SubmissionService(workspace_root()).confirm(
            application_id,
            submission_id,
            evidence,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(attempt.model_dump(mode="json"), json_output=json_output)


@submission_commands.command("resolve")
def submission_resolve(
    application_id: Annotated[str, typer.Argument()],
    submission_id: Annotated[str, typer.Argument()],
    resolution: Annotated[SubmissionResolution, typer.Argument()],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Resolve one uncertain attempt without creating a duplicate retry."""

    try:
        attempt = SubmissionService(workspace_root()).resolve_uncertain(
            application_id,
            submission_id,
            resolution,
        )
    except CareerError as error:
        _fail(error, json_output=json_output)
    _emit(attempt.model_dump(mode="json"), json_output=json_output)
