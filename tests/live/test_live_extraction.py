"""Real Claude calls. Run manually only: `uv run pytest -m live --no-cov`. Max 5 cases."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.domains.earnings_reports.schemas import EarningsReport

pytestmark = pytest.mark.live

URL = "/api/v1/earnings-reports/extract"
FIXTURES = Path(__file__).parent.parent / "fixtures"


def _report(response: Any, source_type: str) -> EarningsReport:
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source_type"] == source_type
    assert data["usage"]["input_tokens"] > 0
    return EarningsReport.model_validate(data["report"])


def test_live_text_transcript_extracts_revenue(live_client: TestClient) -> None:
    text = (FIXTURES / "sample_transcript.txt").read_text(encoding="utf-8")

    report = _report(live_client.post(URL, data={"text": text}), "text")

    assert report.revenue is not None
    assert report.revenue.amount == pytest.approx(4_200_000_000)
    assert report.company_name is not None
    assert "Acme" in report.company_name


def test_live_txt_file(live_client: TestClient) -> None:
    content = (FIXTURES / "sample_transcript.txt").read_bytes()

    response = live_client.post(URL, files={"file": ("q3.txt", content, "text/plain")})

    report = _report(response, "txt")
    assert report.revenue is not None
    assert report.guidance


def test_live_pdf_file(live_client: TestClient) -> None:
    content = (FIXTURES / "sample_transcript.pdf").read_bytes()

    response = live_client.post(URL, files={"file": ("q3.pdf", content, "application/pdf")})

    report = _report(response, "pdf")
    assert report.revenue is not None
    assert report.risks


def test_live_no_guidance_is_not_invented(live_client: TestClient) -> None:
    text = (FIXTURES / "transcript_no_guidance.txt").read_text(encoding="utf-8")

    report = _report(live_client.post(URL, data={"text": text}), "text")

    assert report.guidance == []
    assert report.revenue is not None
    assert report.revenue.amount == pytest.approx(350_000_000)


def test_live_amount_normalization(live_client: TestClient) -> None:
    text = (
        "Initech Q1 2026 earnings call. CFO: Total revenue for the first quarter of 2026 "
        "was $4.2 billion."
    )

    report = _report(live_client.post(URL, data={"text": text}), "text")

    assert report.revenue is not None
    assert report.revenue.amount == 4_200_000_000
    assert report.revenue.currency == "USD"
