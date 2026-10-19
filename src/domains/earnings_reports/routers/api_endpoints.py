from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from src.core.dependencies import get_extraction_service
from src.core.schemas import ApiResponse, ErrorResponse, ResponseMeta
from src.domains.earnings_reports.schemas import EarningsReportResult
from src.domains.earnings_reports.services.extraction_service import ExtractionService

router = APIRouter(prefix="/earnings-reports", tags=["earnings-reports"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        400: "Both or neither of text/file provided, or empty text",
        413: "Upload or text too large",
        415: "Unsupported file type",
        422: "Unreadable PDF or invalid request",
        502: "LLM extraction failed",
        504: "LLM timed out",
    }.items()
}


@router.post(
    "/extract",
    response_model=ApiResponse[EarningsReportResult],
    responses=_ERROR_RESPONSES,
    summary="Extract revenue, guidance and risks from an earnings call transcript",
)
async def extract_earnings_report(
    request: Request,
    service: Annotated[ExtractionService, Depends(get_extraction_service)],
    text: Annotated[str | None, Form(description="Raw transcript text")] = None,
    file: Annotated[UploadFile | None, File(description="Transcript as .txt or .pdf")] = None,
) -> ApiResponse[EarningsReportResult]:
    """Send exactly one of `text` or `file` as multipart/form-data."""
    result = await service.extract(text=text, file=file)
    return ApiResponse(data=result, meta=ResponseMeta.from_request(request))
