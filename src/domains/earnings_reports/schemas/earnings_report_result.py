from typing import Literal

from pydantic import BaseModel, Field

from src.domains.earnings_reports.schemas.llm_extraction import EarningsReport

SourceType = Literal["text", "txt", "pdf"]


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class EarningsReportResult(BaseModel):
    """Payload placed in `ApiResponse.data` by the extract endpoint."""

    source_type: SourceType
    file_name: str | None = None
    model: str
    report: EarningsReport
    usage: TokenUsage
