# Install Career Agent 0.1

## Before you begin

You need Git, Python 3.11–3.13, and [`uv`](https://docs.astral.sh/uv/). Use a tagged Career Agent release, not a moving branch. V0.1 is repository-local: Codex or Claude Code must be launched from the cloned checkout for the bundled skills to be discovered.

The project license and final supported operating-system matrix are still owner decisions. Until they are recorded in a release, treat this as supervised early access rather than a general public release.

## macOS or Linux

```sh
git clone --branch <release-tag> https://github.com/sidart10/career-agent.git
cd career-agent
bash scripts/install.sh
career version --json
career doctor --json
```

## Windows PowerShell

```powershell
git clone --branch <release-tag> https://github.com/sidart10/career-agent.git
Set-Location career-agent
./scripts/install.ps1
career version --json
career doctor --json
```

The installer uses `uv tool install --force` for the CLI. It keeps `.agents/skills` canonical, creates relative Claude skill links where supported, falls back to verified mirrors, and records every managed path in `.career-agent/install-manifest.json`. It refuses an unmanaged conflict or dirty canonical skill source. If `career` is not immediately found, run `uv tool update-shell` and restart the shell.

Re-running the same command repairs the managed installation. To uninstall only manifest-owned paths:

```sh
bash scripts/install.sh --uninstall
```

PowerShell uses `./scripts/install.ps1 -Uninstall`.

After installation, launch the agent host from this checkout and ask it to run `career-onboard`.
