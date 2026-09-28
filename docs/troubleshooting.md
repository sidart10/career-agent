# Troubleshooting

Tell your agent what failed and include the error text without personal document contents. Ask it to inspect the project installation and selected workspace. Diagnostics do not repair or delete data.

| What you see | What to do |
| --- | --- |
| `no such file or directory: release-tag` | Old docs used a shell-breaking placeholder. Use the real clone/ZIP instructions in [installation](installation.md). |
| `career: command not found` | Use this project's launcher, not a global command. See the commands below. |
| Installer says uv is missing | Install uv using its [official instructions](https://docs.astral.sh/uv/getting-started/installation/), with user approval. Restart the terminal if needed. |
| Runtime missing or project moved | Rerun the installer in the current project location. It rebuilds software without relocating your workspace. |
| Interrupted setup data exists | Preserve the reported staging folder and its backups. Ask for an explicit recovery review before moving/restoring anything; rerunning setup will not discard it. |
| Another setup or uninstall is running | Wait for it to finish. Do not remove its lock file or run concurrent repair. |
| Skill drift or unmanaged conflict | Inspect the conflicting path. Preserve user-owned files; do not force-overwrite them. Rerun setup from the intended source. |
| Selected workspace missing or identity changed | Repair software if needed, then follow the recovery steps below. Do not initialize a replacement candidate at the missing path. |
| Legacy workspace format | Preview and approve a format-2 migration; if moved, provide its former root. |
| Unsupported filesystem | Use a supported local folder, not network storage or a cloud-sync folder. |
| Missing LaTeX | Onboarding and text drafts can continue. Ask before installing a renderer for PDF release. |
| Missing browser or approval authority | Preparation can continue; live submission cannot. Do not fake capability declarations. |
| `ocr_required` or empty extraction | Supply a text-bearing document or reviewed transcription. OCR is not bundled. |
| Evidence checksum or span mismatch | Inspect the preserved source after consent; reconstruct the proposal against its actual text. Never relax checks or hand-edit evidence. |

From the project folder, macOS/Linux:

```sh
bash scripts/career.sh doctor --json
bash scripts/career.sh workspace show --json
bash scripts/career.sh onboarding status --json
```

On Windows PowerShell, replace `bash scripts/career.sh` with `./scripts/career.ps1`. If the runtime does not exist, use `scripts/install.sh` or `scripts/install.ps1` first.

Doctor's structured details are under `data.capability_report`. Installation, core workspace, documents, and submission are separate checks. Unknown host identification is informational; it does not by itself prevent local setup.

For interrupted operations, the agent can run `recover plan`, explain its classification, and apply an approved unchanged digest. Cleanup and reset have their own preview/apply contracts. Never manually remove a lock or edit a journal to make an error disappear.

## Recover a missing workspace selection

1. Locate the full workspace you intended to use, including its `workspace.json`, profile, resources, and journals. Stop if you are unsure which candidate it belongs to.
2. If the launcher is missing or says the project moved, rerun `bash scripts/install.sh` (PowerShell: `./scripts/install.ps1`). This repairs software without reading or replacing your saved workspace binding.
3. Verify software with `bash scripts/career.sh doctor --installation-only --json`. Expect `ok: true` and `data.capability_report.installation_ready: true`; this does **not** mean candidate data is healthy.
4. Tell the agent the exact existing workspace folder and explicitly ask it to select it. The engine command is `workspace select` followed by that folder's quoted absolute path and `--json`. Use the project launcher, not a global `career` command. Selection validates the workspace before saving the new binding. If `CAREER_WORKSPACE` or a command-line workspace override is set, resolve that override too; it takes precedence over the binding.
5. Run `workspace show --json`, ordinary `doctor --json`, and `onboarding status --json` through the launcher. Confirm the reported path and identity. Follow any migration or recovery gate; do not manually edit records.

An old layout-migration preview without a `schema_version` is rejected. Generate a fresh plan, review it, and approve its new digest before applying it.
