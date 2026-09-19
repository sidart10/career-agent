from __future__ import annotations

from pathlib import Path

from career_agent.storage.checksums import sha256_file


def test_sha256_file_returns_lowercase_digest_for_file_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abc")

    assert sha256_file(source) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
