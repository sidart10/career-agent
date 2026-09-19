from __future__ import annotations

from pathlib import Path, PurePath, PurePosixPath

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.storage.paths import (
    WorkspacePaths,
    check_filesystem_readiness,
    safe_resolve,
)


def test_workspace_paths_are_derived_from_one_resolved_root(tmp_path: Path) -> None:
    paths = WorkspacePaths.from_root(tmp_path / "workspace")

    assert paths.root == (tmp_path / "workspace").resolve()
    assert paths.profile == paths.root / "profile"
    assert paths.resources == paths.root / "resources"
    assert paths.opportunities == paths.root / "opportunities"
    assert paths.applications == paths.root / "applications"
    assert paths.runs == paths.root / "runs"
    assert paths.journals == paths.root / "journals"


@pytest.mark.parametrize(
    "relative",
    [Path("/tmp/escape.json"), PurePath("..", "escape.json"), PurePath("safe", "..", "escape")],
)
def test_safe_resolve_rejects_absolute_and_parent_paths(tmp_path: Path, relative: PurePath) -> None:
    root = tmp_path / "workspace"

    with pytest.raises(CareerError) as error:
        safe_resolve(root, relative)

    assert error.value.code is ErrorCode.UNSAFE_PATH
    assert not root.exists()


def test_safe_resolve_rejects_symlink_that_leaves_workspace(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(CareerError) as error:
        safe_resolve(root, PurePath("linked", "manifest.json"))

    assert error.value.code is ErrorCode.UNSAFE_PATH
    assert not (outside / "manifest.json").exists()


def test_safe_resolve_rejects_case_fold_collision(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "Applications").mkdir(parents=True)

    with pytest.raises(CareerError, match="case-fold"):
        safe_resolve(root, PurePath("applications", "manifest.json"))


@pytest.mark.parametrize(
    "name",
    ["CON", "aux.txt", "LPT1.json", "trailing. ", "field:name", "field\\name"],
)
def test_safe_resolve_rejects_windows_reserved_components(tmp_path: Path, name: str) -> None:
    with pytest.raises(CareerError, match="Windows"):
        safe_resolve(tmp_path / "workspace", PurePosixPath("applications", name))


def test_safe_resolve_returns_safe_path_without_creating_it(tmp_path: Path) -> None:
    root = tmp_path / "workspace"

    resolved = safe_resolve(root, PurePath("applications", "APP-2026-0001", "manifest.json"))

    assert resolved == root.resolve() / "applications" / "APP-2026-0001" / "manifest.json"
    assert not root.exists()


@pytest.mark.parametrize("filesystem_type", ["nfs", "smbfs", "fuse.sshfs", "unknown"])
def test_readiness_rejects_filesystems_without_supported_atomicity(
    tmp_path: Path, filesystem_type: str
) -> None:
    root = tmp_path / "workspace"

    with pytest.raises(CareerError) as error:
        check_filesystem_readiness(root, filesystem_type=filesystem_type)

    assert error.value.code is ErrorCode.NOT_READY
    assert not root.exists()


def test_readiness_rejects_known_synchronization_provider_path(tmp_path: Path) -> None:
    root = tmp_path / "Dropbox" / "career"

    with pytest.raises(CareerError) as error:
        check_filesystem_readiness(root, filesystem_type="apfs")

    assert error.value.code is ErrorCode.NOT_READY
    assert not root.exists()


def test_readiness_reports_directory_fsync_capability_without_mutating_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"

    readiness = check_filesystem_readiness(root, filesystem_type="apfs")

    assert readiness.filesystem_type == "apfs"
    assert isinstance(readiness.directory_fsync_supported, bool)
    assert not root.exists()


def test_readiness_detects_the_current_supported_local_filesystem(tmp_path: Path) -> None:
    readiness = check_filesystem_readiness(tmp_path / "workspace")

    assert readiness.filesystem_type != "unknown"
