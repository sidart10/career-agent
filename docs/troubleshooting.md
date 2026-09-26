# Troubleshooting

Start with `career doctor --json`; it does not repair anything. Match the reported blocker to its layer:

- `runtime_detection`: launch from a supported Codex or Claude Code host, or set the documented runtime declaration in a controlled test environment.
- `skill_installation`: run the installer again from a clean tagged checkout. Do not overwrite unmanaged skill folders.
- `workspace_mutation`: verify the selected path, permissions, filesystem, and marker with `career workspace show --json`.
- `pdf_inspection`: repair the isolated CLI installation so packaged dependencies are present.
- `latex_rendering`: install a supported LaTeX engine only if document rendering is needed; onboarding itself should continue.
- `browser_control` or `approval_authority`: submission stays unavailable. Do not spoof these declarations for real use.

For interrupted operations, run `career recover plan --json`, inspect the classification, then apply only the current digest. Cleanup and reset have their own preview/apply commands. Do not edit journals or lock files manually.

An image-only PDF reports `ocr_required`; V0.1 does not ship OCR. A proposal checksum, offset, or exact-text error means the recorded model output no longer matches the imported extraction. Re-run interpretation against the current extracted text instead of weakening validation.
