import pytest

from src.utils.grounding import magnitudes_in, normalize, quote_in_text, value_in_quote


def test_normalize_unifies_case_spacing_punctuation_and_thousands() -> None:
    assert normalize("  Revenue of “$4,215” – up  8% ") == ('revenue of "$4215" - up 8%')


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("Total revenue was $4.2 billion", {"billion"}),
        ("$1.85B", {"billion"}),
        ("revenue of 2.3 bn", {"billion"}),
        ("$350 million", {"million"}),
        ("GBP 120m", {"million"}),
        ("$900k", {"thousand"}),
        ("$1.2 trillion", {"trillion"}),
        ("$4.4 billion to $4,600 million", {"billion", "million"}),
        ("EPS of $3.10 for Q3 2026", set()),
        ("revenue grew by year end", set()),
    ],
)
def test_magnitudes_in(quote: str, expected: set[str]) -> None:
    assert magnitudes_in(quote) == expected


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        (4.2, "$4.2 billion", True),
        (3.1, "EPS of $3.10", True),
        (4215, "revenue of 4,215 million", True),
        (-0.10, "a loss of $0.10 per share", True),
        (4_200_000_000, "$4.2 billion", False),
        (0.24, "approximately 24 percent", False),
    ],
)
def test_value_in_quote(value: float, quote: str, expected: bool) -> None:
    assert value_in_quote(value, quote) is expected


def test_quote_in_text_tolerates_line_breaks_and_trailing_period() -> None:
    text = "Total revenue for Q3 2026 was $4.2 billion,\nup 8 percent."

    assert quote_in_text("total revenue for Q3 2026 was $4.2 billion, up 8 percent.", text)
    assert not quote_in_text("Total revenue was $4.3 billion", text)
    assert not quote_in_text("  ", text)
