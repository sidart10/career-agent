# 01 — Foundation and Provenance

Type: task
Status: resolved
Blocked by: none

## Outcome

A clean Python package installs through `uv`, exposes `career --help` and `career doctor`, exports stable error codes, and records the pinned upstream baseline plus a reviewed preserve/redesign/defer/remove capability matrix.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Installable V1 package | `career --help` | `pyproject.toml`, `uv.lock` | Unsupported Python exits with a stable error | `test_cli_baseline.py` |
| Actionable diagnostics | `career doctor --json` | Response envelope | Missing required capability makes readiness false | `test_cli_baseline.py` |
| Pinned upstream provenance | none | `provenance/upstream.json` | Commit and capability dispositions are immutable inputs | `test_upstream_provenance.py` |

## Files

- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `src/career_agent/__init__.py`
- Create: `src/career_agent/cli.py`
- Create: `src/career_agent/config.py`
- Create: `src/career_agent/errors.py`
- Create: `provenance/upstream.json`
- Create: `docs/upstream-parity.md`
- Create: `tests/contract/test_cli_baseline.py`
- Create: `tests/contract/test_upstream_provenance.py`

## Interfaces

```python
class ErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    NOT_READY = "not_ready"
    CONFLICT = "conflict"
    INTEGRITY_ERROR = "integrity_error"
    APPROVAL_REQUIRED = "approval_required"
    UNSAFE_PATH = "unsafe_path"

class CareerError(Exception):
    code: ErrorCode
    message: str
    details: dict[str, object]

def workspace_root(explicit: Path | None = None) -> Path: ...
def doctor_report() -> dict[str, object]: ...
```

The console entry point is `career = "career_agent.cli:app"`. All JSON output uses `{ "ok": bool, "data": object | null, "error": object | null }`.

## Steps

- [ ] Create `pyproject.toml` for Python `>=3.11,<3.14`, a `src/` package, Ruff, mypy strict mode, pytest, and the dependencies locked in the implementation plan.
- [ ] Write `test_cli_baseline.py` asserting `career --help` exits 0, `career doctor --json` parses as the response envelope, and an invalid command exits nonzero without a traceback.
- [ ] Run `uv run pytest tests/contract/test_cli_baseline.py -q` and confirm failure because the package and command do not exist.
- [ ] Implement the Typer root app, response envelope, typed errors, workspace discovery, and baseline doctor report containing Python version, platform, workspace path, and tracked capability names.
- [ ] Create `provenance/upstream.json` with repository URL, commit `27eb57ae93498cddba6268d3dd84d721daa1fa0c`, audit date `2026-09-15`, and no candidate data.
- [ ] Create `docs/upstream-parity.md` with one row for every workflow and deterministic tool named in `upstream-ai-job-search-audit.md`; classify each row as `preserve_v1`, `redesign_v1`, `defer`, or `remove`, and cite its owning issue.
- [ ] Write `test_upstream_provenance.py` to validate the commit hash, permitted disposition values, unique capability names, and the absence of absolute candidate paths or personal profile data.
- [ ] Run `uv lock`, `uv run ruff check .`, `uv run mypy src`, and `uv run pytest tests/contract/test_cli_baseline.py tests/contract/test_upstream_provenance.py -q`.
- [ ] Commit with `git commit -m "chore: establish career agent package and provenance"`.

## Acceptance Criteria

- A clean environment can run `uv sync` and `uv run career doctor --json`.
- The doctor envelope and exit-code behavior are contract-tested.
- Every upstream capability has an explicit V1 disposition and owner.
- The pinned upstream commit is machine-readable and contains no personal data.

## Comments

- 2026-09-18 — Implemented on `feature/generic-career-agent-v1` in commit `3f35c16`.
- RED evidence: CLI contract collection failed with `ModuleNotFoundError: career_agent`; provenance contracts failed because `provenance/upstream.json` did not exist.
- GREEN evidence: `uv lock && uv run ruff check . && uv run mypy src && uv run pytest tests/contract/test_cli_baseline.py tests/contract/test_upstream_provenance.py -q` completed with Ruff clean, mypy clean across four source files, and 7 tests passing.
- Scope preserved: only the package foundation, baseline doctor, stable errors, upstream inventory, and parity matrix shipped. The pre-existing untracked `README.md` and upstream audit were not included in the implementation commit.
