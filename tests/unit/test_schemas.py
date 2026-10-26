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

TRANSCRIPT = (
    "Acme Corp Q3 2026. Total revenue for Q3 2026 was $4.2 billion, up 8 percent. "
    "For Q4 we expect revenue in the range of $4.4 billion to $4.6 billion. "
    "Operating margin should be approximately 24 percent."
)


def _revenue(**overrides: Any) -> dict[str, Any]:
    data = {
        "value": 4.2,
        "unit": "billion",
        "currency": "usd",
        "period": "Q3 2026",
        "quote": "Total revenue for Q3 2026 was $4.2 billion",
    }
    return data | overrides


def _guidance(**overrides: Any) -> dict[str, Any]:
    data = {
        "metric": "revenue",
        "unit": "currency",
        "magnitude": "billion",
        "low_value": 4.4,
        "high_value": 4.6,
        "period": "Q4 2026",
        "quote": "we expect revenue in the range of $4.4 billion to $4.6 billion",
    }
    return data | overrides


def _report(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "is_earnings_call": True,
        "company_name": "Acme Corp",
        "period": "Q3 2026",
        "revenue": _revenue(),
        "guidance": [_guidance()],
        "risks": [{"description": "  Supply chain delays in Asia ", "severity": "medium"}],
    }
    return data | overrides


def _validate(data: dict[str, Any], text: str = TRANSCRIPT) -> EarningsReport:
    return EarningsReport.model_validate(data, context={"source_text": text})


# --- valid report + amounts computed in code ---


def test_valid_report_passes_and_amounts_are_computed_in_code() -> None:
    report = _validate(_report())

    assert report.revenue is not None
    assert report.revenue.amount == 4_200_000_000
    assert report.revenue.currency == "USD"
    assert (report.guidance[0].low, report.guidance[0].high) == (4_400_000_000, 4_600_000_000)
    assert report.risks[0].severity is Severity.MEDIUM
    assert report.risks[0].description == "Supply chain delays in Asia"


@pytest.mark.parametrize(
    ("value", "unit", "quote", "amount"),
    [
        (4.2, "billion", "$4.2 billion", 4_200_000_000),
        (350, "million", "$350 million", 350_000_000),
        (1.85, "billion", "$1.85B", 1_850_000_000),
        (2.3, "billion", "EUR 2.3 billion", 2_300_000_000),
        (4215, "million", "4,215 million", 4_215_000_000),
        (900, "thousand", "$900k", 900_000),
        (4_215_000_000, "ones", "$4,215,000,000", 4_215_000_000),
    ],
)
def test_amount_is_exact_for_every_number_style(
    value: float, unit: str, quote: str, amount: int
) -> None:
    revenue = Revenue(value=value, unit=unit, period="Q1", quote=quote)  # type: ignore[arg-type]

    assert revenue.amount == amount


def test_amount_is_in_serialized_output() -> None:
    dumped = Revenue.model_validate(_revenue()).model_dump(mode="json")

    assert dumped["amount"] == 4_200_000_000


# --- the 1000x / wrong-number cases are rejected ---


def test_wrong_magnitude_for_quote_is_rejected() -> None:
    with pytest.raises(ValidationError, match="magnitude must match"):
        Revenue.model_validate(_revenue(unit="million"))


def test_value_not_written_in_quote_is_rejected() -> None:
    with pytest.raises(ValidationError, match="written exactly as it appears"):
        Revenue.model_validate(_revenue(value=4_200_000_000, unit="ones"))


def test_quote_not_in_transcript_is_rejected() -> None:
    data = _report(revenue=_revenue(quote="Total revenue was $9.9 billion", value=9.9))

    with pytest.raises(ValidationError, match=r"revenue.quote was not found"):
        _validate(data)


def test_guidance_quote_not_in_transcript_is_rejected() -> None:
    data = _report(
        guidance=[_guidance(quote="we expect $5 billion to $6 billion", low_value=5, high_value=6)]
    )

    with pytest.raises(ValidationError, match=r"guidance\[0\].quote was not found"):
        _validate(data)


def test_quote_match_ignores_case_spacing_and_smart_quotes() -> None:
    text = "CEO: “Total  revenue for Q3 2026 was $4.2 billion.”"

    report = _validate(_report(guidance=[]), text=text)

    assert report.revenue is not None


def test_grounding_skipped_without_source_text() -> None:
    report = EarningsReport.model_validate(_report(revenue=_revenue(quote="$4.2 billion")))

    assert report.revenue is not None


def test_negative_revenue_fails() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Revenue.model_validate(_revenue(value=-4.2))


# --- currency is unknown, never invented ---


