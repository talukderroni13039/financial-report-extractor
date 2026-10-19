"""Instructor `response_model` for the extraction call.

Field descriptions are sent to the LLM as part of the JSON schema, so they act as per-field
instructions. Everything optional defaults to None / empty so the model never has to invent data.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Revenue(BaseModel):
    amount: float = Field(
        ge=0,
        description=(
            "Total revenue for the reported period as a full number in currency units, "
            "e.g. $4.2 billion = 4200000000, $350 million = 350000000."
        ),
    )
    currency: str = Field(
        default="USD",
        pattern=r"^[A-Z]{3}$",
        description="ISO 4217 three-letter currency code, e.g. USD, EUR. Default USD.",
    )
    period: str = Field(
        min_length=1,
        description="Period the revenue figure covers as stated in the transcript, e.g. 'Q3 2026'.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def _upper_currency(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class Guidance(BaseModel):
    metric: str = Field(
        min_length=1,
        description="What the guidance is for, e.g. 'revenue', 'EPS', 'operating margin'.",
    )
    low: float | None = Field(
        default=None,
        description="Low end of the guided range as a full number "
        "(e.g. $4.4 billion = 4400000000). For a single-point estimate set low and high "
        "to the same value. Null if not stated.",
    )
    high: float | None = Field(
        default=None,
        description="High end of the guided range as a full number. Null if not stated.",
    )
    period: str | None = Field(
        default=None,
        description="Future period the guidance applies to, e.g. 'Q4 2026' or 'FY2027'.",
    )

    @model_validator(mode="after")
    def _low_not_above_high(self) -> Self:
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("guidance low must be less than or equal to high")
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
    company_name: str | None = Field(
        default=None, description="Company name as stated in the transcript. Null if not stated."
    )
    period: str | None = Field(
        default=None,
        description="Reporting period of the call, e.g. 'Q3 2026'. Null if not stated.",
    )
    revenue: Revenue | None = Field(
        default=None,
        description="Reported total revenue for the period. Null if not explicitly stated.",
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
