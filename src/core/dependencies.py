"""All dependency-injection providers. FastAPI `Depends` only; override in tests via
`app.dependency_overrides`."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.domains.earnings_reports.services.extraction_service import ExtractionService
from src.llm.anthropic_client import AnthropicExtractorClient
from src.llm.base import ExtractorClient


@lru_cache(maxsize=1)
def get_llm_client() -> ExtractorClient:
    """Singleton: one HTTP connection pool for the process, created on first use."""
    return AnthropicExtractorClient()


def get_extraction_service(
    client: Annotated[ExtractorClient, Depends(get_llm_client)],
) -> ExtractionService:
    return ExtractionService(client)
