"""AnthropicExtractorClient with the Instructor call mocked out: no network, no API cost."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import anthropic
import httpx2
import pytest
from anthropic import AsyncAnthropic
from instructor.core import InstructorRetryException
from instructor.v2.core.errors import FailedAttempt
from pydantic import ValidationError

from src.core.dependencies import get_llm_client
from src.core.exceptions import ExtractionFailedError, ExtractionInvalidError, LLMTimeoutError
from src.domains.earnings_reports.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT
from src.domains.earnings_reports.schemas import Revenue
from src.llm.anthropic_client import DEFAULT_MODEL, AnthropicExtractorClient
from tests.fakes import load_fixture_response

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _client_with_mock(mock: AsyncMock, **kwargs: Any) -> AnthropicExtractorClient:
    client = AnthropicExtractorClient(AsyncAnthropic(api_key="test-key"), **kwargs)
    client._client.messages.create_with_completion = mock  # type: ignore[method-assign]
    return client


def _retry_exception(
    cause: Exception, failed: list[FailedAttempt] | None = None
) -> InstructorRetryException:
    try:
        raise InstructorRetryException(
            str(cause), n_attempts=1, total_usage=0, create_kwargs={}, failed_attempts=failed
        ) from cause
    except InstructorRetryException as exc:
        return exc


async def test_extract_returns_report_and_usage() -> None:
    report, _, _ = load_fixture_response()
    completion = SimpleNamespace(usage=SimpleNamespace(input_tokens=120, output_tokens=30))
    mock = AsyncMock(return_value=(report, completion))
    client = _client_with_mock(mock, model="claude-test", max_tokens=123, max_retries=1)

    result, usage = await client.extract("Revenue was $1 billion.")

    assert result == report
    assert (usage.input_tokens, usage.output_tokens) == (120, 30)
    kwargs = mock.await_args.kwargs
    assert kwargs["model"] == "claude-test"
    assert kwargs["max_tokens"] == 123
    assert kwargs["max_retries"] == 1
    assert kwargs["system"] == EXTRACTION_SYSTEM_PROMPT
    assert kwargs["messages"][0]["content"].startswith("<transcript>")
    assert "Revenue was $1 billion." in kwargs["messages"][0]["content"]
    assert kwargs["context"] == {"source_text": "Revenue was $1 billion."}


def test_defaults_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "claude-env-model")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")

    client = AnthropicExtractorClient(AsyncAnthropic(api_key="test-key"))

    assert client.model == "claude-env-model"
    assert client._max_retries == 0


def test_default_model_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    assert AnthropicExtractorClient().model == DEFAULT_MODEL == "claude-haiku-5-5"


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APITimeoutError(request=_REQUEST),
        _retry_exception(anthropic.APITimeoutError(request=_REQUEST)),
    ],
)
async def test_timeout_maps_to_llm_timeout_error(error: Exception) -> None:
    client = _client_with_mock(AsyncMock(side_effect=error))

    with pytest.raises(LLMTimeoutError):
        await client.extract("text")


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=_REQUEST),
        _retry_exception(anthropic.APIConnectionError(request=_REQUEST)),
        _retry_exception(ValueError("unexpected failure")),
    ],
)
async def test_api_failures_map_to_extraction_failed(error: Exception) -> None:
    client = _client_with_mock(AsyncMock(side_effect=error))

    with pytest.raises(ExtractionFailedError):
        await client.extract("text")


def test_get_llm_client_is_a_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_llm_client.cache_clear()
    try:
        first = get_llm_client()
        assert first is get_llm_client()
        assert isinstance(first, AnthropicExtractorClient)
    finally:
        get_llm_client.cache_clear()


def _validation_error() -> ValidationError:
    try:
        Revenue.model_validate(
            {"value": 4.2, "unit": "million", "period": "Q3", "quote": "SECRET $4.2 billion"}
        )
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a validation error")


@pytest.mark.parametrize("via_failed_attempts", [True, False])
async def test_validation_exhausted_maps_to_extraction_invalid(
    via_failed_attempts: bool, caplog: pytest.LogCaptureFixture
) -> None:
    validation_error = _validation_error()
    failed = [FailedAttempt(1, validation_error, None)] if via_failed_attempts else None
    client = _client_with_mock(AsyncMock(side_effect=_retry_exception(validation_error, failed)))

    with (
        caplog.at_level("WARNING", logger="src.llm.anthropic_client"),
        pytest.raises(ExtractionInvalidError),
    ):
        await client.extract("text")

    record = next(
        r for r in caplog.records if r.getMessage() == "LLM output rejected after all retries"
    )
    assert any("magnitude must match" in check for check in record.failed_checks)
    assert "SECRET" not in str(record.failed_checks)
