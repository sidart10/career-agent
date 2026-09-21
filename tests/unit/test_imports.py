from __future__ import annotations

import hashlib
import os
import warnings
import zipfile
from pathlib import Path

import pytest

from career_agent.errors import CareerError, ErrorCode
from career_agent.services.imports import ExtractionStatus, ImportService

FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"


def _make_pdf(path: Path, text: str) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"builtin type (SwigPyPacked|SwigPyObject|swigvarlink).*",
            category=DeprecationWarning,
        )
        import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _make_docx(path: Path, text: str) -> None:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", document_xml)


def test_preview_stages_only_a_run_plan_and_leaves_governed_state_untouched(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "resume.txt"
    source.write_text("Name: Avery Example\nCurrent Title: Product Manager\n")
    original = source.read_bytes()

    preview = ImportService(workspace).preview([source])

    assert preview.run_id == "RUN-0001"
    assert source.read_bytes() == original
    assert not (workspace / "profile").exists()
    assert not (workspace / "resources").exists()
    preview_path = workspace / "runs" / preview.run_id / "import-preview.json"
    assert preview_path.is_file()
    if os.name != "nt":
        assert workspace.stat().st_mode & 0o777 == 0o700
        assert (workspace / "runs").stat().st_mode & 0o777 == 0o700
        assert preview_path.parent.stat().st_mode & 0o777 == 0o700
        assert preview_path.stat().st_mode & 0o777 == 0o600


def test_preview_collapses_duplicate_bytes_without_losing_source_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source_one = tmp_path / "resume-one.txt"
    source_two = tmp_path / "resume-two.txt"
    content = b"Name: Avery Example\nCurrent Title: Product Manager\n"
    source_one.write_bytes(content)
    source_two.write_bytes(content)

    preview = ImportService(workspace).preview([source_one, source_two])

    assert len(preview.source_files) == 1
    imported = preview.source_files[0]
    assert imported.checksum == hashlib.sha256(content).hexdigest()
    assert imported.source_paths == (str(source_one.resolve()), str(source_two.resolve()))
    assert len(preview.duplicates) == 1
    assert preview.duplicates[0].source_id == imported.source_id


def test_preview_extracts_text_from_pdf_and_docx_by_content(tmp_path: Path) -> None:
    pdf = tmp_path / "resume.bin"
    docx = tmp_path / "history.data"
    _make_pdf(pdf, "Name: Avery PDF")
    _make_docx(docx, "Current Title: Product Manager")

    preview = ImportService(tmp_path / "workspace").preview([pdf, docx])

    media_types = {source.media_type for source in preview.source_files}
    assert media_types == {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    assert {fact.value for fact in preview.proposed_facts} == {"Avery PDF", "Product Manager"}


def test_malformed_document_is_reported_and_preserved_on_apply(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes((FIXTURES / "malformed.pdf").read_bytes())
    service = ImportService(tmp_path / "workspace")
    preview = service.preview([source])

    assert preview.source_files[0].extraction_status is ExtractionStatus.FAILED
    result = service.apply(preview.run_id)

    stored = Path(result.imported_sources[0].stored_path)
    assert stored.read_bytes() == source.read_bytes()
    if os.name != "nt":
        assert stored.stat().st_mode & 0o777 == 0o600
        assert stored.parent.stat().st_mode & 0o777 == 0o700
        assert stored.parent.parent.stat().st_mode & 0o777 == 0o700
        assert stored.parent.parent.parent.stat().st_mode & 0o777 == 0o700


def test_embedded_instructions_remain_inert_untrusted_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "adversarial.txt"
    source.write_bytes((FIXTURES / "adversarial.txt").read_bytes())

    preview = ImportService(workspace).preview([source])
    ImportService(workspace).apply(preview.run_id)

    assert {fact.key for fact in preview.proposed_facts} == {"identity.legal_name"}
    assert not (tmp_path / "owned.txt").exists()
    assert not (workspace / "owned.txt").exists()


def test_apply_validates_every_source_before_copying_any_original(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sources = [tmp_path / "one.txt", tmp_path / "two.txt"]
    sources[0].write_text("Name: Avery Example\n")
    sources[1].write_text("Current Title: Product Manager\n")
    service = ImportService(workspace)
    preview = service.preview(sources)
    source_to_change = Path(preview.source_files[-1].source_paths[0])
    source_to_change.write_text("changed after preview")

    with pytest.raises(CareerError) as error:
        service.apply(preview.run_id)

    assert error.value.code is ErrorCode.CONFLICT
    assert not (workspace / "resources").exists()


@pytest.mark.parametrize("artifact", ["import-preview.json", "import-result.json"])
def test_apply_rejects_corrupted_run_artifacts_with_integrity_error(
    tmp_path: Path,
    artifact: str,
) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "resume.txt"
    source.write_text("Name: Avery Example\n")
    service = ImportService(workspace)
    preview = service.preview([source])
    artifact_path = workspace / "runs" / preview.run_id / artifact
    if artifact == "import-result.json":
        service.apply(preview.run_id)
    artifact_path.write_text("{not-json")

    with pytest.raises(CareerError) as error:
        service.apply(preview.run_id)

    assert error.value.code is ErrorCode.INTEGRITY_ERROR
