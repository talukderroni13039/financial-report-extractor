"""Score the extractor against hand-written answers (evals/labels.json) with the REAL model.

Each transcript costs 1-2 real calls (max_retries=1) and counts against the 50-call live budget.
    uv run python -m evals.run_eval
Writes evals/results/latest.json and prints a pass/fail table.
"""

import asyncio
import json
import math
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.core.exceptions import AppError
from src.domains.earnings_reports.schemas import EarningsReport
from src.domains.earnings_reports.services.extraction_service import ExtractionService
from src.llm.anthropic_client import AnthropicExtractorClient
from src.utils.file_reader import extract_text
from tests.live_budget import calls_used, ensure_budget_available, make_budgeted_anthropic

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "evals" / "labels.json"
RESULTS = ROOT / "evals" / "results" / "latest.json"


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def _score(truth: dict[str, Any], report: EarningsReport | None, error: str | None) -> list[str]:
    """Return the list of failed checks (empty = the transcript passed)."""
    if "error" in truth:
        return [] if error == truth["error"] else [f"expected {truth['error']}, got {error or 200}"]
    if error or report is None:
        return [f"expected success, got {error}"]

    failures = []
    amount = report.revenue.amount if report.revenue else None
    if not _same(amount, truth["revenue"]):
        failures.append(f"revenue {amount} != {truth['revenue']}")
    currency = report.revenue.currency if report.revenue else None
    if currency != truth["currency"]:
        failures.append(f"currency {currency} != {truth['currency']}")

    expected = list(truth["guidance"])
    unmatched = []
    for got in report.guidance:
        match = next(
            (
                want
                for want in expected
                if want["metric"] == got.metric
                and _same(got.low, want["low"])
                and _same(got.high, want["high"])
            ),
            None,
        )
        if match:
            expected.remove(match)
        else:
            unmatched.append(f"{got.metric} {got.low}..{got.high}")
    if unmatched:
        failures.append("unexpected guidance: " + "; ".join(unmatched))
    if expected:
        missing = "; ".join(f"{w['metric']} {w['low']}..{w['high']}" for w in expected)
        failures.append("missing guidance: " + missing)
    return failures


async def main() -> None:
    load_dotenv(ROOT / f".env.{os.getenv('APP_ENV', 'dev')}")
    labels: dict[str, dict[str, Any]] = json.loads(LABELS.read_text(encoding="utf-8"))
    start_budget = calls_used()
    rows = []

    for name, truth in labels.items():
        ensure_budget_available()
        path = ROOT / truth["file"]
        text = extract_text(path.name, path.read_bytes())
        client = AnthropicExtractorClient(make_budgeted_anthropic(f"eval:{name}"), max_retries=1)
        report, error = None, None
        try:
            result = await ExtractionService(client).extract(text=text)
            report = result.report
        except AppError as exc:
            error = exc.code
        failures = _score(truth, report, error)
        rows.append(
            {
                "case": name,
                "checks": truth["checks"],
                "passed": not failures,
                "failures": failures,
                "error": error,
                "report": report.model_dump(mode="json") if report else None,
            }
        )
        print(f"{'PASS' if not failures else 'FAIL'}  {name}  {'; '.join(failures)}")

    passed = sum(row["passed"] for row in rows)
    summary = {
        "passed": passed,
        "total": len(rows),
        "live_calls": calls_used() - start_budget,
        "budget_used": calls_used(),
    }
    RESULTS.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", "utf-8")
    print(
        f"\nScore: {passed}/{len(rows)}  |  live calls this run: {summary['live_calls']}"
        f"  |  budget used: {summary['budget_used']}/50"
    )


if __name__ == "__main__":
    asyncio.run(main())