def test_currency_defaults_to_none_not_usd() -> None:
    revenue = Revenue.model_validate(_revenue(currency=None))

    assert revenue.currency is None


@pytest.mark.parametrize("currency", ["US", "DOLLARS", "12$"])
def test_invalid_currency_fails(currency: str) -> None:
    with pytest.raises(ValidationError):
        Revenue.model_validate(_revenue(currency=currency))


# --- guidance: fixed metrics, units, ranges ---


def test_guidance_low_above_high_fails() -> None:
    with pytest.raises(ValidationError, match="low must be less than or equal to high"):
        Guidance.model_validate(_guidance(low_value=4.6, high_value=4.4))


def test_guidance_single_bound_is_valid() -> None:
    guidance = Guidance.model_validate(
        _guidance(
            metric="eps",
            unit="per_share",
            magnitude="ones",
            low_value=1.2,
            high_value=None,
            quote="EPS of at least $1.20",
        )
    )

    assert (guidance.low, guidance.high) == (1.2, None)


def test_percent_guidance_keeps_percent_points() -> None:
    guidance = Guidance.model_validate(
        _guidance(
            metric="operating_margin",
            unit="percent",
            magnitude="ones",
            low_value=24,
            high_value=24,
            quote="approximately 24 percent",
        )
    )

    assert (guidance.low, guidance.high) == (24, 24)


def test_percent_written_as_fraction_is_rejected() -> None:
    with pytest.raises(ValidationError, match="written exactly"):
        Guidance.model_validate(
            _guidance(
                metric="operating_margin",
                unit="percent",
                magnitude="ones",
                low_value=0.24,
                high_value=0.24,
                quote="approximately 24 percent",
            )
        )


def test_percent_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="24 for 24 percent"):
        Guidance.model_validate(
            _guidance(
                metric="other",
                unit="percent",
                magnitude="ones",
                low_value=240,
                high_value=240,
                quote="240 percent",
            )
        )


@pytest.mark.parametrize(
    ("metric", "unit"),
    [("eps", "currency"), ("operating_margin", "currency"), ("revenue", "percent")],
)
def test_metric_must_use_its_unit(metric: str, unit: str) -> None:
    with pytest.raises(ValidationError, match="must use unit"):
        Guidance.model_validate(_guidance(metric=metric, unit=unit))


def test_unknown_metric_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Guidance.model_validate(_guidance(metric="Op. margin"))


def test_magnitude_only_for_currency_guidance() -> None:
    with pytest.raises(ValidationError, match="magnitude must be 'ones'"):
        Guidance.model_validate(
            _guidance(
                metric="eps",
                unit="per_share",
                magnitude="billion",
                low_value=3.1,
                high_value=3.2,
                quote="EPS of $3.10 to $3.20",
            )
        )


def test_eps_loss_is_negative() -> None:
    guidance = Guidance.model_validate(
        _guidance(
            metric="eps",
            unit="per_share",
            magnitude="ones",
            low_value=-0.10,
            high_value=-0.05,
            quote="a loss per share of $0.10 to $0.05",
        )
    )

    assert (guidance.low, guidance.high) == (-0.10, -0.05)


# --- other fields ---


def test_invalid_severity_fails() -> None:
    with pytest.raises(ValidationError):
        Risk.model_validate({"description": "FX headwinds", "severity": "critical"})


def test_empty_risk_description_fails() -> None:
    with pytest.raises(ValidationError):
        Risk.model_validate({"description": "   ", "severity": "low"})


def test_missing_optional_sections_default_to_empty() -> None:
    report = EarningsReport.model_validate({"is_earnings_call": False})

    assert report.company_name is None
    assert report.revenue is None
    assert report.guidance == []
    assert report.risks == []


def test_is_earnings_call_is_required() -> None:
    with pytest.raises(ValidationError):
        EarningsReport.model_validate({})


def test_result_wraps_report_and_usage() -> None:
    result = EarningsReportResult(
        source_type="pdf",
        file_name="call.pdf",
        model="claude-haiku-5-5",
        report=_validate(_report()),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )

    dumped = result.model_dump(mode="json")
    assert dumped["report"]["revenue"]["amount"] == 4_200_000_000
    assert dumped["report"]["guidance"][0]["low"] == 4_400_000_000
    assert dumped["usage"] == {"input_tokens": 10, "output_tokens": 5}


def test_result_rejects_unknown_source_type() -> None:
    with pytest.raises(ValidationError):
        EarningsReportResult.model_validate(
            {
                "source_type": "docx",
                "model": "m",
                "report": {"is_earnings_call": True},
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        )
