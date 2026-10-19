import logging
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import AppError
from src.core.middleware import REQUEST_ID_HEADER
from src.core.schemas import ErrorDetail, ErrorResponse, ResponseMeta

logger = logging.getLogger(__name__)


def _validation_message(exc: RequestValidationError) -> str:
    # Only field locations + messages: never echo submitted values (they may be transcript text).
    parts = [
        f"{'.'.join(str(loc) for loc in error.get('loc', ()))}: {error.get('msg', 'invalid')}"
        for error in exc.errors()
    ]
    return "Invalid request: " + "; ".join(parts) if parts else "Invalid request"


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The single handler that turns any exception into an `ErrorResponse`."""
    meta = ResponseMeta.from_request(request)

    if isinstance(exc, AppError):
        logger.warning("%s: %s", exc.code, exc.message, extra={"error_code": exc.code})
        status_code, code, message = exc.status_code, exc.code, exc.message
    elif isinstance(exc, RequestValidationError):
        status_code, code, message = 422, "VALIDATION_ERROR", _validation_message(exc)
        logger.warning("VALIDATION_ERROR: %s", message, extra={"error_code": code})
    elif isinstance(exc, StarletteHTTPException):
        status_code = exc.status_code
        code = HTTPStatus(status_code).name
        message = str(exc.detail)
    else:
        logger.exception("Unhandled error", extra={"error_code": "INTERNAL_ERROR"})
        status_code, code, message = 500, "INTERNAL_ERROR", "Unexpected server error"

    body = ErrorResponse(error=ErrorDetail(code=code, message=message), meta=meta)
    headers = {REQUEST_ID_HEADER: meta.request_id} if meta.request_id else None
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)
