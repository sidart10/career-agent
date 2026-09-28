from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from career_agent.resource_files import read_schema, read_text_resource

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_resources_are_available_through_package_api() -> None:
    schema = json.loads(read_schema("profile-fact.schema.json"))
    template = read_text_resource("templates/resume/default/resume.tex")

    assert schema["title"] == "ProfileFact"
    assert "\\documentclass" in template


def test_wheel_and_sdist_have_explicit_public_contents(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "build", "--no-sources", "--out-dir", str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next(tmp_path.glob("*.whl"))
    source_distribution = next(tmp_path.glob("*.tar.gz"))

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
        wheel_payload = b"\n".join(archive.read(name) for name in wheel_names)
    assert "career_agent/resources/schemas/profile-fact.schema.json" in wheel_names
    assert "career_agent/resources/templates/resume/default/resume.tex" in wheel_names
    assert "career_agent/THIRD_PARTY_NOTICES.md" in wheel_names

    with tarfile.open(source_distribution) as archive:
        sdist_names = {member.name for member in archive.getmembers()}
        sdist_payload = b"\n".join(
            stream.read()
            for member in archive.getmembers()
            if member.isfile() and (stream := archive.extractfile(member)) is not None
        )
    assert any(
        name.endswith("career_agent/resources/schemas/profile-fact.schema.json")
        for name in sdist_names
    )
    assert any(
        name.endswith("career_agent/resources/templates/resume/default/resume.tex")
        for name in sdist_names
    )
    assert any(name.endswith("THIRD_PARTY_NOTICES.md") for name in sdist_names)
    assert any(name.endswith("/README.md") for name in sdist_names)
    assert any(name.endswith("/scripts/career.sh") for name in sdist_names)
    assert any(name.endswith("/scripts/career.ps1") for name in sdist_names)
    forbidden = (
        "/.hypothesis/",
        "/.scratch/",
        "/.pytest_cache/",
        "/.mypy_cache/",
        "/workspace/",
        "/.career-agent/",
        "/.venv/",
    )
    assert not any(marker in name for name in sdist_names for marker in forbidden)
    for payload in (wheel_payload, sdist_payload):
        lowered = payload.lower()
        assert b"/users/sid/" not in lowered
        assert b"sid.dani@" not in lowered
        assert b"sk-proj-" not in lowered

    environment = tmp_path / "isolated"
    created = subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(environment)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    installed = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    career = environment / ("Scripts/career.exe" if os.name == "nt" else "bin/career")
    version = subprocess.run(
        [str(career), "version", "--json"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "CAREER_WORKSPACE": str(tmp_path / "external-workspace")},
    )
    assert version.returncode == 0, version.stdout + version.stderr
    assert json.loads(version.stdout)["data"]["cli_version"] == "0.1.0"
    resources = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from career_agent.resource_files import read_schema, read_text_resource; "
                "assert 'ProfileFact' in read_schema('profile-fact.schema.json'); "
                "assert r'\\documentclass' in "
                "read_text_resource('templates/resume/default/resume.tex')"
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert resources.returncode == 0, resources.stdout + resources.stderr
