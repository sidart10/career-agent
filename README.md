# Career Agent

A personal job-search assistant you use through **Codex or Claude Code**, with your evidence and work saved in ordinary files. It helps you review your career history, evaluate jobs, prepare application documents, and track applications.

Career Agent is a **development preview**, not a standalone chat app or an unattended job-application bot. You need a local agent host that can read files and run commands. Live portal submission is experimental; preparing documents does not require a browser.

## Start here

1. [Download the project ZIP](https://github.com/sidart10/career-agent/archive/refs/heads/main.zip) and extract it, or clone this repository. Keep the extracted folder somewhere you can find again.
2. Open **that folder** as a local project in Codex or Claude Code. For everyday use, use the same folder, not a new worktree or a cloud copy.
3. Say:

   > Help me set up my career agent. Keep my personal files in this project's workspace folder and walk me through onboarding.

The agent follows the instructions shipped with this project. It checks prerequisites, explains any installation needed, runs setup, and guides you through your profile. You should not need to write JSON or learn the internal commands.

Setup needs [uv](https://docs.astral.sh/uv/getting-started/installation/) and internet access to download Python and dependencies. Git is optional if you downloaded the ZIP. Your agent should ask before installing missing software. If your agent cannot run local commands, use the [installation guide](docs/installation.md).

## What onboarding does

- Shows you where your personal files will live: **`workspace/` inside this folder**, unless you already selected another workspace.
- Lets you add a résumé or career-history file to `workspace/inbox/`, or provide its location. If you have no résumé, the agent can help you write a career-history text file.
- Explains which model provider will receive personal text and asks for your consent before interpreting it.
- Proposes facts backed by exact passages. You confirm, correct, or reject them; conflicting facts need your choice.
- Captures your target roles, locations, and job-search preferences separately from evidence-backed facts.
- Tells you what is ready and what is still missing.

Read the [onboarding walkthrough](docs/onboarding.md). A successful installation is not the same as a completed profile, and neither authorizes an application submission.

## What you can ask

- “Import this résumé and show me what you learned before saving any facts.”
- “Help me decide which of these jobs fit my goals.”
- “Prepare a résumé and cover letter for this job. Do not submit anything.”
- “Show my applications and what needs attention.”
- “Resume my setup from where we stopped.”

Research and portal interaction depend on the tools available in your agent host. The system must say when it cannot browse, render a document, or submit. It must not invent career facts, claim unverified results, or silently send messages.

## How it works

The bundled skills tell the agent how to run career workflows. A small Python engine validates evidence, saves structured records, and records important operations for recovery. The agent uses project-local launchers; you do not need a global `career` command.

```text
career-agent/
├── workspace/          Your personal career workspace (ignored by Git)
│   ├── inbox/          Files you want to import
│   ├── profile/        Reviewed facts, preferences, and privacy acknowledgement
│   ├── resources/      Preserved source files and extracted evidence
│   ├── opportunities/  Jobs and evaluations
│   ├── applications/   Per-job drafts, document releases, and tracking
│   └── pipeline.md     Generated application overview
├── .agents/skills/     Canonical workflow instructions
├── .claude/skills/     Installer-managed Claude discovery links or mirrors
├── .career-agent/     Local runtime and workspace selection (ignored by Git)
├── scripts/           Installation and project-local launchers
├── src/career_agent/  Python engine; not your personal files
└── docs/              Detailed guides
```

Some folders and files appear only when their workflow first runs. You can edit original evidence and unreleased drafts. Ask the agent to change governed records; do not hand-edit journals, approvals, releases, or generated state.

## Privacy and safety

Files are local **plaintext**, not encrypted by this project. Git ignore prevents normal accidental additions; it does not stop force-adds, backups, cloud sync, or an already-tracked file from being shared. Back up the complete workspace privately.

Your agent host may send text to its configured model provider. Privacy acknowledgement records consent; it is not a network firewall. Never put passwords, API keys, or authentication tokens into career records.

## Guides and project status

- [Install, repair, move, and uninstall](docs/installation.md)
- [Onboarding](docs/onboarding.md) · [Your first application](docs/first-application.md)
- [Workspace and files](docs/workspace-and-state.md) · [Configuration](docs/configuration.md)
- [Security and privacy](docs/security-and-privacy.md) · [Troubleshooting](docs/troubleshooting.md)
- [All documentation](docs/README.md) · [Contributing](docs/contributing.md)

The current download follows `main`; it is not a tagged stable release. Cross-platform release validation and a project license decision remain release gates. See [compatibility](docs/compatibility.md) and [release operations](docs/release.md) for the evidence and limitations.
