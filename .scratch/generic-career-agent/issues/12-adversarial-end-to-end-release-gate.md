# 12 — Adversarial End-to-End Release Gate

Type: task
Status: resolved
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11

## Outcome

A configurable local fake employer portal and synthetic candidate prove the complete V1 journey, uncertain submission handling, crash recovery, trust boundaries, and platform installation without contacting a real employer or persisting real personal information.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Complete reliable loop | all V1 commands through skills | complete synthetic workspace | Clean-clone journey ends confirmed with reproducible pipeline | `test_happy_path.py`, `test_clean_clone.py` |
| Uncertain external outcome | submission commands | uncertain attempt plus retained evidence | No automatic retry or fabricated success | `test_uncertain_submission.py` |
| Dynamic/adversarial portal | same flow | invalidated approval/evidence limitation | Conditional mutation, rejection, expiry, and delay fail safely | `test_adversarial_portal.py` |
| Recovery at every boundary | rerun interrupted command | journal/checkpoint chain | No duplicate IDs, releases, approvals, or external receipt | `test_crash_matrix.py` |
| Untrusted-content boundary | all ingestion surfaces | sanitized records | Content cannot change paths, policy, permissions, or executable config | `test_trust_boundaries.py` |

## Files

- Create: `tests/e2e/fake_portal/app.py`
- Create: `tests/e2e/fake_portal/scenarios.py`
- Create: `tests/e2e/fake_portal/templates/`
- Create: `tests/e2e/test_happy_path.py`
- Create: `tests/e2e/test_uncertain_submission.py`
- Create: `tests/e2e/test_adversarial_portal.py`
- Create: `tests/e2e/test_crash_matrix.py`
- Create: `tests/e2e/test_trust_boundaries.py`
- Create: `tests/e2e/test_clean_clone.py`
- Create: `tests/fixtures/candidate/`
- Create: `docs/manual-portal-compatibility.md`
- Create: `.github/workflows/ci.yml`

## Interfaces

```python
class PortalScenario(StrEnum):
    HAPPY_PATH = "happy_path"
    CONDITIONAL_AFTER_APPROVAL = "conditional_after_approval"
    NORMALIZE_VALUE = "normalize_value"
    REJECT_UPLOAD = "reject_upload"
    SESSION_EXPIRES = "session_expires"
    DELAYED_SUBMIT = "delayed_submit"
    DUPLICATE_CLICK = "duplicate_click"
    PARTIAL_SUCCESS = "partial_success"
    NO_CONFIRMATION = "no_confirmation"
    NETWORK_FAIL_AFTER_SUBMIT = "network_fail_after_submit"

class FakePortalReceipt(BaseModel):
    receipt_id: str
    echoed_fields: dict[str, str]
    received_file_digests: dict[str, str]
    submitted_at: datetime
```

## Steps

- [x] Implement a local-only FastAPI portal bound to loopback with deterministic scenario selection, account/attestation gates, conditional questions, upload digesting, idempotency tokens, delayed responses, and receipts that may intentionally omit payload details.
- [x] Create a synthetic candidate, imported evidence set, two duplicate-like postings with distinct requisitions, a valid LaTeX document, low-risk and high-risk questions, and no real names, emails, employers, or credentials.
- [x] Write the happy-path test from clean workspace initialization through import, fact confirmation, opportunity capture, authoritative evaluation, application creation, document release, answer capture, browser filling, trusted test approval authority, submission, confirmation, and pipeline regeneration.
- [x] Write the uncertain-path test where the portal accepts the application and the connection fails before confirmation; assert one external receipt, local `uncertain`, retained evidence, and rejection of an automatic retry.
- [x] Parameterize adversarial tests over every `PortalScenario`; assert payload mutations invalidate approval, rejected uploads cannot enter the payload, duplicate clicks remain idempotent, and missing receipt details lower evidence level.
- [x] Inject instructions into posting text, email-like fixtures, imported documents, filenames, form labels, and confirmation pages; assert no change to managed paths, approval policy, tool permissions, or executable configuration.
- [x] Add failpoints before and after every journal checkpoint and external-action boundary; for each failpoint, restart and assert old-valid or new-valid state with no duplicate ID, release, approval, or submission attempt.
- [x] Add clean-clone CI jobs for Linux, macOS, and Windows that install, run doctor against fixture capabilities, execute non-LaTeX unit/contract suites, provision or detect the declared TeX engine for document/e2e jobs, and run the complete release gate.
- [x] Write `docs/manual-portal-compatibility.md` as a non-submitting checklist for Workday-style, Greenhouse-style, Lever-style, and custom multi-page portals; prohibit real uploads and treat results as observations rather than automated release evidence.
- [x] Run `uv run pytest tests/e2e -q`, `uv run pytest -q`, Ruff, mypy, Unix installer tests, PowerShell installer tests, and every CI matrix job.
- [x] Commit with `git commit -m "test: add adversarial career application release gate"`.

## Acceptance Criteria

- Happy and uncertain journeys pass from a clean clone on the declared platform matrix.
- No automated test contacts a real employer, inbox, or production Notion workspace.
- Every adversarial scenario has an executable assertion, not a prose-only warning.
- Crash replay never duplicates an application, release, approval, or external submission.
- The release gate reports evidence limitations instead of upgrading observation into employer confirmation.

## Comments

- 2026-09-18 — Implemented the adversarial release gate in `c0fdd93`, hardened it after whole-branch self-review in `ed13ba4`, and fixed the hosted Linux/Windows findings through `5b1cc3f`.
- Local evidence: `uv lock --check`, 311 accumulated pytest cases (including a forced non-UTF-8 locale), Ruff lint/format, mypy over 55 source files, schema export verification, and `git diff --check` all pass on macOS. The 21 end-to-end cases include the CLI-driven happy/uncertain journeys, every fake-portal scenario, trust-boundary fixtures, clean-source installation, and consequential crash replay.
- Review fixes: added the missing idempotent `career init`; changed the primary journey to use public CLI contracts; made clean-source installation PowerShell/mirror-aware on Windows; made CI fail closed on doctor readiness; exported platform TeX paths; added polarity-change, email-like, confirmation-page, and external-receipt crash assertions.
- Hosted evidence: GitHub Actions run [35426808064](https://github.com/the-sid-dani/career-agent/actions/runs/35426808064) passed quality plus Ubuntu, macOS, and Windows on `5b1cc3f`. Windows passed 287 unit/contract tests with 3 intentional Unix-only skips, all 21 end-to-end cases, and the native PowerShell mirror-install contract. Ubuntu and macOS passed 290 unit/contract tests and all 21 end-to-end cases.
- Hosted hardening: Linux installs the required LaTeX base format, doctor tests isolate ambient runtime configuration, governed text I/O is explicitly UTF-8, Unix installer tests are host-scoped, and workspace locks combine stable in-process serialization with the cross-process platform lock.
- Release decision: all declared V1 gates pass; Ticket 12 is resolved and the Generic Career Agent V1 release boundary is complete.
