"""Transactional repo-local installer shared by Unix and PowerShell entry points."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

CANONICAL_SKILLS = Path(".agents/skills")
CLAUDE_SKILLS = Path(".claude/skills")
PRODUCT_VERSION = "0.1.0"
SKILL_BUNDLE_VERSION = "0.1.0"
SKILL_API_VERSION = "1.0"
SUPPORTED_CLI_RANGE = ">=0.1.0,<0.2.0"


class InstallError(RuntimeError):
    """Expected installation failure with a concise user-facing message."""


@contextmanager
def _installation_lock(target: Path) -> Iterator[None]:
    metadata = target / ".career-agent"
    metadata.mkdir(parents=True, exist_ok=True)
    lock_path = metadata / "install.lock"
    if lock_path.is_symlink():
        raise InstallError("Refusing symbolic-link installation lock")
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise InstallError(
                "Another setup or uninstall is running; wait for it to finish"
            ) from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    resolved = root.resolve(strict=False)
    for path in sorted(resolved.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(resolved).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _skill_directories(source: Path) -> tuple[Path, ...]:
    skills_root = source / CANONICAL_SKILLS
    skills = tuple(
        sorted(
            path
            for path in skills_root.glob("career-*")
            if path.is_dir() and not path.is_symlink() and (path / "SKILL.md").is_file()
        )
    )
    if not skills:
        raise InstallError(f"No canonical career skills found under {skills_root}")
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
            str(CANONICAL_SKILLS),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InstallError("Could not verify canonical source cleanliness")
    if result.stdout.strip():
        raise InstallError("Dirty canonical source; commit or restore skill changes first")


def _source_revision(source: Path, checksum: str) -> str:
    if not (source / ".git").exists() or shutil.which("git") is None:
        return f"tree:{checksum}"
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if result.returncode == 0 and len(revision) == 40:
        return f"git:{revision}"
    return f"tree:{checksum}"


def _load_manifest(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _absolute_path(path: Path) -> Path:
    """Return a lexical absolute path without resolving a managed symlink target."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _managed_paths(
    prior: dict[str, object] | None,
    skills: tuple[Path, ...],
    target: Path | None = None,
) -> set[Path]:
    if prior is None:
        return set()
    managed = prior.get("managed_paths")
    if isinstance(managed, list):
        return {
            _absolute_path(
                (target / value)
                if target is not None and not Path(value).is_absolute()
                else Path(value)
            )
            for value in managed
            if isinstance(value, str)
        }
    targets = prior.get("installed_targets")
    if not isinstance(targets, dict):
        return set()
    claude_root = targets.get("claude_code")
    if not isinstance(claude_root, str):
        return set()
    root = _absolute_path(Path(claude_root))
    return {_absolute_path(root / skill.name) for skill in skills}


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _is_equivalent_install(destination: Path, source_skill: Path) -> bool:
    if destination.is_symlink():
        try:
            return destination.resolve() == source_skill.resolve()
        except OSError:
            return False
    return destination.is_dir() and hash_tree(destination) == hash_tree(source_skill)


def _validate_destinations(
    skills: tuple[Path, ...],
    destination_root: Path,
    managed: set[Path],
) -> None:
    for source_skill in skills:
        destination = destination_root / source_skill.name
        if not _path_exists(destination):
            continue
        if _absolute_path(destination) in managed:
            continue
        if _is_equivalent_install(destination, source_skill):
            continue
        raise InstallError(f"Refusing to replace unmanaged skill path: {destination}")


def _stage_skills(
    skills: tuple[Path, ...],
    staging: Path,
    destination_root: Path,
    *,
    mode: str,
) -> None:
    staging.mkdir(parents=True)
    for source_skill in skills:
        destination = destination_root / source_skill.name
        staged = staging / source_skill.name
        if mode == "link":
            relative = os.path.relpath(source_skill.resolve(), destination.parent.resolve())
            staged.symlink_to(relative, target_is_directory=True)
        else:
            shutil.copytree(source_skill, staged)


