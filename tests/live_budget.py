"""Hard cap on real Anthropic API calls made by live tests and fixture-capture scripts.

Every HTTP attempt (including Instructor re-asks) passes through an httpx request hook that
records it in `tests/.live_call_budget.json` (gitignored) and refuses once the cap is reached.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

BUDGET_FILE = Path(__file__).parent / ".live_call_budget.json"
MAX_LIVE_CALLS = 50


class LiveBudgetExhaustedError(RuntimeError):
    pass


def _load() -> dict[str, Any]:
    if not BUDGET_FILE.exists():
        return {"max_calls": MAX_LIVE_CALLS, "count": 0, "calls": []}
    data: dict[str, Any] = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    return data


def calls_used() -> int:
    return int(_load()["count"])


def ensure_budget_available() -> None:
    used = calls_used()
    if used >= MAX_LIVE_CALLS:
        raise LiveBudgetExhaustedError(
            f"live API budget exhausted: {used}/{MAX_LIVE_CALLS} real Anthropic calls used "
            f"(see {BUDGET_FILE.name})"
        )


def record_call(label: str) -> int:
    """Check the cap, then record one real call. Returns the new count."""
    ensure_budget_available()
    data = _load()
    data["count"] = int(data["count"]) + 1
    data["calls"].append({"at": datetime.now(tz=UTC).isoformat(), "label": label})
    BUDGET_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return int(data["count"])


def make_budgeted_anthropic(label: str) -> AsyncAnthropic:
    """Real AsyncAnthropic whose every HTTP request is counted against the budget.

    SDK-level retries are disabled so each attempt is deliberate and visible.
    """

    async def count_request(_request: object) -> None:
        record_call(label)

    return AsyncAnthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        http_client=DefaultAsyncHttpxClient(event_hooks={"request": [count_request]}),
        max_retries=0,
        timeout=60.0,
    )
