import logging
import os
import time

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from src.core.exceptions import (
    InputTooLargeError,
    InvalidInputError,
    NoFinancialDataError,
    NotEarningsTranscriptError,
)
from src.domains.earnings_reports.schemas import EarningsReportResult, SourceType
from src.llm.base import ExtractorClient
from src.utils.file_reader import ensure_supported, extract_text

logger = logging.getLogger(__name__)

_BYTES_PER_MB = 1024 * 1024


def _max_upload_bytes() -> int:
    return int(float(os.getenv("MAX_UPLOAD_MB", "10")) * _BYTES_PER_MB)


def _max_text_chars() -> int:
    return int(os.getenv("MAX_TEXT_CHARS", "300000"))


class ExtractionService:
    """Input (text XOR .txt/.pdf file) → validated transcript text → LLM → `EarningsReportResult`.

    Raises only `AppError` subclasses; knows nothing about HTTP status codes.
    """

    def __init__(self, client: ExtractorClient) -> None:
        self._client = client

    async def extract(
        self, *, text: str | None = None, file: UploadFile | None = None
    ) -> EarningsReportResult:
        started = time.perf_counter()
        has_text = text is not None
        has_file = file is not None and bool(file.filename)

        if has_text and has_file:
            raise InvalidInputError("Provide either 'text' or 'file', not both")
        if not has_text and not has_file:
            raise InvalidInputError("Provide either 'text' or a 'file' (.txt or .pdf)")

        source_type: SourceType
        file_name: str | None = None
        if file is not None and file.filename:
            file_name = file.filename
            extension = ensure_supported(file_name)
            content = await self._read_upload(file)
            transcript = await run_in_threadpool(extract_text, file_name, content)
            source_type = "pdf" if extension == ".pdf" else "txt"
        else:
            transcript = text or ""
            source_type = "text"

        transcript = transcript.strip()
        if not transcript:
            raise InvalidInputError("Transcript text is empty")
        max_chars = _max_text_chars()
        if len(transcript) > max_chars:
            raise InputTooLargeError(f"Extracted text exceeds {max_chars} characters")

        report, usage = await self._client.extract(transcript)

        # An empty answer must not look like success: "not a transcript" and "found nothing"
        # are reported as errors, while a real transcript with no guidance still passes.
        if not report.is_earnings_call:
            raise NotEarningsTranscriptError(
                "The text does not look like an earnings call transcript"
            )
        if report.revenue is None and not report.guidance and not report.risks:
            raise NoFinancialDataError("No revenue, guidance or risks were found in the transcript")

        logger.info(
            "extraction completed",
            extra={
                "source_type": source_type,
                "text_chars": len(transcript),
                "model": self._client.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        return EarningsReportResult(
            source_type=source_type,
            file_name=file_name,
            model=self._client.model,
            report=report,
            usage=usage,
        )

    @staticmethod
    async def _read_upload(file: UploadFile) -> bytes:
        max_bytes = _max_upload_bytes()
        too_large = InputTooLargeError(f"File exceeds {max_bytes // _BYTES_PER_MB} MB upload limit")
        if file.size is not None and file.size > max_bytes:
            raise too_large
        # Read at most one byte past the limit so an unknown-size upload is still bounded.
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise too_large
        return content
