"""Instructor `response_model` for the extraction call.

Field descriptions are sent to the LLM as part of the JSON schema, so they act as per-field
instructions. Everything optional defaults to None / empty so the model never has to invent data.

The model reports numbers *as written* (value + magnitude word) plus the exact quote they came
from; code computes the full amounts and checks every figure against the transcript. Validation
error messages are sent back to the model on retry, so they are phrased as instructions and never
echo transcript text.
"""

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)

from src.utils.grounding import magnitudes_in, quote_in_text, value_in_quote

Magnitude = Literal["ones", "thousand", "million", "billion", "trillion"]
MULTIPLIER: dict[str, int] = {
    "ones": 1,
    "thousand": 10**3,
    "million": 10**6,
    "billion": 10**9,
    "trillion": 10**12,
}

GuidanceMetric = Literal[
    "revenue",
    "revenue_growth",
    "eps",
    "operating_margin",
    "gross_margin",
    "operating_income",
    "net_income",
    "other",
]
GuidanceUnit = Literal["currency", "per_share", "percent"]

# The unit each metric must use ("other" may use any unit).
_METRIC_UNIT: dict[str, str] = {
    "revenue": "currency",
    "operating_income": "currency",
    "net_income": "currency",
    "eps": "per_share",
    "revenue_growth": "percent",
    "operating_margin": "percent",
    "gross_margin": "percent",
}

_QUOTE_DESCRIPTION = (
    "The exact words from the transcript that state this figure, copied character for "
    "character, e.g. 'Total revenue for Q3 2026 was $4.2 billion'."
)


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _check_figure(field: str, value: float, magnitude: str, quote: str) -> None:
    """The number and magnitude word must be the ones written in the quote."""
    if not value_in_quote(value, quote):
        raise ValueError(
            f"{field}: the number must be written exactly as it appears in the quote "
            "(e.g. 4.2 for '$4.2 billion'); do not convert or round it"
        )
    written = magnitudes_in(quote)
    if written and magnitude not in written:
        raise ValueError(
            f"{field}: magnitude must match the word in the quote "
            f"(quote uses {', '.join(sorted(written))})"
        )


