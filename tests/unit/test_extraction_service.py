import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from src.core.dependencies import get_extraction_service
from src.core.exceptions import (
    ExtractionFailedError,
    FileParseError,
    InputTooLargeError,
    InvalidInputError,
    LLMTimeoutError,
    UnsupportedFileTypeError,
)
from src.domains.earnings_reports.services.extraction_service import ExtractionService
from tests.fakes import FakeExtractorClient
from tests.pdf_factory import build_pdf

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _upload(name: str, content: bytes, *, declare_size: bool = True) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content), filename=name, size=len(content) if declare_size else None
    )


@pytest.fixture
def fake_client() -> FakeExtractorClient:
    return FakeExtractorClient()


@pytest.fixture
def service(fake_client: FakeExtractorClient) -> ExtractionService:
    return ExtractionService(fake_client)


async def test_text_input_ok(service: ExtractionService, fake_client: FakeExtractorClient) -> None:
    result = await service.extract(text="  Revenue was $4.2 billion.  ")

    assert result.source_type == "text"
    assert result.file_name is None
    assert result.model == "claude-haiku-5-5"
    assert result.report == fake_client.report
    assert result.usage == fake_client.usage
    assert fake_client.calls == ["Revenue was $4.2 billion."]


async def test_txt_file_input_ok(
    service: ExtractionService, fake_client: FakeExtractorClient
) -> None:
    content = (FIXTURES / "sample_transcript.txt").read_bytes()

    result = await service.extract(file=_upload("q3.txt", content))

    assert result.source_type == "txt"
    assert result.file_name == "q3.txt"
    assert "Acme Corp" in fake_client.calls[0]


async def test_pdf_file_input_ok(
    service: ExtractionService, fake_client: FakeExtractorClient
) -> None:
    content = (FIXTURES / "sample_transcript.pdf").read_bytes()

    result = await service.extract(file=_upload("Q3_Call.PDF", content))

    assert result.source_type == "pdf"
    assert result.file_name == "Q3_Call.PDF"
    assert "$4.2 billion" in fake_client.calls[0]


async def test_both_inputs_rejected(service: ExtractionService) -> None:
    with pytest.raises(InvalidInputError, match="not both"):
        await service.extract(text="hello", file=_upload("a.txt", b"hi"))


async def test_neither_input_rejected(service: ExtractionService) -> None:
    with pytest.raises(InvalidInputError):
        await service.extract()


async def test_upload_without_filename_counts_as_no_file(service: ExtractionService) -> None:
    with pytest.raises(InvalidInputError):
        await service.extract(file=_upload("", b""))


@pytest.mark.parametrize("text", ["", "   \n\t "])
async def test_empty_text_rejected(service: ExtractionService, text: str) -> None:
    with pytest.raises(InvalidInputError, match="empty"):
        await service.extract(text=text)


async def test_empty_txt_file_rejected(service: ExtractionService) -> None:
    with pytest.raises(InvalidInputError, match="empty"):
        await service.extract(file=_upload("empty.txt", b"  "))


async def test_docx_rejected(service: ExtractionService, fake_client: FakeExtractorClient) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        await service.extract(file=_upload("report.docx", b"PK\x03\x04"))
    assert fake_client.calls == []


async def test_scanned_pdf_rejected(service: ExtractionService) -> None:
    with pytest.raises(FileParseError):
        await service.extract(file=_upload("scan.pdf", build_pdf([""])))


@pytest.mark.parametrize("declare_size", [True, False])
async def test_oversize_upload_rejected(
    service: ExtractionService,
    fake_client: FakeExtractorClient,
    monkeypatch: pytest.MonkeyPatch,
    declare_size: bool,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")  # ~1 KB
    content = b"a" * 2_000

    with pytest.raises(InputTooLargeError, match="upload limit"):
        await service.extract(file=_upload("big.txt", content, declare_size=declare_size))
    assert fake_client.calls == []


async def test_oversize_text_rejected(
    service: ExtractionService, fake_client: FakeExtractorClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_TEXT_CHARS", "10")

    with pytest.raises(InputTooLargeError, match="exceeds 10 characters"):
        await service.extract(text="x" * 11)
    assert fake_client.calls == []


async def test_oversize_extracted_file_text_rejected(
    service: ExtractionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_TEXT_CHARS", "10")

    with pytest.raises(InputTooLargeError):
        await service.extract(file=_upload("a.txt", b"y" * 50))


async def test_llm_timeout_propagates() -> None:
    service = ExtractionService(FakeExtractorClient(error=LLMTimeoutError("timed out")))

    with pytest.raises(LLMTimeoutError):
        await service.extract(text="Revenue was $1.")


async def test_llm_failure_propagates() -> None:
    service = ExtractionService(FakeExtractorClient(error=ExtractionFailedError("failed")))

    with pytest.raises(ExtractionFailedError):
        await service.extract(text="Revenue was $1.")


def test_get_extraction_service_wraps_client(fake_client: FakeExtractorClient) -> None:
    assert isinstance(get_extraction_service(fake_client), ExtractionService)