def _manifest_payload(
    source: Path,
    target: Path,
    skills: tuple[Path, ...],
    *,
    claude_mode: str,
    prior: dict[str, object] | None,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    checksum = hash_tree(source / CANONICAL_SKILLS)
    created_at = prior.get("created_at", now) if prior else now
    claude_root = _absolute_path(target / CLAUDE_SKILLS)
    managed_paths = [str(_absolute_path(claude_root / skill.name)) for skill in skills]
    return {
        "schema_version": 3,
        "created_at": created_at,
        "updated_at": now,
        "product_version": PRODUCT_VERSION,
        "skill_bundle_version": SKILL_BUNDLE_VERSION,
        "skill_api_version": SKILL_API_VERSION,
        "supported_cli_range": SUPPORTED_CLI_RANGE,
        "source_revision": _source_revision(source, checksum),
        "canonical_source": CANONICAL_SKILLS.as_posix(),
        "source_checksum": checksum,
        "installed_targets": {
            "claude_code": CLAUDE_SKILLS.as_posix(),
            "codex": CANONICAL_SKILLS.as_posix(),
        },
        "installed_modes": {"claude_code": claude_mode, "codex": "canonical"},
        "managed_paths": [str(Path(p).relative_to(target)) for p in managed_paths],
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def _transactional_skill_install(
    source: Path,
    target: Path,
    skills: tuple[Path, ...],
    *,
    force_mirror: bool,
    simulate_failure_after: int | None,
    validate_install: Callable[[Path, dict[str, object]], None] | None = None,
    runtime_relative: str | None = None,
) -> tuple[Path, dict[str, object]]:
    metadata_root = target / ".career-agent"
    manifest_path = metadata_root / "install-manifest.json"
    prior = _load_manifest(manifest_path)
    managed = _managed_paths(prior, skills, target)
    destination_root = target / CLAUDE_SKILLS
    _validate_destinations(skills, destination_root, managed)

    staging_root = metadata_root / "install-staging"
    if staging_root.exists() and any(staging_root.iterdir()):
        raise InstallError(
            f"Interrupted setup data exists at {staging_root}; preserve it and inspect backups "
            "before repair. No files were discarded."
        )
    run_root = staging_root / uuid.uuid4().hex
    new_root = run_root / "new"
    backup_root = run_root / "backup"
    destination_root_existed = destination_root.exists()
    destination_root.mkdir(parents=True, exist_ok=True)

    mode = "mirror" if force_mirror else "link"
    preserve_backups = False
    try:
        try:
            _stage_skills(skills, new_root, destination_root, mode=mode)
        except OSError:
            if force_mirror:
                raise
            shutil.rmtree(new_root, ignore_errors=True)
            mode = "mirror"
            _stage_skills(skills, new_root, destination_root, mode=mode)

        manifest = _manifest_payload(
            source,
            target,
            skills,
            claude_mode=mode,
            prior=prior,
        )
        if runtime_relative is not None:
            manifest["runtime_path"] = runtime_relative
        staged_manifest = run_root / "new-manifest.json"
        _write_json(staged_manifest, manifest)

        installed: list[Path] = []
        backups: list[tuple[Path, Path]] = []
        try:
            backup_root.mkdir(parents=True)
            for index, source_skill in enumerate(skills, start=1):
                destination = destination_root / source_skill.name
                backup = backup_root / source_skill.name
                if _path_exists(destination):
                    os.replace(destination, backup)
                    backups.append((backup, destination))
                os.replace(new_root / source_skill.name, destination)
                installed.append(destination)
                if simulate_failure_after == index:
                    raise InstallError("Simulated transactional installer failure")

            prior_manifest_backup = backup_root / "install-manifest.json"
            if manifest_path.is_file():
                os.replace(manifest_path, prior_manifest_backup)
                backups.append((prior_manifest_backup, manifest_path))
            os.replace(staged_manifest, manifest_path)
            installed.append(manifest_path)
            if validate_install is not None:
                validate_install(manifest_path, manifest)
            if runtime_relative is not None:
                pointer = metadata_root / "active-runtime"
                pointer_backup = backup_root / "active-runtime"
                if pointer.exists():
                    os.replace(pointer, pointer_backup)
                    backups.append((pointer_backup, pointer))
                staged_pointer = run_root / "new-pointer"
                staged_pointer.write_text(runtime_relative + "\n", encoding="utf-8")
                os.replace(staged_pointer, pointer)
                installed.append(pointer)
        except BaseException:
            try:
                for path in reversed(installed):
                    _remove_path(path)
                for backup, destination in reversed(backups):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(backup, destination)
            except BaseException:
                preserve_backups = True
                raise
            raise
        return manifest_path, manifest
    finally:
        if not preserve_backups:
            shutil.rmtree(run_root, ignore_errors=True)
            with suppress(OSError):
                staging_root.rmdir()
        if not destination_root_existed and destination_root.is_dir():
            with suppress(OSError):
                destination_root.rmdir()


def _uv() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise InstallError("uv is required; install it before running Career Agent setup")
    return executable


def _run_doctor(executable: Path, target: Path, manifest_path: Path) -> None:
    environment = dict(os.environ)
    environment.update(
        {
            "CAREER_INSTALL_MANIFEST": str(manifest_path.resolve()),
        }
    )
    result = subprocess.run(
        [
            str(executable),
            "-m",
            "career_agent",
            "--project",
            str(target),
            "doctor",
            "--installation-only",
            "--json",
        ],
        cwd=target,
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout)
        ready = payload["ok"] and payload["data"]["capability_report"]["installation_ready"] is True
    except (ValueError, KeyError, TypeError):
        ready = False
    if result.returncode != 0 or not ready:
        raise InstallError(
            "Installation verification failed; previous installation was preserved. "
            + result.stdout
        )


def _uninstall(source: Path, target: Path, *, skip_python_install: bool) -> None:
    manifest_path = target / ".career-agent" / "install-manifest.json"
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        raise InstallError("No valid Career Agent install manifest was found")
    skills = _skill_directories(source)
    managed = _managed_paths(manifest, skills, target)
    canonical = {skill.name: skill for skill in skills}
    claude_root = _absolute_path(target / CLAUDE_SKILLS)
    for path in sorted(managed):
        if path.parent != claude_root or path.name not in canonical:
            raise InstallError(f"Refusing to uninstall unexpected managed path: {path}")
        if _path_exists(path) and not _is_equivalent_install(path, canonical[path.name]):
            raise InstallError(f"Refusing to remove drifted managed skill path: {path}")
    for path in sorted(managed, reverse=True):
        _remove_path(path)
    runtimes = target / ".career-agent/runtimes"
    if runtimes.is_dir() and not runtimes.is_symlink():
        for runtime in runtimes.iterdir():
            owner = runtime / ".project-root"
            if (
                runtime.is_dir()
                and not runtime.is_symlink()
                and owner.is_file()
                and owner.read_text().strip() == str(target)
            ):
                _remove_path(runtime)
    (target / ".career-agent/active-runtime").unlink(missing_ok=True)
    manifest_path.unlink()
    print(f"Uninstalled Career Agent managed paths from {target}")


def _install_local_runtime(source: Path) -> tuple[Path, str]:
    """Build a frozen runtime at its final location; only the pointer is swapped."""
    relative = "runtimes/" + uuid.uuid4().hex
    runtime = source / ".career-agent" / relative
    runtime.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["UV_PROJECT_ENVIRONMENT"] = str(runtime)
    environment.pop("VIRTUAL_ENV", None)
    result = subprocess.run(
        [
            _uv(),
            "sync",
            "--project",
            str(source),
            "--frozen",
            "--no-dev",
            "--no-editable",
            "--python",
            "3.12",
        ],
        env=environment,
        check=False,
    )
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if result.returncode != 0 or not python.is_file():
        _remove_path(runtime)
        raise InstallError(
            "Dependency installation failed. Check network access and rerun setup; "
            "personal files were not changed."
        )
    (runtime / ".project-root").write_text(str(source) + "\n", encoding="utf-8")
    return python, relative


def install(args: argparse.Namespace) -> None:
    source = args.source.expanduser().resolve()
    target = args.target.expanduser().resolve()
    if target == Path(target.anchor) or target == Path.home().resolve():
        raise InstallError("Refusing to install into a filesystem root or home directory")
    if target != source:
        raise InstallError("Installation is project-local: --target must be the source folder")
    for relative in (
        ".career-agent",
        ".claude",
        ".claude/skills",
        ".career-agent/runtimes",
        ".career-agent/install-staging",
        ".career-agent/active-runtime",
        ".career-agent/install-manifest.json",
    ):
        if (target / relative).is_symlink():
            raise InstallError(f"Refusing symbolic-link installation directory: {relative}")
    with _installation_lock(target):
        _install_locked(args, source, target)


def _install_locked(args: argparse.Namespace, source: Path, target: Path) -> None:
    staging = target / ".career-agent/install-staging"
    if staging.exists() and any(staging.iterdir()):
        raise InstallError(f"Interrupted setup: preserve and inspect backups at {staging}")
    if args.uninstall:
        _uninstall(source, target, skip_python_install=args.skip_python_install)
        return

    skills = _skill_directories(source)
    if not args.allow_dirty_source:
        _reject_dirty_source(source)
    runtime_relative = None
    try:
        executable = None
        if not args.skip_python_install:
            executable, runtime_relative = _install_local_runtime(source)

        def validate_install(manifest_path: Path, _manifest: dict[str, object]) -> None:
            if args.simulate_validation_failure:
                raise InstallError("Simulated post-install validation failure")
            if args.skip_doctor:
                return
            doctor_executable = executable
            if doctor_executable is None:
                raise InstallError(
                    "Doctor requires the project runtime; do not skip its installation"
                )
            _run_doctor(doctor_executable, target, manifest_path)

        _manifest_path, manifest = _transactional_skill_install(
            source,
            target,
            skills,
            force_mirror=args.force_mirror,
            simulate_failure_after=args.simulate_failure_after,
            validate_install=validate_install,
            runtime_relative=runtime_relative,
        )
    except BaseException:
        if runtime_relative is not None:
            _remove_path(source / ".career-agent" / runtime_relative)
        raise
    mode = manifest["installed_modes"]
    print(f"Installed Career Agent V0.1 at {target} with skill modes {mode}")
    print("Next: open this folder in Codex or Claude Code and say: Help me set up my career agent.")
    print("Personal files default to workspace/. Existing global installations were not changed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--force-mirror", action="store_true")
    parser.add_argument("--allow-dirty-source", action="store_true")
    parser.add_argument("--skip-python-install", action="store_true")
    parser.add_argument("--skip-doctor", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument(
        "--simulate-failure-after",
        type=int,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--simulate-validation-failure",
        action="store_true",
        help=argparse.SUPPRESS,
    )
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
