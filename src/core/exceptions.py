class AppError(Exception):
    """Base class for every expected application error.

    Subclasses set `status_code` + `code`; the global handler renders them as `ErrorResponse`.
    Messages are returned to the client, so they must never contain transcript content or secrets.
    """

    status_code: int = 500
    code: str = "APP_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(AppError):
    status_code = 400
    code = "INVALID_INPUT"


class InputTooLargeError(AppError):
    status_code = 413
    code = "INPUT_TOO_LARGE"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "UNSUPPORTED_FILE_TYPE"


class FileParseError(AppError):
    status_code = 422
    code = "FILE_PARSE_FAILED"


class NotEarningsTranscriptError(AppError):
    status_code = 422
    code = "NOT_EARNINGS_TRANSCRIPT"


class NoFinancialDataError(AppError):
    status_code = 422
    code = "NO_FINANCIAL_DATA"


class ExtractionFailedError(AppError):
    """The LLM provider failed (API error, network, bad response)."""

    status_code = 502
    code = "EXTRACTION_FAILED"


class ExtractionInvalidError(AppError):
    """The model answered, but its output kept failing validation after every retry."""

    status_code = 502
    code = "EXTRACTION_INVALID"


class LLMTimeoutError(AppError):
    status_code = 504
    code = "LLM_TIMEOUT"
