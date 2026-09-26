# Compatibility

Career Agent 0.1 requires Python 3.11, 3.12, or 3.13. `career version --json` reports CLI `0.1.0`, skill bundle `0.1.0`, skill API `1.0`, accepted skill API range, and workspace schema support.

The source tree contains Unix and PowerShell installers. CI exercises the deterministic suite on GitHub-hosted Ubuntu, macOS, and Windows runners, but the repository owner must still name the exact public support matrix before release. A platform is not supported merely because source code is expected to be portable.

V0.1 skills are repo-local. Codex uses `.agents/skills`; Claude Code uses installer-managed `.claude/skills` relative links or mirrors. Installing the Python tool alone does not make the skills globally available.

OCR is deferred. Text PDFs, DOCX, and UTF-8 text are supported extraction inputs. Image-only PDFs fail with `ocr_required` and must be replaced with a text-bearing file or transcribed through a separately governed process.
