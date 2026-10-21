import os

# Must run before `src.main` is imported: no .env.test exists, so no real key is loaded into tests.
os.environ["APP_ENV"] = "test"

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.core.dependencies import get_llm_client
from src.main import app
from tests.fakes import FakeExtractorClient


@pytest.fixture
def fake_llm() -> FakeExtractorClient:
    return FakeExtractorClient()


@pytest.fixture
def client(fake_llm: FakeExtractorClient) -> Iterator[TestClient]:
    """TestClient whose LLM dependency is the fake: zero real API calls."""
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
