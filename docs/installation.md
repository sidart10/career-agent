# Install Career Agent 0.1

## Before you begin

You need Git, Python 3.11–3.13, and [`uv`](https://docs.astral.sh/uv/). Use a tagged Career Agent release, not a moving branch. V0.1 is repository-local: Codex or Claude Code must be launched from the cloned checkout for the bundled skills to be discovered.

Run `uv tool update-shell` once before installation if `uv tool dir --bin` is not already on `PATH`, then restart the shell. The installer verifies that `career` is resolvable and does not edit shell startup files for you.

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

The installer uses `uv tool install --force` for the CLI. It keeps `.agents/skills` canonical, creates relative Claude skill links where supported, falls back to verified mirrors, and records every managed path in `.career-agent/install-manifest.json`. It refuses an unmanaged conflict or dirty canonical skill source. Before changing an existing CLI tool environment, it snapshots that environment and executable. Managed skill paths and the ownership manifest are staged with backups. A failed CLI install, skill swap, or final Doctor validation restores the prior managed installation.

## Repair, upgrade, rollback, and uninstall

- Repair: rerun the installer from the same clean tagged checkout.
- Upgrade: check out the newer release tag, review its release notes, and rerun the installer.
- Roll back: check out the previously used release tag and rerun the installer. The installer replaces only its manifest-owned skill paths and the isolated `uv` tool.
- Uninstall: run the command below. It removes only manifest-owned skill paths and the `career-agent` uv tool; unrelated skills remain untouched.

```sh
bash scripts/install.sh --uninstall
```

PowerShell uses `./scripts/install.ps1 -Uninstall`.

After installation, launch the agent host from this checkout and ask it to run `career-onboard`.
