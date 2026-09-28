# Compatibility and validation boundaries

The project installer provisions Python 3.12 from the frozen lockfile. The package declares Python 3.11–3.13 compatibility; that declaration alone is not proof of every platform combination.

The repository includes Unix and PowerShell installers and a CI matrix for Ubuntu, macOS, and Windows. The setup-repair work was exercised locally on macOS, including a real archive install, paths with spaces and Unicode, nested launcher invocation, failed-validation rollback, relocation/repair, and uninstall preserving personal data. Changes to the CI workflow still need a remote run; Windows and Linux results must not be inferred from local macOS results.

Skills are repository-local. The canonical source is `.agents/skills/`; the installer creates managed `.claude/skills/` links or verified mirrors. Python package installation alone does not provide host discovery. Open the same project as a local folder. A live first-user onboarding session in each host remains a release validation step, not something a parser or unit test proves.

Text PDFs, DOCX, and UTF-8 text are extraction inputs. OCR is not bundled. Image-only PDFs report `ocr_required`; provide text-bearing evidence or a separately reviewed transcription.

Workspace format 2 supports relative internal evidence paths. Format 1 is a legacy read/migrate format. The product remains a development preview until release gates, including license and support-matrix decisions, are satisfied.
