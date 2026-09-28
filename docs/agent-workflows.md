# Agent command reference

This page is for the agent, not a prerequisite for the person onboarding. Read project-root `career-rules.md` first. In the following syntax, `career` means the absolute project-local launcher:

- Unix: `bash "/absolute/project/scripts/career.sh"`
- PowerShell: `& "/absolute/project/scripts/career.ps1"`

These are syntax references, not copy-paste first-run commands. Replace uppercase argument labels with values returned by the actual operation. Do not type angle-bracket placeholders into a shell. Use `--help` to inspect an unfamiliar contract; do not infer command names from prose.

## Responses and paths

Successful JSON results contain `{"ok":true,"data":...,"error":null,"workspace":...}`. Read `data`, not top-level model fields. Errors have `ok:false`, a code and details; a zero exit code alone does not mean every diagnostic check passed.

Doctor's fields are in `data.capability_report`. Onboarding status fields are directly in `data`. Input paths supplied to `--input` or `--posting` should be absolute. Internal stored evidence paths are relative to the selected workspace. Application-relative draft paths are relative to the application's own directory.

Save agent-authored request files in the selected workspace's inbox, not tracked project docs. Show the human-readable proposal first when human confirmation is required. Never overwrite an existing user file to stage a request.

## First-run and evidence commands

```text
career workspace show --json
career init --json
career workspace select WORKSPACE_PATH --json
career doctor --json
career onboarding status --json
career import preview SOURCE_PATH --json
career import apply RETURNED_RUN_ID --source-id RETURNED_SOURCE_ID --json
career privacy status --json
career privacy acknowledge --policy-version REPORTED_VERSION --provider ACTUAL_PROVIDER --json
career import inspect RETURNED_SOURCE_ID --json
career profile propose --input PROPOSAL_FILE --json
career profile list --json
career profile confirm RETURNED_FACT_ID --value JSON_ENCODED_VALUE --source-id RETURNED_SOURCE_ID --json
career profile reject RETURNED_FACT_ID --reason USER_REASON --json
career preferences set --input PREFERENCES_FILE --json
```

Multiple `--source-id` options select multiple import sources or confirmation sources. Omitting the import selection attempts all sources, including failed ones. Inspect failures before applying.

Before reading personal text into the model, explain the actual host/provider and obtain acknowledgement. Set the process environment variable `CAREER_MODEL_PROVIDER` consistently on subsequent invocations; an acknowledgement for one declared provider is not consent for another. Do not store secrets there.

For a string value, confirmation needs JSON quotes. For example, the literal shell argument for the synthetic string Alex Doe is `'"Alex Doe"'` on a Unix shell. Prefer the host's structured argument API where available. Confirm only the exact value and source IDs returned by a supported proposal.

### Proposal request

The [ProfileProposalBatch schema](../src/career_agent/resources/schemas/profile-proposal-batch.schema.json) is authoritative. The wrapper is `proposals`, not a raw array. Each entry has `key`, `value`, and one `source`.

To construct a request from `import inspect`:
1. Copy the source's `source_id`, `checksum` into `source_checksum`, `normalized_text_checksum`, `extractor`, and `extractor_version`.
2. Choose a real returned block; copy its `block_id` and `page_number` (null for a nonpaged block).
3. Choose absolute character offsets into the full returned normalized text, bounded by the block's `start_offset` and `end_offset`; do not restart at zero for each block/page. Set `exact_text = text[start_offset:end_offset]`. Offsets are Python Unicode-character indices, not UTF-8 byte offsets.
4. Set a fact key and value supported by that passage. Evidence-span validation proves provenance, not semantic truth; the user must review the claim.
5. Wrap the entries as `{"proposals":[...]}` and validate through `profile propose`.

Never calculate offsets against a separately extracted copy or invent checksums. Returned fact IDs are assigned by the engine; they do not belong in this input.

### Preferences example

This is a schema-valid **synthetic example**, not defaults for a real user. Use their actual confirmed choices. Omitted optional fields are reported as defaulted.

```json
{
  "target_roles": ["Product Manager"],
  "locations": ["Remote"],
  "work_modes": ["remote"],
  "relocation": "not_willing",
  "hard_exclusions": ["Unpaid roles"],
  "weighted_priorities": [
    {"name": "Meaningful product ownership", "weight": 5}
  ]
}
```

See [PreferenceInput](../src/career_agent/resources/schemas/preference-input.schema.json). Priority weights are integers 1–5, not a dictionary of percentages. Unknown fields are rejected.

## Preparation commands

```text
career opportunity add --company COMPANY --title TITLE --location LOCATION --url URL --posting ABSOLUTE_TEXT_FILE --posting-complete --idempotency-key STABLE_KEY --json
career opportunity list --json
career opportunity evaluate OPPORTUNITY_ID --input EVALUATION_FILE --idempotency-key STABLE_KEY --json
career opportunity pursue OPPORTUNITY_ID --idempotency-key STABLE_KEY --json
career application show APPLICATION_ID --json
career release create APPLICATION_ID --input RELEASE_REQUEST_FILE --json
career release upload-copy APPLICATION_ID RELEASE_ID --artifact-type resume_pdf --json
career pipeline build --json
```

Use `--posting-complete` only for a full capture. Reuse an idempotency key for a retry of the same operation, not different content. Take the actual `application_id` from the returned manifest. Its directory is `applications/APPLICATION_ID/` inside the selected workspace and ordinary drafts live in its `drafts/` child. Verify the directory and reject symlink escapes before writing. Do not synthesize IDs or use company names as folder names.

Input contracts:
- [EvaluationDraft](../src/career_agent/resources/schemas/evaluation-draft.schema.json): evidence-backed scoring; profile references use confirmed fact IDs, posting evidence uses exact spans.
- [PostingCapture](../src/career_agent/resources/schemas/posting-capture.schema.json): refreshed posting evidence.
- [ReleaseRequest](../src/career_agent/resources/schemas/release-request.schema.json): artifacts, claim references, and idempotency key.
- [SetAnswerCommand](../src/career_agent/resources/schemas/set-answer-command.schema.json) and [QuestionContext](../src/career_agent/resources/schemas/question-context.schema.json): retention/reuse choices for actual questions.

A schema-valid request is not necessarily semantically acceptable: services verify source identity, evidence, document claims, and state. Do not weaken those checks.

## Experimental submission contracts

Only after an explicit request and actual portal observation, inspect `career submission --help` and the relevant subcommand help. Preparation-only work should stop before this section.

- [PrepareSubmissionRequest](../src/career_agent/resources/schemas/prepare-submission-request.schema.json)
- [BeginSubmissionRequest](../src/career_agent/resources/schemas/begin-submission-request.schema.json)
- [ObservedEvidence](../src/career_agent/resources/schemas/observed-evidence.schema.json)
- [EmployerConfirmation](../src/career_agent/resources/schemas/employer-confirmation.schema.json)

Payload preparation is not approval. Never provide a model-authored approval boolean or treat a browser click as employer confirmation. See [evidence and approval](evidence-and-approval.md).

## Maintenance

Use `migrate plan --target-version 2 --json` for legacy layout migration. For a moved legacy workspace, add its explicitly known `--former-root`. Applying uses `migrate apply RETURNED_DIGEST --json`. There is no `--plan-id` option.

Read the plan, show effects/backups, and obtain approval. Recovery, cleanup, and reset have separate help and digest-bound contracts; never use them as automatic installation repair.
