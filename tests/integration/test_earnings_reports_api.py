from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import ExtractionFailedError, LLMTimeoutError
from src.main import app
from tests.fakes import FakeExtractorClient
from tests.pdf_factory import build_pdf

URL = "/api/v1/earnings-reports/extract"
FIXTURES = Path(__file__).parent.parent / "fixtures"


def _assert_success(response: Any, source_type: str, file_name: str | None) -> dict[str, Any]:
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["success"] is True
    assert set(body) == {"success", "data", "meta"}
    data = body["data"]
    assert data["source_type"] == source_type
    assert data["file_name"] == file_name
    assert data["model"] == "claude-haiku-5-5"
    assert data["report"]["revenue"]["amount"] == 4_200_000_000
    assert data["usage"]["input_tokens"] > 0
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]
    assert isinstance(body["meta"]["processing_time_ms"], int)
    return data


def _assert_error(response: Any, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert body["success"] is False
    assert set(body) == {"success", "error", "meta"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert body["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_extract_from_text(client: TestClient, fake_llm: FakeExtractorClient) -> None:
    response = client.post(URL, data={"text": "Acme revenue was $4.2 billion in Q3 2026."})

    _assert_success(response, "text", None)
    assert fake_llm.calls == ["Acme revenue was $4.2 billion in Q3 2026."]


def test_extract_from_txt_file(client: TestClient) -> None:
    content = (FIXTURES / "sample_transcript.txt").read_bytes()

    response = client.post(URL, files={"file": ("q3_call.txt", content, "text/plain")})

    _assert_success(response, "txt", "q3_call.txt")


def test_extract_from_pdf_file(client: TestClient) -> None:
    content = (FIXTURES / "sample_transcript.pdf").read_bytes()

    response = client.post(URL, files={"file": ("q3_call.pdf", content, "application/pdf")})

    data = _assert_success(response, "pdf", "q3_call.pdf")
    assert data["report"]["guidance"][0]["low"] == 4_400_000_000


def test_both_inputs_returns_400(client: TestClient, fake_llm: FakeExtractorClient) -> None:
    response = client.post(
        URL, data={"text": "hello"}, files={"file": ("a.txt", b"hi", "text/plain")}
    )

    _assert_error(response, 400, "INVALID_INPUT")
    assert fake_llm.calls == []


def test_no_input_returns_400(client: TestClient) -> None:
    _assert_error(client.post(URL), 400, "INVALID_INPUT")


def test_whitespace_text_returns_400(client: TestClient) -> None:
    _assert_error(client.post(URL, data={"text": "   "}), 400, "INVALID_INPUT")


def test_docx_returns_415(client: TestClient) -> None:
    response = client.post(URL, files={"file": ("report.docx", b"PK\x03\x04", "application/zip")})

    _assert_error(response, 415, "UNSUPPORTED_FILE_TYPE")


def test_oversize_upload_returns_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")

    response = client.post(URL, files={"file": ("big.txt", b"a" * 5_000, "text/plain")})

    _assert_error(response, 413, "INPUT_TOO_LARGE")


def test_oversize_text_returns_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_TEXT_CHARS", "20")

    response = client.post(URL, data={"text": "x" * 21})

    _assert_error(response, 413, "INPUT_TOO_LARGE")
    assert "20 characters" in response.json()["error"]["message"]


def test_scanned_pdf_returns_422(client: TestClient) -> None:
    response = client.post(URL, files={"file": ("scan.pdf", build_pdf([""]), "application/pdf")})

    _assert_error(response, 422, "FILE_PARSE_FAILED")


def test_corrupt_pdf_returns_422(client: TestClient) -> None:
    response = client.post(URL, files={"file": ("bad.pdf", b"%PDF-garbage", "application/pdf")})

    _assert_error(response, 422, "FILE_PARSE_FAILED")


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ExtractionFailedError("Could not extract"), 502, "EXTRACTION_FAILED"),
        (LLMTimeoutError("timed out"), 504, "LLM_TIMEOUT"),
    ],
)
def test_llm_errors_map_to_status_codes(
    client: TestClient, fake_llm: FakeExtractorClient, error: Exception, status_code: int, code: str
) -> None:
    fake_llm.error = error

    response = client.post(URL, data={"text": "Revenue was $1."})

    _assert_error(response, status_code, code)


def test_unexpected_llm_bug_returns_500_without_details(fake_llm: FakeExtractorClient) -> None:
    from src.core.dependencies import get_llm_client

    fake_llm.error = RuntimeError("internal secret detail")
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(URL, data={"text": "Revenue was $1."})
    finally:
        app.dependency_overrides.clear()

    _assert_error(response, 500, "INTERNAL_ERROR")
    assert "internal secret detail" not in response.text
    assert "Traceback" not in response.text


def test_openapi_documents_extract_endpoint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    operation = schema["paths"][URL]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert {"200", "400", "413", "415", "422", "502", "504"} <= set(operation["responses"])
