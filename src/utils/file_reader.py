"""Convert uploaded file bytes to plain text. Knows nothing about HTTP or the LLM.

Functions here are synchronous and CPU-bound (PDF parsing): call them via a threadpool
from async code.
"""

import io
import logging
from pathlib import PurePath

from pypdf import PdfReader

from src.core.exceptions import FileParseError, UnsupportedFileTypeError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({".txt", ".pdf"})


def get_extension(file_name: str) -> str:
    return PurePath(file_name).suffix.lower()


def ensure_supported(file_name: str) -> str:
    """Return the lower-cased extension, or raise `UnsupportedFileTypeError`."""
    extension = get_extension(file_name)
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{extension or 'none'}'. Allowed: {allowed}"
        )
    return extension


def read_txt(content: bytes) -> str:
    """Decode UTF-8 (BOM tolerated), falling back to latin-1, which never fails."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def read_pdf(content: bytes) -> str:
    """Extract text page by page. Corrupt or text-less (scanned) PDFs raise `FileParseError`."""
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises many unrelated exception types on malformed input
        logger.warning("PDF parsing failed", extra={"error_type": type(exc).__name__})
        raise FileParseError("Could not read PDF file; it may be corrupt or encrypted") from exc

    text = "\n\n".join(page.strip() for page in pages if page.strip())
    if not text:
        raise FileParseError(
            "PDF contains no extractable text (it may be a scanned image); "
            "send a text-based PDF or the transcript text"
        )
    return text


def extract_text(file_name: str, content: bytes) -> str:
    """Dispatch on extension: `.txt` → decode, `.pdf` → pypdf."""
    extension = ensure_supported(file_name)
    if extension == ".pdf":
        return read_pdf(content)
    return read_txt(content)
