"""Fixtures for `@pytest.mark.live` tests only: real Claude calls, counted against the budget."""

import os
from collections.abc import Iterator

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from src.core.dependencies import get_llm_client
from src.llm.anthropic_client import AnthropicExtractorClient
from src.main import app
from tests.live_budget import (
    MAX_LIVE_CALLS,
    LiveBudgetExhaustedError,
    calls_used,
    ensure_budget_available,
    make_budgeted_anthropic,
)


@pytest.fixture
def live_client(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    """TestClient wired to the real Anthropic API (max_retries=1), budget-guarded."""
    load_dotenv(f".env.{os.getenv('LIVE_APP_ENV', 'dev')}")
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; live tests need .env.dev")
    try:
        ensure_budget_available()
    except LiveBudgetExhaustedError as exc:
        pytest.fail(str(exc))

    extractor = AnthropicExtractorClient(make_budgeted_anthropic(request.node.name), max_retries=1)
    app.dependency_overrides[get_llm_client] = lambda: extractor
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        print(f"\n[live budget] {calls_used()}/{MAX_LIVE_CALLS} real calls used")
