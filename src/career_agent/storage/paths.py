"""Workspace path derivation and escape prevention."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePath

from career_agent.errors import CareerError, ErrorCode

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_SUPPORTED_LOCAL_FILESYSTEMS = {
    "apfs",
    "btrfs",
    "exfat",
    "ext2",
    "ext3",
    "ext4",
    "fat32",
    "hfs",
    "hfs+",
    "ntfs",
    "overlay",
    "refs",
    "tmpfs",
    "ufs",
    "xfs",
    "zfs",
}
_UNSUPPORTED_NETWORK_FILESYSTEMS = {
    "9p",
    "afpfs",
    "cifs",
    "davfs",
    "fuse.sshfs",
    "nfs",
    "nfs4",
    "smbfs",
    "sshfs",
}
_SYNCHRONIZATION_COMPONENTS = {
    "dropbox",
    "google drive",
    "icloud drive",
    "mobile documents",
    "onedrive",
}


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    profile: Path
    resources: Path
    opportunities: Path
    applications: Path
    runs: Path
    journals: Path

    @classmethod
    def from_root(cls, root: Path) -> WorkspacePaths:
        resolved_root = root.resolve(strict=False)
        return cls(
            root=resolved_root,
            profile=resolved_root / "profile",
            resources=resolved_root / "resources",
            opportunities=resolved_root / "opportunities",
            applications=resolved_root / "applications",
            runs=resolved_root / "runs",
            journals=resolved_root / "journals",
        )


@dataclass(frozen=True)
class FilesystemReadiness:
    filesystem_type: str
    directory_fsync_supported: bool


def _unsafe(message: str, **details: object) -> CareerError:
    return CareerError(ErrorCode.UNSAFE_PATH, message, dict(details))


def _validate_component(component: str) -> None:
    if component in {"", ".", ".."}:
        raise _unsafe("Path traversal is not allowed", component=component)
    if component.endswith((" ", ".")):
        raise _unsafe("Path component is invalid on Windows", component=component)
    if any(character in component for character in '<>:"\\|?*') or any(
        ord(character) < 32 for character in component
    ):
        raise _unsafe("Path component is invalid on Windows", component=component)
    base = component.split(".", 1)[0].upper()
    if base in _WINDOWS_RESERVED or re.fullmatch(r"[A-Za-z]:", component):
        raise _unsafe("Path component is reserved on Windows", component=component)


def _reject_case_fold_collision(parent: Path, component: str) -> None:
    if not parent.is_dir():
        return
    for child in parent.iterdir():
        if child.name != component and child.name.casefold() == component.casefold():
            raise _unsafe(
                "Path has a case-fold collision with an existing entry",
                requested=component,
                existing=child.name,
            )


def safe_resolve(root: Path, relative: PurePath, *, allow_symlink: bool = False) -> Path:
    """Resolve a relative workspace path without allowing ambiguous or escaped paths."""

    if relative.is_absolute() or relative.anchor:
        raise _unsafe("Absolute paths are not allowed", path=str(relative))

    components = relative.parts
    for component in components:
        _validate_component(component)

    resolved_root = root.resolve(strict=False)
    candidate = resolved_root
    for component in components:
        _reject_case_fold_collision(candidate, component)
        candidate = candidate / component
        if candidate.is_symlink() and not allow_symlink:
            raise _unsafe("Symbolic links are not allowed in governed paths", path=str(candidate))

    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise _unsafe("Resolved path leaves the workspace", path=str(relative))
    return resolved_candidate


def _existing_ancestor(path: Path) -> Path:
    candidate = path.resolve(strict=False)
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _linux_filesystem_type(path: Path) -> str:
    try:
        lines = Path("/proc/self/mountinfo").read_text().splitlines()
    except OSError:
        return "unknown"
    target = str(path)
    matches: list[tuple[int, str]] = []
    for line in lines:
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        fields = before.split()
        filesystem_fields = after.split()
        if len(fields) < 5 or not filesystem_fields:
            continue
        mount_point = (
            fields[4]
            .replace(r"\040", " ")
            .replace(r"\011", "\t")
            .replace(r"\012", "\n")
            .replace(r"\134", "\\")
        )
        if target == mount_point or target.startswith(f"{mount_point.rstrip('/')}/"):
            matches.append((len(mount_point), filesystem_fields[0]))
    return max(matches, default=(0, "unknown"))[1]


def _windows_filesystem_type(path: Path) -> str:
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    volume_path = ctypes.create_unicode_buffer(260)
    filesystem_name = ctypes.create_unicode_buffer(260)
    if not kernel32.GetVolumePathNameW(str(path), volume_path, len(volume_path)):
        return "unknown"
    if not kernel32.GetVolumeInformationW(
        volume_path.value,
        None,
        0,
        None,
        None,
        None,
        filesystem_name,
        len(filesystem_name),
    ):
        return "unknown"
    return filesystem_name.value


def _bsd_filesystem_type(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["mount"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    target = str(path)
    matches: list[tuple[int, str]] = []
    for line in completed.stdout.splitlines():
        mounted, separator, options = line.rpartition(" (")
        if not separator or not options.endswith(")"):
            continue
        _, on_separator, mount_point = mounted.partition(" on ")
        if not on_separator:
            continue
        mount_point = mount_point.replace(r"\040", " ")
        if target == mount_point or target.startswith(f"{mount_point.rstrip('/')}/"):
            filesystem_type = options[:-1].split(",", 1)[0]
            matches.append((len(mount_point), filesystem_type))
    return max(matches, default=(0, "unknown"))[1]


def _detect_filesystem_type(path: Path) -> str:
    system = platform.system()
    if system == "Linux":
        return _linux_filesystem_type(path)
    if system == "Windows":
        return _windows_filesystem_type(path)
    if system in {"Darwin", "FreeBSD"}:
        return _bsd_filesystem_type(path)
    return "unknown"


def check_filesystem_readiness(
    root: Path,
    *,
    filesystem_type: str | None = None,
) -> FilesystemReadiness:
    """Refuse roots where the storage kernel cannot promise local atomic replacement."""

    resolved_root = root.resolve(strict=False)
    casefolded_parts = {part.casefold() for part in resolved_root.parts}
    sync_component = casefolded_parts.intersection(_SYNCHRONIZATION_COMPONENTS)
    if sync_component:
        raise CareerError(
            ErrorCode.NOT_READY,
            "Synchronized workspace roots are not supported",
            {"provider_path_component": sorted(sync_component)[0]},
        )

    detected = (filesystem_type or _detect_filesystem_type(_existing_ancestor(root))).casefold()
    if detected in _UNSUPPORTED_NETWORK_FILESYSTEMS or detected not in _SUPPORTED_LOCAL_FILESYSTEMS:
        raise CareerError(
            ErrorCode.NOT_READY,
            "Workspace filesystem does not provide supported local atomicity",
            {"filesystem_type": detected},
        )
    return FilesystemReadiness(
        filesystem_type=detected,
        directory_fsync_supported=os.name != "nt" and hasattr(os, "O_DIRECTORY"),
    )
