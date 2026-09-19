"""Shared, deterministic implementation for the Unix and PowerShell installers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

RUNTIMES = {"claude_code": Path(".claude/skills"), "codex": Path(".agents/skills")}
ENTRY_FILES = ("career-rules.md", "AGENTS.md", "CLAUDE.md")


class InstallError(RuntimeError):
    """Expected installation failure with a concise user-facing message."""


def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.resolve(strict=False).rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root.resolve(strict=False)).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _skill_directories(source: Path) -> tuple[Path, ...]:
    skills_root = source / "skills"
    skills = tuple(
        sorted(
            path
            for path in skills_root.glob("career-*")
            if path.is_dir() and (path / "SKILL.md").is_file()
        )
    )
    if not skills:
        raise InstallError(f"No canonical career skills found under {skills_root}")
    missing = [name for name in ENTRY_FILES if not (source / name).is_file()]
    if missing:
        raise InstallError(f"Canonical source is missing: {', '.join(missing)}")
    return skills


def _reject_dirty_source(source: Path) -> None:
    if not (source / ".git").exists():
        return
    result = subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "skills",
            *ENTRY_FILES,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InstallError("Could not verify canonical source cleanliness")
    if result.stdout.strip():
        raise InstallError("Dirty canonical source; commit or restore workflow changes first")


def _load_prior_manifest(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _managed_roots(manifest: dict[str, object] | None) -> set[Path]:
    if manifest is None or not isinstance(manifest.get("installed_targets"), dict):
        return set()
    targets = manifest["installed_targets"]
    assert isinstance(targets, dict)
    return {
        Path(value).expanduser().resolve(strict=False)
        for value in targets.values()
        if isinstance(value, str)
    }


def _remove_managed_destination(
    path: Path,
    root: Path,
    managed_roots: set[Path],
    source_skill: Path,
) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    recoverable_mirror = path.is_dir() and hash_tree(path) == hash_tree(source_skill)
    if root.resolve(strict=False) not in managed_roots and not recoverable_mirror:
        raise InstallError(f"Refusing to replace unmanaged skill path: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        raise InstallError(f"Refusing to replace non-directory skill path: {path}")


def _install_links(
    skills: tuple[Path, ...],
    target_roots: dict[str, Path],
    managed_roots: set[Path],
) -> None:
    created: list[Path] = []
    try:
        for root in target_roots.values():
            root.mkdir(parents=True, exist_ok=True)
            for source_skill in skills:
                destination = root / source_skill.name
                if destination.is_symlink() and destination.resolve() == source_skill.resolve():
                    continue
                _remove_managed_destination(destination, root, managed_roots, source_skill)
                destination.symlink_to(source_skill.resolve(), target_is_directory=True)
                created.append(destination)
    except OSError:
        for path in reversed(created):
            if path.is_symlink():
                path.unlink()
        raise


def _install_mirrors(
    skills: tuple[Path, ...],
    target_roots: dict[str, Path],
    managed_roots: set[Path],
    staging_root: Path,
) -> None:
    run_staging = staging_root / uuid.uuid4().hex
    try:
        for runtime, root in target_roots.items():
            runtime_staging = run_staging / runtime
            runtime_staging.mkdir(parents=True)
            for source_skill in skills:
                shutil.copytree(source_skill, runtime_staging / source_skill.name)
            root.mkdir(parents=True, exist_ok=True)
            for source_skill in skills:
                destination = root / source_skill.name
                _remove_managed_destination(destination, root, managed_roots, source_skill)
                os.replace(runtime_staging / source_skill.name, destination)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _install_entry_files(source: Path, target: Path, *, mode: str) -> None:
    for name in ENTRY_FILES:
        source_path = (source / name).resolve()
        destination = target / name
        if source_path == destination.resolve(strict=False):
            continue
        if destination.is_symlink():
            if mode == "link" and destination.resolve() == source_path:
                continue
            destination.unlink()
        elif destination.exists():
            if destination.is_file() and destination.read_bytes() == source_path.read_bytes():
                continue
            raise InstallError(f"Refusing to replace existing root instruction file: {destination}")
        if mode == "link":
            destination.symlink_to(source_path)
        else:
            with tempfile.NamedTemporaryFile(dir=target, delete=False) as temporary:
                temporary.write(source_path.read_bytes())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)


def _validate_entry_files(source: Path, target: Path) -> None:
    """Fail before skill mutation when a consumer owns conflicting root policy."""

    for name in ENTRY_FILES:
        source_path = (source / name).resolve()
        destination = target / name
        if source_path == destination.resolve(strict=False) or not destination.exists():
            continue
        if destination.is_symlink() and destination.resolve() == source_path:
            continue
        if destination.is_file() and destination.read_bytes() == source_path.read_bytes():
            continue
        raise InstallError(f"Refusing to replace existing root instruction file: {destination}")


def _write_manifest(
    path: Path,
    *,
    mode: str,
    source: Path,
    target_roots: dict[str, Path],
    prior: dict[str, object] | None,
) -> None:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    created_at = prior.get("created_at", now) if prior else now
    manifest = {
        "schema_version": 1,
        "created_at": created_at,
        "updated_at": now,
        "mode": mode,
        "canonical_source": str((source / "skills").resolve()),
        "source_checksum": hash_tree(source / "skills"),
        "installed_targets": {
            runtime: str(path.resolve(strict=False))
            for runtime, path in sorted(target_roots.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(manifest, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def _install_python(source: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError("uv is required for the pinned Python installation")
    result = subprocess.run([uv, "sync", "--frozen", "--project", str(source)], check=False)
    if result.returncode != 0:
        raise InstallError("Pinned Python dependency installation failed")


def _run_doctor(source: Path, target: Path, manifest_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise InstallError("uv is required to run the installed doctor")
    environment = dict(os.environ)
    environment.update(
        {
            "CAREER_WORKSPACE": str((target / ".career").resolve()),
            "CAREER_INSTALL_MANIFEST": str(manifest_path.resolve()),
            "CAREER_RUNTIME": environment.get("CAREER_RUNTIME", "codex"),
        }
    )
    result = subprocess.run(
        [uv, "run", "--project", str(source), "career", "doctor", "--json"],
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise InstallError("career doctor could not inspect the installation")


def install(args: argparse.Namespace) -> None:
    source = args.source.expanduser().resolve()
    target = args.target.expanduser().resolve()
    if target == Path(target.anchor) or target == Path.home().resolve():
        raise InstallError("Refusing to install into a filesystem root or home directory")
    skills = _skill_directories(source)
    if not args.allow_dirty_source:
        _reject_dirty_source(source)
    target.mkdir(parents=True, exist_ok=True)
    _validate_entry_files(source, target)
    metadata_root = target / ".career-agent"
    manifest_path = metadata_root / "install-manifest.json"
    prior = _load_prior_manifest(manifest_path)
    managed_roots = _managed_roots(prior)
    target_roots = {runtime: target / relative for runtime, relative in RUNTIMES.items()}
    staging_root = metadata_root / "install-staging"
    shutil.rmtree(staging_root, ignore_errors=True)

    mode = "mirror" if args.force_mirror else "link"
    if mode == "link":
        try:
            _install_links(skills, target_roots, managed_roots)
        except OSError:
            mode = "mirror"
    if mode == "mirror":
        _install_mirrors(skills, target_roots, managed_roots, staging_root)
    _install_entry_files(source, target, mode=mode)
    _write_manifest(
        manifest_path,
        mode=mode,
        source=source,
        target_roots=target_roots,
        prior=prior,
    )
    if not args.skip_python_install:
        _install_python(source)
    if not args.skip_doctor:
        _run_doctor(source, target, manifest_path)
    print(f"Installed career workflows in {mode} mode at {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--force-mirror", action="store_true")
    parser.add_argument("--allow-dirty-source", action="store_true")
    parser.add_argument("--skip-python-install", action="store_true")
    parser.add_argument("--skip-doctor", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        install(parse_args())
    except InstallError as error:
        print(f"install error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
