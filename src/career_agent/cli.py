"""Command-line entry point for governed career workspace operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Never

import typer

from career_agent.config import doctor_report, workspace_root
from career_agent.errors import CareerError, ErrorCode
from career_agent.services.profile import ProfileService

app = typer.Typer(
    name="career",
    help="Manage a local-first career application workspace.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
import_commands = typer.Typer(help="Preview and apply copy-first career evidence imports.")
profile_commands = typer.Typer(help="Review and confirm canonical profile facts.")
app.add_typer(import_commands, name="import")
app.add_typer(profile_commands, name="profile")

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
        "message": error.message,
        "details": error.details,
    }
    if json_output:
        typer.echo(json.dumps({"ok": False, "data": None, "error": payload}, sort_keys=True))
    else:
        typer.echo(f"Error [{error.code.value}]: {error.message}", err=True)
    raise typer.Exit(_EXIT_CODES[error.code])


@app.callback()
def main() -> None:
    """Manage a local-first career application workspace."""


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit a machine-readable response envelope."),
    ] = False,
) -> None:
    """Report local runtime and capability readiness."""

    data = doctor_report()
    if json_output:
        typer.echo(json.dumps({"ok": True, "data": data, "error": None}, sort_keys=True))
        return

    typer.echo(f"Workspace: {data['workspace_path']}")
    typer.echo(f"Python: {data['python_version']}")
    typer.echo(f"Platform: {data['platform']}")


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
