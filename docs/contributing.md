# Contributing

Keep changes inside the documented 0.1 boundary and use synthetic candidate/employer data. Do not add private documents, credentials, portal recordings, or absolute user paths.

Set up with `uv sync --frozen`. During development, run the narrowest relevant tests and type checks. Before proposing a change, run:

```sh
uv run ruff check .
uv run ruff format --check scripts src tests
uv run mypy src
uv run python scripts/export_schemas.py --check
uv run pytest -q
uv build --no-sources
```

CI also runs the Agent Skills reference validator pinned to the audited `agentskills/agentskills` revision recorded in the workflow.

Public behavior goes through the `career` CLI. Persisted models are strict and versioned; update exported schemas with their code. Safety-critical skill rules must live within each skill directory, and all canonical skills remain under `.agents/skills`.

New recurring or metered model evaluations require an explicit cost decision. Do not enable network calls, real portals, or real submissions in CI.
