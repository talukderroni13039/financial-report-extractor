"""Deterministic checks that an LLM-extracted figure really comes from the source text.

Pure functions: no LLM, no HTTP. Used by the extraction schema's validators.
"""

import re
import unicodedata

# Smart quotes, dashes and non-breaking spaces vary between PDFs, Word and plain text.
_PUNCTUATION_MAP = str.maketrans(
    {
        0x2018: "'",  # left single quote
        0x2019: "'",  # right single quote / apostrophe
        0x201C: '"',  # left double quote
        0x201D: '"',  # right double quote
        0x2013: "-",  # en dash
        0x2014: "-",  # em dash
        0x2212: "-",  # minus sign
        0x00A0: " ",  # no-break space
    }
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3})")

# Magnitude words as they appear in transcripts ("$4.2 billion", "1.85B", "EUR 120m", "$900k").
_MAGNITUDE_PATTERNS: dict[str, re.Pattern[str]] = {
    "trillion": re.compile(r"\btrillion\b|\d\s?tn\b"),
    "billion": re.compile(r"\bbillion\b|\bbn\b|\d\s?bn?\b"),
    "million": re.compile(r"\bmillion\b|\bmn\b|\bmm\b|\d\s?m\b"),
    "thousand": re.compile(r"\bthousand\b|\d\s?k\b"),
}


def normalize(text: str) -> str:
    """Lower-case, unify punctuation and whitespace, drop thousands separators."""
    text = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION_MAP).lower()
    text = _THOUSANDS_SEPARATOR.sub("", text)
    return " ".join(text.split())


def quote_in_text(quote: str, text: str) -> bool:
    """True if `quote` appears in `text`, ignoring case, spacing and punctuation variants."""
    needle = normalize(quote).strip(" .\"'")
    return bool(needle) and needle in normalize(text)


def numbers_in(quote: str) -> list[float]:
    return [float(match) for match in _NUMBER.findall(normalize(quote))]


def value_in_quote(value: float, quote: str) -> bool:
    """True if `value` is one of the numbers written in `quote` (sign ignored: "loss of $0.10")."""
    return any(abs(abs(value) - number) < 1e-9 for number in numbers_in(quote))


def magnitudes_in(quote: str) -> set[str]:
    """Magnitude words written in `quote`, e.g. {"billion"} for "$4.2 billion"."""
    normalized = normalize(quote)
    return {name for name, pattern in _MAGNITUDE_PATTERNS.items() if pattern.search(normalized)}
