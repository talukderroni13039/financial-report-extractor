import logging
import os

import anthropic
import instructor
from anthropic import AsyncAnthropic

from src.core.exceptions import ExtractionFailedError, LLMTimeoutError
from src.domains.earnings_reports.prompts.extraction_prompt import (
    EXTRACTION_SYSTEM_PROMPT,
    build_user_message,
)
from src.domains.earnings_reports.schemas import EarningsReport, TokenUsage

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-5-5"


def _find_cause[E: BaseException](exc: BaseException, error_type: type[E]) -> E | None:
    """Instructor wraps provider errors in InstructorRetryException; walk the cause chain."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, error_type):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


class AnthropicExtractorClient:
    """`ExtractorClient` backed by Claude via Instructor (tool-mode structured output)."""

    def __init__(
        self,
        client: AsyncAnthropic | None = None,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._model: str = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
        self._max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", "4000"))
        # Instructor semantics: max_retries=N allows N re-asks after the first attempt.
        self._max_retries = (
            max_retries if max_retries is not None else int(os.getenv("LLM_MAX_RETRIES", "2"))
        )
        raw_client = client or AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        )
        self._client = instructor.from_anthropic(raw_client)

    @property
    def model(self) -> str:
        return self._model

    async def extract(self, text: str) -> tuple[EarningsReport, TokenUsage]:
        try:
            report, completion = await self._client.messages.create_with_completion(
                model=self._model,
                max_tokens=self._max_tokens,
                max_retries=self._max_retries,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(text)}],
                response_model=EarningsReport,
            )
        except Exception as exc:
            if _find_cause(exc, anthropic.APITimeoutError) is not None:
                raise LLMTimeoutError("The language model did not respond in time") from exc
            api_error = _find_cause(exc, anthropic.APIError)
            logger.error(
                "LLM extraction failed",
                extra={
                    "error_type": type(api_error or exc).__name__,
                    "status_code": getattr(api_error, "status_code", None),
                },
            )
            raise ExtractionFailedError(
                "Could not extract a valid earnings report from the transcript"
            ) from exc

        usage = TokenUsage(
            input_tokens=completion.usage.input_tokens,
            output_tokens=completion.usage.output_tokens,
        )
        return report, usage
