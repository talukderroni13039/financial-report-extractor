import logging
import sys

import pytest
from fastapi.testclient import TestClient

from src import main


def test_swagger_title_shows_environment(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "Financial Report Extractor API [test]"


def test_startup_log_shows_environment_and_docs_url(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["uvicorn", "src.main:app", "--port", "8001"])
    app = main.create_app()  # resets root log handlers, so re-attach pytest's capture handler
    logging.getLogger().addHandler(caplog.handler)

    with caplog.at_level(logging.INFO, logger="src.main"), TestClient(app):
        pass

    record = next(r for r in caplog.records if r.name == "src.main")
    assert record.getMessage() == "Application started"
    assert record.environment == "test"
    assert record.docs_url == "http://127.0.0.1:8001/docs"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["uvicorn", "src.main:app"], "http://127.0.0.1:8000"),
        (["uvicorn", "src.main:app", "--host=0.0.0.0", "--port=9000"], "http://localhost:9000"),
        (["uvicorn", "src.main:app", "--host", "10.0.0.5"], "http://10.0.0.5:8000"),
    ],
)
def test_base_url_from_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: str) -> None:
    monkeypatch.setattr(sys, "argv", argv)

    assert main._base_url() == expected
