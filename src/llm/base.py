from typing import Protocol

from src.domains.earnings_reports.schemas import EarningsReport, TokenUsage


class ExtractorClient(Protocol):
    """What the extraction service needs from an LLM provider. Implementations map provider
    errors to `LLMTimeoutError` / `ExtractionFailedError`."""

    @property
    def model(self) -> str: ...

    async def extract(self, text: str) -> tuple[EarningsReport, TokenUsage]: ...
