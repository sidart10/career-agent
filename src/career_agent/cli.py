"""Command-line entry point for governed career workspace operations."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from career_agent.config import doctor_report

app = typer.Typer(
    name="career",
    help="Manage a local-first career application workspace.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


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
