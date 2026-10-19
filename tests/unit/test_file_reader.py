from pathlib import Path

import pytest

from src.core.exceptions import FileParseError, UnsupportedFileTypeError
from src.utils.file_reader import (
    ALLOWED_EXTENSIONS,
    ensure_supported,
    extract_text,
    read_pdf,
    read_txt,
)
from tests.pdf_factory import build_pdf

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_allowed_extensions() -> None:
    assert {".txt", ".pdf"} == ALLOWED_EXTENSIONS


def test_txt_utf8_is_decoded() -> None:
    assert read_txt("Revenue €4.2 billion".encode()) == "Revenue €4.2 billion"


def test_txt_utf8_bom_is_stripped() -> None:
    assert read_txt(b"\xef\xbb\xbfHello") == "Hello"


def test_txt_latin1_fallback() -> None:
    content = "Café revenue £3m".encode("latin-1")

    assert read_txt(content) == "Café revenue £3m"


def test_valid_pdf_text_is_extracted() -> None:
    text = read_pdf((FIXTURES / "sample_transcript.pdf").read_bytes())

    assert "Acme Corp" in text
    assert "$4.2 billion" in text


def test_multi_page_pdf_joins_pages() -> None:
    text = read_pdf(build_pdf(["Page one revenue", "", "Page three risks"]))

    assert text == "Page one revenue\n\nPage three risks"


def test_scanned_or_empty_pdf_raises_file_parse_error() -> None:
    with pytest.raises(FileParseError, match="no extractable text"):
        read_pdf(build_pdf(["", ""]))


def test_corrupt_pdf_raises_file_parse_error() -> None:
    with pytest.raises(FileParseError, match="Could not read PDF"):
        read_pdf(b"%PDF-1.4 this is definitely not a real pdf")


def test_extract_text_dispatches_on_extension_case_insensitively() -> None:
    assert extract_text("NOTES.TXT", b"hello") == "hello"
    assert "Acme Corp" in extract_text(
        "call.PDF", (FIXTURES / "sample_transcript.pdf").read_bytes()
    )


@pytest.mark.parametrize("file_name", ["report.docx", "transcript", "image.png", "a.pdf.exe"])
def test_unsupported_extension_raises(file_name: str) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        ensure_supported(file_name)
