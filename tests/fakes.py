"""Test doubles: `FakeExtractorClient` satisfies `ExtractorClient` with zero API calls."""

import json
from pathlib import Path

from src.domains.earnings_reports.schemas import EarningsReport, TokenUsage

LLM_RESPONSE_FIXTURE = Path(__file__).parent / "fixtures" / "llm_response.json"


def load_fixture_response() -> tuple[EarningsReport, TokenUsage, str]:
    """The real LLM response captured once by scripts/capture_llm_fixture.py."""
    data = json.loads(LLM_RESPONSE_FIXTURE.read_text(encoding="utf-8"))
    return (
        EarningsReport.model_validate(data["report"]),
        TokenUsage.model_validate(data["usage"]),
        str(data["model"]),
    )


class FakeExtractorClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.report, self.usage, self._model = load_fixture_response()
        self.error = error
        self.calls: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    async def extract(self, text: str) -> tuple[EarningsReport, TokenUsage]:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return self.report, self.usage
