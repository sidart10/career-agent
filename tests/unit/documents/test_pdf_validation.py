from __future__ import annotations

from pathlib import Path

import fitz

from career_agent.documents.pdf_validation import PdfValidator, ValidationRequest


def write_pdf(path: Path, pages: list[list[tuple[float, float, str]]]) -> None:
    document = fitz.open()
    for entries in pages:
        page = document.new_page(width=612, height=792)
        for x, y, text in entries:
            page.insert_text((x, y), text, fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()


def valid_text() -> str:
    return (
        "Avery Candidate | avery@example.test | 555-0100\n"
        "EXPERIENCE\nSenior Product Manager at Example Labs\n"
        "Led measurement products and partnered with engineering teams.\n"
        "Delivered measurable customer outcomes across multiple launches.\n"
        "EDUCATION\nExample University, Bachelor of Science"
    )


def test_valid_pdf_preserves_raw_ats_text_and_passes_mechanical_checks(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "applications" / "APP-2026-0001" / "drafts" / "resume.pdf"
    text = valid_text()
    write_pdf(artifact, [[(72, 72, line) for line in text.splitlines()]])

    report = PdfValidator(tmp_path).validate(
        "APP-2026-0001",
        artifact,
        ValidationRequest(
            required_fields=("avery@example.test", "555-0100"),
            logical_order=("EXPERIENCE", "EDUCATION"),
            minimum_text_characters=120,
            maximum_pages=2,
        ),
    )

    assert report.passed is True
    assert report.page_count == 1
    assert (tmp_path / report.ats_text_path).read_text() == report.raw_ats_text
    assert report.normalized_ats_text != ""


def test_unreadable_empty_placeholder_and_wrong_contact_cannot_pass(
    tmp_path: Path,
) -> None:
    validator = PdfValidator(tmp_path)
    unreadable = tmp_path / "applications" / "APP-2026-0001" / "drafts" / "bad.pdf"
    unreadable.parent.mkdir(parents=True)
    unreadable.write_bytes(b"not a pdf")
    empty = unreadable.with_name("empty.pdf")
    write_pdf(empty, [[]])
    placeholder = unreadable.with_name("placeholder.pdf")
    write_pdf(
        placeholder,
        [[(72, 72, "Avery Candidate TODO replace@example.test EXPERIENCE EDUCATION")]],
    )

    unreadable_report = validator.validate(
        "APP-2026-0001", unreadable, ValidationRequest(required_fields=("email",))
    )
    empty_report = validator.validate(
        "APP-2026-0001", empty, ValidationRequest(required_fields=("email",))
    )
    placeholder_report = validator.validate(
        "APP-2026-0001",
        placeholder,
        ValidationRequest(required_fields=("avery@example.test",)),
    )

    assert unreadable_report.passed is False
    assert empty_report.passed is False
    assert placeholder_report.passed is False
    assert any(not check.passed for check in placeholder_report.placeholders)
    assert any(not check.passed for check in placeholder_report.required_fields)


def test_thin_page_stranded_heading_footer_collision_and_order_are_reported(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "applications" / "APP-2026-0001" / "drafts" / "layout.pdf"
    write_pdf(
        artifact,
        [
            [
                (72, 72, "EDUCATION before experience"),
                (72, 730, "EXPERIENCE"),
                (72, 785, "footer collision"),
            ],
            [(72, 72, "thin")],
        ],
    )

    report = PdfValidator(tmp_path).validate(
        "APP-2026-0001",
        artifact,
        ValidationRequest(
            logical_order=("EXPERIENCE", "EDUCATION"),
            minimum_text_characters=100,
            maximum_pages=2,
        ),
    )

    assert report.passed is False
    failing_names = {
        check.name for check in (*report.layout, *report.logical_order) if not check.passed
    }
    assert {"thin_page", "stranded_heading", "footer_collision", "logical_order"} <= failing_names
