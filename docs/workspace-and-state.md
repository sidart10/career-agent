# Your workspace and saved state

Personal data belongs in the selected workspace. New project-based setups default to **`workspace/` inside the Career Agent folder**. Existing selected external workspaces remain supported; setup must show your selection instead of silently relocating it.

The root ignore rules exclude `workspace/` and `.career-agent/` from normal Git additions. This does not protect already-tracked files, forced additions, cloud sync, or screenshots. Never publish your personal workspace.

## Folder guide

| Location inside the workspace | Contents | Edit directly? |
| --- | --- | --- |
| `inbox/` | Files awaiting import | Yes |
| `resources/` | Preserved evidence, normalized text, provenance | No; import new evidence instead |
| `profile/` | Facts, proposals, preferences, consent, reusable answers | Use the agent's governed commands |
| `opportunities/` | Job records, evaluations, source snapshots | Use the agent |
| `applications/` | Per-job manifests, drafts, releases, uploads | Unreleased drafts only |
| `pipeline.md` | Generated overview | No; regenerate |
| `runs/`, `journals/`, `maintenance/` | Operation identities, recovery and migration records | No |
| `workspace.json` | Workspace identity and format version | No |

Some paths appear only when their workflow runs. Generated records are not a substitute for original evidence.

## Portability

New workspaces use format 2. Internal imported source/text paths are stored relative to the workspace and resolved within it. Original external source locations remain provenance, not required read locations after import.

To move a project: stop active operations, back up the complete workspace, move the whole project, and rerun the installer to rebuild its Python runtime. The default/internal workspace selection travels with the project. External bindings must be reselected if their external path changes.

Back up and restore the whole workspace, including hidden files, not just `profile/`. Preserve the project-local binding separately if you use a nondefault selection. Copies with the same workspace ID should not be used concurrently.

## Existing format-1 workspaces

Legacy workspaces are readable, but governed CLI writes require an explicit migration. The agent should:

1. Inspect the workspace identity and show the selected root.
2. Prepare a layout migration with `migrate plan --target-version 2 --json`.
3. If the workspace has already moved, supply its former absolute root using `--former-root`; never guess it from a document's instructions.
4. Show the affected files and plan digest and obtain approval.
5. Apply that exact plan using `migrate apply DIGEST --json` (substitute the returned digest, not the word DIGEST).

Migration validates preserved imported evidence, backs up affected records, rewrites supported internal import/profile references, and keeps workspace identity and historical operation records. It must not rewrite historical submission payload digests or grants of authority. Failed validation is a blocker; do not hand-edit paths to make it pass.

Source files in `inbox/` and ordinary drafts remain yours. Reset, cleanup, and migration are separate planned operations, never implied by running Doctor.