class Revenue(BaseModel):
    value: float = Field(
        ge=0,
        description="Total revenue number exactly as written, without its magnitude word: "
        "4.2 for '$4.2 billion', 350 for '$350 million', 4215 for '$4,215 million'.",
    )
    unit: Magnitude = Field(
        description="Magnitude word written next to the number: 'billion' for '$4.2 billion' "
        "or '$4.2B', 'million' for '$350 million' or '$350m'; 'ones' if none is written.",
    )
    currency: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217 code of the currency stated in the transcript ($ = USD, "
        "€ or EUR = EUR, £ = GBP). Null if no currency is stated; never assume one.",
    )
    period: str = Field(
        min_length=1,
        description="Period the revenue figure covers as stated in the transcript, e.g. 'Q3 2026'.",
    )
    quote: str = Field(min_length=1, description=_QUOTE_DESCRIPTION)

    @field_validator("currency", mode="before")
    @classmethod
    def _upper_currency(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper() or None
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def amount(self) -> float:
        """Full amount computed in code, e.g. 4.2 billion -> 4200000000."""
        return self.value * MULTIPLIER[self.unit]

    @model_validator(mode="after")
    def _figure_matches_quote(self) -> Self:
        _check_figure("revenue", self.value, self.unit, self.quote)
        return self


class Guidance(BaseModel):
    metric: GuidanceMetric = Field(
        description="What the guidance is for. revenue_growth = growth in percent; "
        "eps = earnings per share; use 'other' only if nothing else fits.",
    )
    unit: GuidanceUnit = Field(
        description="currency for money amounts, per_share for EPS, percent for margins and "
        "growth rates.",
    )
    magnitude: Magnitude = Field(
        default="ones",
        description="For currency amounts only: magnitude word written next to the numbers "
        "('billion' for '$4.4 to $4.6 billion'). 'ones' for per_share and percent.",
    )
    low_value: float | None = Field(
        default=None,
        description="Low end exactly as written, without magnitude (4.4 for '$4.4 billion', "
        "24 for '24 percent'; negative for a loss). For a single figure set low and high to "
        "the same value. Null if not stated.",
    )
    high_value: float | None = Field(
        default=None,
        description="High end exactly as written, without magnitude. Null if not stated.",
    )
    period: str | None = Field(
        default=None,
        description="Future period the guidance applies to, e.g. 'Q4 2026' or 'FY2027'.",
    )
    quote: str = Field(min_length=1, description=_QUOTE_DESCRIPTION)

    def _scale(self, value: float | None) -> float | None:
        if value is None:
            return None
        return value * MULTIPLIER[self.magnitude] if self.unit == "currency" else value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def low(self) -> float | None:
        """Low end computed in code: full currency amount, EPS per share, or percent (24 = 24%)."""
        return self._scale(self.low_value)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def high(self) -> float | None:
        """High end computed in code, same units as `low`."""
        return self._scale(self.high_value)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        expected_unit = _METRIC_UNIT.get(self.metric)
        if expected_unit and self.unit != expected_unit:
            raise ValueError(f"guidance for {self.metric} must use unit '{expected_unit}'")
        if self.unit != "currency" and self.magnitude != "ones":
            raise ValueError("magnitude must be 'ones' for per_share and percent guidance")
        if (
            self.low_value is not None
            and self.high_value is not None
            and self.low_value > self.high_value
        ):
            raise ValueError("guidance low must be less than or equal to high")
        for name, value in (("low_value", self.low_value), ("high_value", self.high_value)):
            if value is None:
                continue
            if self.unit == "percent" and not -100 <= value <= 100:
                raise ValueError("percent guidance must be written as 24 for 24 percent")
            _check_figure(f"guidance {name}", value, self.magnitude, self.quote)
        return self


class Risk(BaseModel):
    description: str = Field(
        min_length=1,
        description="One-sentence description of a risk or headwind mentioned in the transcript.",
    )
    severity: Severity = Field(
        description="high = management flags material impact on results/guidance; "
        "medium = noted concern with limited or uncertain impact; low = briefly mentioned.",
    )

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class EarningsReport(BaseModel):
    is_earnings_call: bool = Field(
        description="True if the text is an earnings call transcript or earnings results "
        "statement from a company; false for anything else (lists, articles, legal text).",
    )
    company_name: str | None = Field(
        default=None, description="Company name as stated in the transcript. Null if not stated."
    )
    period: str | None = Field(
        default=None,
        description="Reporting period of the call, e.g. 'Q3 2026'. Null if not stated.",
    )
    revenue: Revenue | None = Field(
        default=None,
        description="Reported total revenue for the period (not a segment, not a prior-year "
        "comparison, not guidance). Null if not explicitly stated.",
    )
    guidance: list[Guidance] = Field(
        default_factory=list,
        description="Forward-looking guidance explicitly given by management. "
        "Empty list if none was given; never infer guidance.",
    )
    risks: list[Risk] = Field(
        default_factory=list,
        description="Risks or headwinds explicitly discussed. Empty list if none.",
    )

    @model_validator(mode="after")
    def _quotes_are_in_transcript(self, info: ValidationInfo) -> Self:
        """Grounding: every quoted figure must exist in the source text (when it is provided)."""
        source_text = (info.context or {}).get("source_text")
        if not source_text:
            return self
        if self.revenue and not quote_in_text(self.revenue.quote, source_text):
            raise ValueError(
                "revenue.quote was not found in the transcript; copy the sentence exactly"
            )
        for index, guidance in enumerate(self.guidance):
            if not quote_in_text(guidance.quote, source_text):
                raise ValueError(
                    f"guidance[{index}].quote was not found in the transcript; "
                    "copy the words exactly"
                )
        return self
