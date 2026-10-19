import os

# Must run before `src.main` is imported: no .env.test exists, so no real key is loaded into tests.
os.environ["APP_ENV"] = "test"

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
