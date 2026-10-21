import json
import logging
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.exceptions import InvalidInputError
from src.core.logging_config import JsonFormatter, RequestIdFilter, request_id_ctx
from src.main import create_app


@pytest.fixture
def app_with_failing_routes() -> FastAPI:
    app = create_app()

    @app.get("/raise-app-error")
    async def raise_app_error() -> None:
        raise InvalidInputError("bad input")

    @app.get("/raise-bug")
    async def raise_bug() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/needs-int")
    async def needs_int(value: int) -> int:
        return value

    return app


def _assert_error_envelope(body: dict[str, object], code: str) -> None:
    assert body["success"] is False
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    meta = body["meta"]
    assert isinstance(meta, dict)
    assert meta["request_id"]
    assert isinstance(meta["processing_time_ms"], int)


def test_app_error_rendered_as_error_response(app_with_failing_routes: FastAPI) -> None:
    with TestClient(app_with_failing_routes) as client:
        response = client.get("/raise-app-error")

    assert response.status_code == 400
    _assert_error_envelope(response.json(), "INVALID_INPUT")
    assert response.json()["error"]["message"] == "bad input"
    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_exception_returns_generic_500_without_stack_trace(
    app_with_failing_routes: FastAPI,
) -> None:
    with TestClient(app_with_failing_routes, raise_server_exceptions=False) as client:
        response = client.get("/raise-bug")

    assert response.status_code == 500
    body = response.json()
    _assert_error_envelope(body, "INTERNAL_ERROR")
    assert body["error"]["message"] == "Unexpected server error"
    assert "Traceback" not in response.text
    assert "secret internal detail" not in response.text
    assert response.headers["X-Request-ID"] == body["meta"]["request_id"]


def test_request_validation_error_uses_envelope(app_with_failing_routes: FastAPI) -> None:
    with TestClient(app_with_failing_routes) as client:
        response = client.get("/needs-int", params={"value": "not-a-number-xyz"})

    assert response.status_code == 422
    _assert_error_envelope(response.json(), "VALIDATION_ERROR")
    assert "not-a-number-xyz" not in response.text


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    _assert_error_envelope(response.json(), "NOT_FOUND")


def test_valid_incoming_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"
    assert response.json()["meta"]["request_id"] == "abc-123"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id\twith spaces"})

    assert response.headers["X-Request-ID"] != "bad id\twith spaces"
    assert len(response.headers["X-Request-ID"]) == 36


def test_json_formatter_includes_request_id_and_extras() -> None:
    token = request_id_ctx.set("req-1")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("x",), None)
        RequestIdFilter().filter(record)
        record.source_type = "pdf"
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_ctx.reset(token)

    assert payload["message"] == "hello x"
    assert payload["request_id"] == "req-1"
    assert payload["source_type"] == "pdf"
    assert payload["level"] == "INFO"


def test_json_formatter_includes_exception_info() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError" in payload["exc_info"]
