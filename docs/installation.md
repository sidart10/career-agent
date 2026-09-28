# Install and repair Career Agent

## Recommended: let your agent guide setup

Download and extract the [project ZIP](https://github.com/sidart10/career-agent/archive/refs/heads/main.zip), or clone the repository. Open the resulting folder as a **local project** in Codex or Claude Code, then say:

> Help me set up my career agent. Keep my personal files in this project's workspace folder and walk me through onboarding.

The root instructions route first-run requests to the onboarding skill, including when the software has not been installed yet. The agent should check prerequisites, explain the plan, and ask before installing missing software. If the host cannot read files or execute commands locally, this setup route cannot run there.

This is a moving development preview. There is no release-tag placeholder to replace.

### Open the right folder

- **Codex:** add/open the extracted Career Agent folder as a local project and start a task there. The folder should contain `AGENTS.md`, `pyproject.toml`, and `.agents/skills/`. Do not open only `docs/` or your résumé folder. Codex normally detects skill changes automatically; restart Codex if they do not appear. You can also ask the agent to read `.agents/skills/career-onboard/SKILL.md` directly. See [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills).
- **Claude Code:** start your local session in that same folder. Review any workspace-trust prompt before accepting; do not bypass your organization's restrictions. After the installer first creates `.claude/skills/`, run `/reload-skills` if that directory did not exist when the session started. See [Claude's skill refresh rules](https://code.claude.com/docs/en/skills#edit-a-skill-during-a-session).

In either host, the agent needs permission to read this project and run local commands. If those permissions are unavailable, stop and resolve them with your administrator instead of repeatedly rerunning setup.

## Requirements

- A working local Codex or Claude Code session with file and command access. The host's account and model access are separate from Career Agent.
- [uv](https://docs.astral.sh/uv/getting-started/installation/), the Python environment manager. Use its official installation instructions for your system. If it was just installed, open a new terminal or make sure it exists in its default user location.
- Internet access and disk space for Python and dependencies. The installer requests Python 3.12 automatically; you do not need to choose or install Python first.
- Git only if you choose cloning. An extracted ZIP works without Git.

No model API key is required by the local installation itself. Model usage through your host may incur its normal costs. Do not purchase or enable integrations during setup without understanding their costs.

## Terminal fallback

If you already downloaded and extracted the ZIP, open a terminal **in the extracted project folder** and skip the clone and change-directory commands.

### macOS or Linux

```sh
git clone https://github.com/sidart10/career-agent.git
cd career-agent
bash scripts/install.sh
bash scripts/career.sh version --json
bash scripts/career.sh doctor --installation-only --json
```

### Windows PowerShell

```powershell
git clone https://github.com/sidart10/career-agent.git
Set-Location career-agent
./scripts/install.ps1
./scripts/career.ps1 version --json
./scripts/career.ps1 doctor --installation-only --json
```

If PowerShell blocks script execution, follow your organization's execution-policy guidance. Do not disable machine-wide security settings just to run setup.

Stop if a command fails; later commands cannot repair a failed clone. If the folder already exists, open it instead of cloning over it. For missing Git, use the ZIP route.

## What success means

The installer reports the project launcher and validates software-only diagnostics before activating the new runtime. JSON command results use `ok` and `data`. The command above should return `"ok": true` with `data.capability_report.installation_ready` equal to `true`. It deliberately returns `workspace: null`: it has not checked your candidate files or repaired your saved workspace choice.

- **Installation ready:** the local runtime and skill installation passed installation checks.
- **Onboarding ready:** the selected workspace, consent, profile review, and preferences passed onboarding checks.
- **Document/submission readiness:** separate workflow checks. Missing browser tools do not prevent importing evidence or drafting.

Now open this same project in your agent and ask to continue onboarding. Installation alone does not create or confirm your career profile.

Before initialization, `workspace show --json` can report “Workspace is not initialized.” For a genuinely new setup with no saved selection, the agent confirms the proposed folder with you, initializes it, and saves the selection. If you previously selected a workspace, the same error means recovery is needed; do not initialize over the missing location. After onboarding, `onboarding status --json` should show `onboarding_ready: true` and `first_incomplete_phase: null`. Otherwise, its `next_action` explains what remains.

## What setup changes

The installer creates a frozen, project-local Python environment under `.career-agent/runtimes/`. It exposes the canonical `.agents/skills/` through managed Claude links or verified mirrors, records ownership in an installation manifest, and activates the new runtime only after validation.

It does not require a global `career` command, change your shell startup files, replace a global tool installation, or delete your personal workspace. The launchers anchor all project paths to their own location, so they also work when invoked by absolute path from another folder.

## Repair, update, move, and uninstall

**Repair:** rerun the same installer. It builds and validates a new runtime before switching. A failed validation keeps the previous active runtime.

**Missing or changed saved workspace:** repair the software first if needed; installation does not depend on the saved candidate being accessible. Then ask the agent to locate and explicitly select your intended existing workspace. The installer preserves the old binding until you make that choice. Do not delete the binding, edit its identity, or create an empty replacement to silence the error. See the [recovery steps](troubleshooting.md#recover-a-missing-workspace-selection).

**Update:** back up your workspace first. With a Git checkout, review local modifications and update the code before rerunning setup. Do not discard local changes. With a ZIP, keep the old folder until the new installation works; ask the agent to select your existing workspace explicitly rather than copying only some of its records.

**Move or rename the folder:** stop active career operations, move the whole project, then rerun setup. Python environments are not portable, so the old launcher intentionally asks for repair. Format-2 workspace evidence uses relative paths. Legacy format-1 workspaces need an explicit backed-up migration; see [workspace and state](workspace-and-state.md).

**Uninstall the local software:**

```sh
bash scripts/install.sh --uninstall
```

On PowerShell use `./scripts/install.ps1 -Uninstall`. Uninstall removes verified installer-owned skill links/mirrors, the active pointer, and owned runtime generations. It preserves your workspace, workspace selection, and unrelated global installations. It does not delete your personal data.

See [troubleshooting](troubleshooting.md) if a check fails. Local automated test coverage is not a promise that every host/OS combination has been release-tested.
