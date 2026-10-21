from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.earnings_reports.schemas import (
    EarningsReport,
    EarningsReportResult,
    Guidance,
    Revenue,
    Risk,
    Severity,
    TokenUsage,
)


def _valid_report_data() -> dict[str, Any]:
    return {
        "company_name": "Acme Corp",
        "period": "Q3 2026",
        "revenue": {"amount": 4_200_000_000, "currency": "usd", "period": "Q3 2026"},
        "guidance": [
            {"metric": "revenue", "low": 4.4e9, "high": 4.6e9, "period": "Q4 2026"},
        ],
        "risks": [{"description": "  Supply chain delays in Asia ", "severity": "medium"}],
    }


def test_valid_report_passes() -> None:
    report = EarningsReport.model_validate(_valid_report_data())

    assert report.revenue is not None
    assert report.revenue.amount == 4_200_000_000
    assert report.revenue.currency == "USD"
    assert report.guidance[0].low == 4.4e9
    assert report.risks[0].severity is Severity.MEDIUM
    assert report.risks[0].description == "Supply chain delays in Asia"


def test_negative_revenue_fails() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Revenue(amount=-1, period="Q3 2026")


def test_guidance_low_above_high_fails() -> None:
    with pytest.raises(ValidationError, match="low must be less than or equal to high"):
        Guidance(metric="revenue", low=5.0, high=4.0)


def test_guidance_with_single_bound_is_valid() -> None:
    guidance = Guidance(metric="EPS", low=1.2)

    assert guidance.high is None


def test_invalid_severity_fails() -> None:
    with pytest.raises(ValidationError):
        Risk.model_validate({"description": "FX headwinds", "severity": "critical"})


def test_empty_risk_description_fails() -> None:
    with pytest.raises(ValidationError):
        Risk.model_validate({"description": "   ", "severity": "low"})


@pytest.mark.parametrize("currency", ["US", "DOLLARS", "12$"])
def test_invalid_currency_fails(currency: str) -> None:
    with pytest.raises(ValidationError):
        Revenue(amount=1, currency=currency, period="Q1")


def test_missing_optional_sections_default_to_empty() -> None:
    report = EarningsReport.model_validate({})

    assert report.company_name is None
    assert report.period is None
    assert report.revenue is None
    assert report.guidance == []
    assert report.risks == []


def test_result_wraps_report_and_usage() -> None:
    result = EarningsReportResult(
        source_type="pdf",
        file_name="call.pdf",
        model="claude-haiku-5-5",
        report=EarningsReport.model_validate(_valid_report_data()),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )

    dumped = result.model_dump(mode="json")
    assert dumped["report"]["risks"][0]["severity"] == "medium"
    assert dumped["usage"] == {"input_tokens": 10, "output_tokens": 5}


def test_result_rejects_unknown_source_type() -> None:
    with pytest.raises(ValidationError):
        EarningsReportResult.model_validate(
            {
                "source_type": "docx",
                "model": "m",
                "report": {},
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )
