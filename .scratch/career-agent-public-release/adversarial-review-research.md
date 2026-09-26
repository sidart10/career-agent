# Adversarial Review: Career Agent Public-Release Plan

Reviewed: 2026-09-26
Plan reviewed: `spec.md` in this directory
Repository: `sidart10/career-agent` at `340c21b6bb45f242301edc0b471a5c8e7bbba6a3`

## Verdict

**No-go as written. Revise, then decompose.**

The plan has the right product boundary: a deterministic Python engine, thin Agent Skills, an external personal workspace, layered readiness, and public documentation. The conventional `src/career_agent` package is also the correct Python layout and should stay.

The plan is not implementation-ready because it currently combines two incompatible distribution promises, treats a nondeterministic model workflow as one deterministic cross-platform acceptance test, leaves the safety policy outside portable skill roots, and makes the license necessary for release while declaring the license decision out of scope. It also needs a stronger contract for resume evidence, model-data consent, workspace selection, skill/CLI version compatibility, and read-only diagnostics.

Recommended release posture: **private development now; supervised, repo-local early access after the P0 items pass.** Defer a broadly installable plugin and any production-ready browser-submission claim.

## What the plan gets right

- Keeping the engine under `src/career_agent` follows the standard Python `src` layout and cleanly separates importable code from repository tooling.
- Moving canonical Codex project skills to `.agents/skills` is current and correct for repo-local discovery. Codex scans `.agents/skills` from the working directory to the repository root and supports symlinked skill folders. [OpenAI: Build skills](https://developers.openai.com/codex/build-skills)
- Claude Code officially supports project skills under `.claude/skills`, personal skills under `~/.claude/skills`, external project directories through `--add-dir`, and symlinked skill directories. [Anthropic: Extend Claude with skills](https://code.claude.com/docs/en/skills)
- The proposed split between deterministic extraction and model interpretation is directionally right.
- The proposed core/document/submission readiness layers fix a real onboarding flaw.
- Externalizing personal career data from the source checkout is the right default.
- Limiting public claims to executable evidence is exactly the right release principle.

## P0 findings — block implementation or public early access

### P0.1 — The distribution model contradicts itself

The plan says the product is a source-clone early-access distribution, puts canonical skills in the repo-scoped `.agents/skills` surface, installs the CLI with `uv tool`, and describes the result as a generic product. These are not one installation boundary:

- `uv tool install .` installs the Python distribution and exposes its console entry point in an isolated tool environment; it does not install repo skills into Codex or Claude Code. `uv` also requires an explicit upgrade or reinstall flow for installed tools. [uv: Tools](https://docs.astral.sh/uv/concepts/tools/)
- Repo-scoped `.agents/skills` load only when Codex is launched inside that repository hierarchy. [OpenAI: Build skills](https://developers.openai.com/codex/build-skills)
- Repo-scoped `.claude/skills` likewise load in that repository; personal or plugin installation is the “works across projects” mechanism in Claude Code. [Anthropic: Extend Claude with skills](https://code.claude.com/docs/en/skills)
- OpenAI now explicitly describes direct skill folders as authoring/local-discovery surfaces and recommends plugins to distribute reusable skills or bundles beyond one repo. Its older `openai/skills` catalog is now deprecated in favor of `openai/plugins`. [OpenAI: Build skills](https://developers.openai.com/codex/build-skills), [openai/skills](https://github.com/openai/skills), [openai/plugins](https://github.com/openai/plugins)

**Required amendment:** define exactly one V0.1 contract:

1. Clone a tagged release.
2. Run the installer, which installs the `career` executable and verifies it on `PATH`.
3. Launch Codex or Claude Code from the clone.
4. Store all personal data outside the clone.

State plainly that V0.1 skills are repo-local. Defer “install once, use in any project,” marketplace distribution, and the universal OpenAI plugin directory. Add a later plugin milestone instead of pretending repo-local skills are the final generic distribution system.

### P0.2 — Safety policy is not portable with the skills

Every current skill says `Read ../../career-rules.md`. That happens to work from the current top-level `skills/<name>` layout, but after moving the canonical skill into `.agents/skills/<name>`, the same relative reference points at `.agents/career-rules.md`, not the repository-root file. A copied user-scope skill or plugin bundle has the same problem.

The Agent Skills specification treats each skill directory as the portable unit and recommends relative references within that skill, with supporting material under `references/`, `scripts/`, or `assets/`. [Agent Skills specification](https://agentskills.io/specification)

**Required amendment:** safety-critical instructions must be self-contained in each skill’s `SKILL.md` or its own `references/` directory. A repository-wide `career-rules.md` may remain useful context, but it cannot be the only carrier of rules needed to prevent unsafe state mutation or submission. If generated copies are used, validate them by checksum in CI and in the installer.

### P0.3 — The single acceptance seam is not actually one kind of test

The plan asks one journey to verify a clean installation, package resources, skill discovery, skill invocation, resume interpretation, state mutation, and fresh-session resumability on every supported operating system. That merges deterministic product testing with model behavior.

OpenAI’s current guidance treats skill evaluation as prompt evaluation: capture the agent run, trace, and artifacts; check whether the skill triggered and which commands ran; then combine deterministic checks with rubric-based grading. It recommends a small trigger/non-trigger prompt set and `codex exec --json` traces. [OpenAI: Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills)

**Required amendment:** create two release gates:

- **Deterministic product journey, every OS and every PR:** build/install the artifact, execute only the public CLI, use a checked-in synthetic extracted-text fixture or proposal fixture at the model boundary, and verify workspace state and resumability.
- **Model-driven skill eval, pinned runtime/model on release candidates and scheduled runs:** verify direct and implicit triggering, non-trigger cases, command sequence, evidence discipline, human gates, and output quality from captured traces.

Do not call a recorded proposal fixture a real model test, and do not make paid/networked agent runs a hidden requirement of the ordinary unit-test matrix.

### P0.4 — License and attribution are simultaneously required and out of scope

User story 7 and implementation decision 171 require a license and upstream attribution before describing the project as open source. Out-of-scope item 215 excludes selecting a license from this implementation. A public release cannot satisfy both.

The pinned upstream commit is MIT licensed and requires its copyright and permission notice to accompany copies or substantial portions. [Pinned upstream LICENSE](https://raw.githubusercontent.com/MadsLorentzen/ai-job-search/27eb57ae93498cddba6268d3dd84d721daa1fa0c/LICENSE)

**Required amendment:** make “release licensing and provenance” a blocking pre-release workstream, even if the final license choice remains a human decision. The likely low-friction path is an MIT project license plus preservation of Mads Lorentzen’s MIT notice in `THIRD_PARTY_NOTICES.md` for adapted portions. Confirm copied/adapted code and assets before publishing. This is a release requirement, not optional documentation polish.

### P0.5 — Resume interpretation lacks a complete evidence contract

“Exact evidence spans” is not precise enough. PDF and DOCX extraction can normalize whitespace, reorder columns, lose page boundaries, or return no text for scanned documents. A locator such as `resume.pdf#extracted-text` does not prove that a proposed value exists in the evidence.

**Required amendment:** define and test an immutable extraction record containing at minimum:

- source checksum and media type;
- extractor name/version and extraction timestamp;
- normalized extracted text checksum;
- page or block identity when available;
- start/end character offsets into the stored normalized text;
- the exact quoted substring expected at those offsets;
- extraction status, warnings, and OCR status.

The CLI must reject proposals whose offsets, substring, source ID, or checksums do not match. Scanned PDFs should be reported as “no text/OCR required” unless an explicit OCR dependency is supported. Resume content remains untrusted input and cannot issue agent instructions.

### P0.6 — Privacy consent comes too late

The plan promises a security/privacy document, but the actual risk happens when the skill sends extracted resume text and later application answers to the host model. “Local-first storage” does not mean local-only processing.

**Required amendment:** before the first model-assisted interpretation, onboarding must show:

- the confirmed local workspace path;
- that files are plaintext unless the operating system protects the disk;
- that selected resume text will be processed by the active model provider;
- that provider terms, retention, enterprise settings, and network policy apply;
- what is copied locally and what is not collected yet;
- an explicit continue/cancel choice recorded without storing sensitive prose in logs.

No background import or model call should precede this disclosure.

### P0.7 — `doctor` must be read-only; recovery must be explicit

The spec says diagnostics should avoid surprising governed mutations, but that is too weak. In the current CLI, the application callback runs recovery and cleanup before every command, including `doctor`; the current skill even states that Doctor performs recovery. Inspection and repair are therefore conflated.

**Required amendment:** make `career doctor` strictly read-only. Add separate, previewable commands such as `career recover plan`, `career recover apply <digest>`, and the existing cleanup plan/apply flow. If safe replay remains automatic for normal mutations, document the exact boundary and keep it out of diagnostic commands.

### P0.8 — The current baseline is not release-green

On 2026-09-26, `uv run pytest -q` produced **311 passed, 1 failed**. The failing concurrency allocator test failed again in isolation because a spawned worker did not exit within the test’s 10-second join. This may be a test-harness deadlock or timeout rather than a registry defect, but it is still a failed release signal.

The current wheel also omits skills, schemas, templates, installers, and policy files. The source distribution includes `.hypothesis` cache material and internal planning content. These observations validate the plan’s packaging concerns, but also mean the plan must not describe the current baseline as release-clean.

**Required amendment:** add a baseline-remediation gate before restructuring begins: repeatably green tests, classified flaky tests, wheel/sdist allowlists, and a clean-tree artifact build. The official `uv` release guidance recommends building with `uv build --no-sources` and testing installation outside the project. [uv: Building and publishing a package](https://docs.astral.sh/uv/guides/package/)

## P1 findings — resolve in the revised spec

### P1.1 — Persisted onboarding can create a second source of truth

The plan says onboarding is a persisted state machine while also saying authoritative state already lives in workspace markers, imports, profile proposals, preferences, answers, and capability reports.

**Amendment:** make onboarding status a deterministic projection over authoritative domain state plus explicit pending-operation records. Persist only information that cannot be derived, such as an acknowledged privacy disclosure or an intentionally paused human gate. Do not maintain a second mutable phase counter that can disagree with the underlying state.

### P1.2 — Workspace selection needs explicit precedence and identity protection

A mutable global “active workspace” pointer can silently route one person’s command to another person’s data. A stable path alone is insufficient.

**Amendment:** specify precedence as `--workspace` argument > `CAREER_WORKSPACE` > user config > platform default. Every resolved directory must contain a versioned marker with a stable workspace ID and `single_candidate` kind. Show the path and workspace ID before consequential operations. Configuration updates must be atomic, reject symlink/path traversal surprises, and never auto-switch because of the current directory.

Use `platformdirs` for config/data locations, but document the actual path per OS and confirm it during onboarding. `platformdirs` distinguishes user data, config, state, cache, and log directories and has OS-specific semantics. [platformdirs API](https://platformdirs.readthedocs.io/en/latest/api.html)

### P1.3 — The skill bundle and CLI need a compatibility handshake

Installing the CLI with `uv tool` copies code into an isolated environment, while the skills remain in a mutable clone or installer-managed mirror. A pulled skill can call a command that an older installed CLI does not support.

**Amendment:** add:

- `career --version`;
- an API/schema compatibility version;
- skill-bundle version metadata;
- a declared supported CLI version range per bundle;
- installer and Doctor checks that fail clearly on mismatch;
- documented update, rollback, and uninstall flows.

### P1.4 — The canonical skill location requires explicit Git rules

The current `.gitignore` ignores the entire `.agents/` tree. Simply moving canonical skills there will leave them untracked unless the ignore rules change.

**Amendment:** explicitly track `.agents/skills/career-*` and any required shared assets while keeping runtime state ignored. Generate Claude Code links/mirrors at install time rather than committing platform-sensitive links. Git for Windows disables real symlink support in many environments unless permissions or Developer Mode are available, so the mirror fallback is justified. [Git for Windows: Symbolic Links](https://gitforwindows.org/symbolic-links.html)

### P1.5 — Skill conformance needs standards validation and behavioral evals

The current names and frontmatter are broadly compatible with the Agent Skills standard, but portability must be enforced mechanically.

**Amendment:** run `skills-ref validate` for each canonical skill; verify names match directories; keep descriptions concise and distinct; test positive, indirect, incomplete, and negative trigger prompts; and make every required dependency or environment expectation explicit. The standard recommends `SKILL.md` under 500 lines and one-level-deep references. [Agent Skills specification](https://agentskills.io/specification)

### P1.6 — The installer contract needs rollback and ownership rules

The spec covers preservation of unrelated skills but not a failed partial update, downgrade, uninstall, or a missing source clone after CLI installation.

**Amendment:** make installation transactional and record every managed path, source revision, checksum, mode, CLI version, and previous managed version. Verify `career` resolves from a shell outside the clone. On failure, restore the previous managed state. Uninstall may remove only paths owned by the manifest.

### P1.7 — Package-resource rules need precise artifact tests

Python’s `importlib.resources` is designed for non-code resources that may not exist as normal filesystem paths; `as_file()` is needed when a consumer requires a real path. [Python: `importlib.resources`](https://docs.python.org/3/library/importlib.resources.html)

**Amendment:** declare which assets ship inside the Python package and access them through `importlib.resources.files()`. Artifact tests must inspect wheel and sdist allowlists, install each into a clean isolated environment, execute the console entry point outside the repo, and exercise every packaged template/schema. Do not package `.scratch`, caches, personal data, or user-owned untracked files.

### P1.8 — “One normal installation command” is underspecified

The user must already have Git and `uv`, and `uv` may need `uv tool update-shell` before the executable is visible. [uv: Tools](https://docs.astral.sh/uv/concepts/tools/)

**Amendment:** define exact macOS/Linux and PowerShell commands, supported Python versions, PATH verification, shell-restart behavior, update commands, and offline/failure behavior. Install from a tagged release, not an unspecified moving `main` branch.

### P1.9 — Model-assisted onboarding and skill evals have a cost surface

The plan has no model/provider or cost contract. A host subscription may cover interactive use, while automated skill evals can consume metered tokens and network access.

**Amendment:** document that the Python engine itself does not require a model API key, identify which host runtime supplies reasoning, and require explicit maintainer approval before enabling recurring paid evals. Record the pinned runtime/model and token/cost budget for release evals.

### P1.10 — Scope language still overreaches the executable public surface

The plan’s first-application documentation can be read as a supported end-to-end flow, but current document render/upload-copy services are not fully exposed through the CLI, and real browser submission is not proven.

**Amendment:** position V0.1 as a governed career setup, opportunity, ranking, and application-preparation framework. Label the portal phase experimental until the public CLI and host-browser handoff have their own evidence-backed release gate.

## P2 findings — quality and maintenance

- Generate CLI reference sections from Typer help and JSON schemas to reduce drift.
- Add `SECURITY.md`, `CONTRIBUTING.md`, `SUPPORT.md`, a changelog, a release checklist, and a compatibility matrix.
- Move historical specs/tickets out of an ambiguously live `.scratch` product surface or explicitly exclude them from distributions.
- Add synthetic conventional resumes with single-column, multi-column, DOCX, scanned-PDF, Unicode, date ambiguity, and adversarial prompt-injection cases.
- Add redacted support bundles and tests that prevent raw resume text or sensitive answers from entering diagnostics.
- Keep the seven skills small. OpenAI’s current guidance warns that large skill inventories can cause descriptions to be shortened or omitted from the initial context, so descriptions should have narrow triggers and negative boundaries. [OpenAI: Build skills](https://developers.openai.com/codex/build-skills)

## Recommended replacement decisions for the spec

1. **Release boundary:** V0.1 is supervised, repo-local early access for technically comfortable users. Real portal submission is experimental.
2. **Canonical code:** keep `src/career_agent`; include runtime resources beneath the package and use `importlib.resources`.
3. **Canonical skills:** commit repo-local Codex skills under `.agents/skills`. Generate Claude Code `.claude/skills` links or verified mirrors during install. Do not commit absolute links.
4. **Future distribution:** create a skills-only plugin milestone after repo-local V0.1. No MCP server is required merely to package skills.
5. **Skill safety:** required safety rules travel inside each skill. Repo-level AGENTS/CLAUDE files provide additional context, not the sole policy dependency.
6. **Install:** clone a tagged release, install the CLI with `uv tool`, verify PATH and version, install/verify the Claude discovery surface, and print the exact next command.
7. **Workspace:** external platform-specific default, explicit precedence, stable marker ID, one candidate, no CWD fallback, previewed copy-first migration.
8. **Onboarding:** derived resumable projection; privacy disclosure before model processing; phase-scoped readiness; proposal validation before confirmation.
9. **Evidence:** immutable extracted text with checksummed, offset-based spans; deterministic validator; OCR explicitly supported or explicitly unavailable.
10. **Diagnostics:** Doctor is read-only. Recovery, cleanup, migration, and reset remain separate preview/apply operations.
11. **Testing:** deterministic cross-platform product journey plus separate model-driven skill eval suite.
12. **Release:** license/attribution, security/privacy docs, green tests, clean artifact allowlists, tagged version, and truthful claims are blocking gates.

## Suggested implementation order

1. Resolve the P0 spec decisions and change status from `ready-for-agent` to `needs-info` or equivalent.
2. Record the V0.1 distribution/release boundary and the license/provenance decision.
3. Split the work into independently verifiable tickets:
   - packaging and artifact hygiene;
   - CLI installation/version handshake;
   - canonical skill migration and portable safety rules;
   - external workspace configuration;
   - read-only Doctor and explicit recovery;
   - evidence-span schema and proposal API;
   - preferences and derived onboarding status;
   - onboarding skill and privacy gate;
   - public docs/examples;
   - deterministic release journey;
   - model skill evals;
   - release/legal/security gates.
4. Run deterministic gates first; run paid/networked model evals only after the static and CLI layers pass.
5. Publish only after a clean machine can follow the tracked README without using internal Python services or hidden state.

## External references reviewed

- [OpenAI — Build skills](https://developers.openai.com/codex/build-skills)
- [OpenAI — Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [OpenAI — Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills)
- [OpenAI — current plugin examples](https://github.com/openai/plugins)
- [Anthropic — Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [Anthropic — public skills/plugin examples](https://github.com/anthropics/skills)
- [Agent Skills specification](https://agentskills.io/specification)
- [uv — Tools](https://docs.astral.sh/uv/concepts/tools/)
- [uv — Building and publishing a package](https://docs.astral.sh/uv/guides/package/)
- [Python — `importlib.resources`](https://docs.python.org/3/library/importlib.resources.html)
- [platformdirs API](https://platformdirs.readthedocs.io/en/latest/api.html)
- [Git for Windows — Symbolic Links](https://gitforwindows.org/symbolic-links.html)
- [Pinned upstream MIT license](https://raw.githubusercontent.com/MadsLorentzen/ai-job-search/27eb57ae93498cddba6268d3dd84d721daa1fa0c/LICENSE)
