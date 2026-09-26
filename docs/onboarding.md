# Onboarding

Onboarding is a read-only projection over real workspace state. There is no phase ledger to become stale. Start or resume at any time with:

```sh
career onboarding status --json
```

The command reports the first incomplete phase, exact next action, imports, proposals, conflicts, confirmed facts, preferences, redacted answer counts, and all three readiness layers.

The normal sequence is:

1. `career init --json`, then verify `career workspace show --json`.
2. `career import preview <resume-or-files> --json`.
3. Inspect extraction status, warnings, duplicates, and OCR status; apply all sources or repeat `--source-id` to apply only selected successful sources.
4. Read `career privacy status --json`. Deterministic import can happen first, but model-assisted interpretation cannot.
5. Record informed consent with `career privacy acknowledge --policy-version <shown-version> --provider <configured-provider> --json`.
6. Send the model's structured, exact-span output through `career profile propose --input <proposal.json> --json`.
7. Review `career profile list --json` and confirm each supported fact with `career profile confirm`.
8. Save subjective goals with `career preferences set --input <preferences.json> --json`.
9. Re-run `career onboarding status --json`.

Onboarding never stores credentials, silently retains sensitive answers, or grants submission authority. Missing facts stay missing. Conflicting facts require a human choice.
