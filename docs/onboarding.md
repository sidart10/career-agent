# Set up your profile

Open the Career Agent folder in your local agent and say:

> Help me set up my career agent. Keep my personal files here and walk me through each step.

The agent should do the technical work and explain the human decisions. You should not need to compose structured JSON or know internal command names.

## The walkthrough

1. **Check installation.** If the project runtime is missing, the agent follows the [installation guide](installation.md). It does not start by assuming a global command exists.
2. **Choose your workspace.** The default is the visible `workspace/` folder inside this project. If you previously selected a workspace, the agent shows that path and its identity and asks whether to keep it. It must not silently create a second profile.
3. **Add career evidence.** Put a résumé, work-history notes, or other supported document in `workspace/inbox/`, or provide its location. With no résumé, dictate your background and ask the agent to save a text file for import. Sources are copied into the workspace; originals are not deleted.
4. **Review the import preview.** The preview reports file metadata, duplicates, extraction failures, and warnings without exposing extracted personal text to the interpreting model. Image-only PDFs need OCR supplied separately; an empty extraction is not a successful résumé import.
5. **Decide about model processing.** The agent explains the actual provider used by your host and the data it will receive. You can decline. Local extraction can happen before consent, but model interpretation and source-text inspection must wait. Changing the declared provider requires renewed acknowledgement.
6. **Review proposed facts.** The agent reads consented text and proposes evidence-backed facts. Confirm, correct, or reject each suggestion. Corrections need supporting evidence; conflicting alternatives need a choice. Declining every suggestion is valid, but leaves more evidence work before a usable profile exists.
7. **Set preferences.** Explain target roles, locations, exclusions, and priorities. These are your preferences, not claims that require résumé evidence. The agent prepares the structured input and asks you to confirm it.
8. **Check readiness.** The agent reports what passed, what remains, and the next concrete action.

## Resume later

Say “Continue my onboarding.” Status is computed from saved records, not conversation memory. Confirmed facts, rejected proposals, and resolved conflicts should not repeatedly be offered for confirmation.

If you import corrected evidence after rejecting suggestions, the agent must interpret that new source before asking for more files. A source with no proposed facts remains at interpretation; the agent should explain if it contains no usable career evidence and ask for relevant evidence, never invent facts just to clear the status. Rejecting every alternative closes that conflict but does not create a confirmed fact.

For agents, `onboarding status --json` returns `data.first_incomplete_phase`, `next_action`, counts, `profile_review_complete`, and `onboarding_ready`. A reviewed profile is not proof that every career fact is represented. Document generation and live submission have separate readiness checks.

## Where things are saved

- `workspace/inbox/`: files you provide.
- `workspace/resources/`: preserved evidence and extraction.
- `workspace/profile/`: structured profile, preferences, and privacy acknowledgement.
- `workspace/applications/`: job-specific work created later.

The actual selected workspace may be elsewhere if you chose one. Ask “Where are my files?” to see the resolved path. See [workspace and state](workspace-and-state.md) before moving or restoring files.

## Boundaries

Onboarding never grants submission authority, asks for credentials, or silently retains sensitive application answers. Missing facts remain missing. Metadata previews can still expose filenames; do not put sensitive content in filenames.

Privacy acknowledgement records your decision but cannot prevent an agent host from reading a file directly or sending it to its provider. The shipped workflow requires the agent to honor this boundary.

[Agent command examples and input schemas](agent-workflows.md) document the engine contracts used behind this conversation.
