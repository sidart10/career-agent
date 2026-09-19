# 08 — Documents and Releases

Type: task
Status: resolved
Blocked by: 03, 04, 06

## Outcome

Confirmed profile facts and application requirements produce editable LaTeX drafts, validated PDFs, optional portal-required DOCX exports, and append-only tamper-evident releases whose claims, artifacts, checksums, and employer-facing upload copies are auditable.

## Requirement Contract

| Requirement | CLI | Persisted contract | Invariant / failure | Acceptance test |
|---|---|---|---|---|
| Canonical rendering | draft service, `career release create` | `RenderResult` | Missing TeX engine fails readiness; no silent install | `test_render.py` |
| Mechanical validation | `career release verify` | `ValidationReport` | Failed checks remain drafts | `test_pdf_validation.py` |
| Grounded release | `career release create|list` | `DocumentRelease` | Every claim has confirmed evidence and artifact checksum | `test_release.py`, `test_release_cli.py` |
| Professional upload copy | submission preparation consumer | `UploadArtifact` | Copy records source checksum and does not claim employer receipt | `test_release.py` |

## Files

- Create: `src/career_agent/documents/render.py`
- Create: `src/career_agent/documents/pdf_validation.py`
- Create: `src/career_agent/documents/layout_validation.py`
- Create: `src/career_agent/documents/release.py`
- Create: `src/career_agent/documents/filenames.py`
- Create: `templates/resume/default/`
- Create: `tests/fixtures/documents/`
- Create: `tests/unit/documents/test_render.py`
- Create: `tests/unit/documents/test_pdf_validation.py`
- Create: `tests/unit/documents/test_release.py`
- Create: `tests/contract/test_release_cli.py`

## Interfaces

```python
class DocumentService:
    def render_draft(self, application_id: str, draft: StructuredDocument) -> RenderResult: ...
    def validate(self, application_id: str, artifact: Path) -> ValidationReport: ...
    def create_release(self, application_id: str, request: ReleaseRequest) -> DocumentRelease: ...
    def prepare_upload_copy(self, release_id: str, artifact_type: ArtifactType) -> UploadArtifact: ...

class ValidationReport(BaseModel):
    passed: bool
    engine: str
    page_count: int
    required_fields: tuple[CheckResult, ...]
    placeholders: tuple[CheckResult, ...]
    layout: tuple[CheckResult, ...]
    ats_text_path: str
    logical_order: tuple[CheckResult, ...]
```

## Steps

- [ ] Port the upstream PDF and layout validation concepts with provenance comments while adapting all paths and output to V1 models; preserve raw ATS extraction separately from normalized comparison text.
- [ ] Create valid, unreadable, empty, placeholder-containing, footer-collision, stranded-heading, thin-page, wrong-contact, and illogical-text-order fixtures.
- [ ] Write failing tests proving compilation success alone cannot release a document and every approved claim references a confirmed fact ID or imported evidence locator.
- [ ] Run `uv run pytest tests/unit/documents -q` and confirm failure.
- [ ] Implement process execution with argument arrays, bounded timeouts, managed run directories, sanitized environment, and no shell interpolation.
- [ ] Implement `lualatex`/`xelatex` detection and fail document readiness when neither exists; never install system software.
- [ ] Implement the release gate for readability, required contact fields, placeholders, page constraints, layout signals, ATS text, logical order, source fact references, and artifact checksums.
- [ ] Implement fixed internal artifact names and sanitized `First_Last_Company_Role_Artifact` upload copies with collision-resistant suffixes and source-release checksums.
- [ ] Verify a direct edit to a release causes quarantine and invalidates every derived upload copy and approval reference.
- [ ] Run focused tests, the accumulated suite, Ruff, and mypy.
- [ ] Commit with `git commit -m "feat: render and validate tamper-evident document releases"`.

## Acceptance Criteria

- Failed validation cannot create a release.
- Every released claim resolves to confirmed evidence.
- Release bytes are checksum-verified at every consequential read.
- Upload-copy evidence states what local file was selected without claiming employer receipt.
- Temporary render artifacts are confined to the run directory.

## Comments

- 2026-09-18 — Implemented on `feature/generic-career-agent-v1` in commit `7731cd4`.
- RED evidence: renderer tests first failed because no document package existed; PDF checks then exposed compilation-only release, placeholder/contact/order/layout failures, and unconstrained draft paths; release tests exposed ungrounded claims, unsealed manifests, unchecked listing, validation-report tampering, non-OOXML ZIP acceptance, and crash-time idempotency rebinding.
- GREEN evidence: 20 focused render/validation/release/CLI tests and 233 accumulated tests pass; deterministic schema checking, Ruff, formatting, strict mypy, and diff checks all pass.
- Design note: canonical rendering detects `lualatex` then `xelatex`, uses a bounded argument-array process with shell escape disabled and a sanitized environment, confines intermediates to a managed run directory, preserves editable LaTeX drafts, and persists source/PDF checksums as render provenance. A PDF cannot release without matching provenance.
- Design note: the mechanical gate preserves raw ATS extraction separately from normalized comparison text and checks readability, required fields, placeholders, page count, thin pages, stranded headings, footer collisions, and logical section order. DOCX remains an optional portal format and must be a readable OOXML container.
- Design note: releases use application-local immutable identities, fixed internal names, passing validation-report checksums, confirmed fact or imported-source grounding, application locks, atomic writes, journal checkpoints, and a journal-sealed manifest. Consequential list, verify, replay, and upload-copy reads recheck release bytes.
- Design note: any artifact, report, or manifest checksum mismatch moves the affected file to application quarantine, records the incident, invalidates every derived upload record, and moves ready/approved applications back to preparing. Employer-facing copies use sanitized descriptive names plus a checksum suffix and explicitly record that employer receipt is unconfirmed.
