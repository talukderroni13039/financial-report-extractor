"""The live-call budget guard itself (no network)."""

import json
from pathlib import Path

import pytest

from tests import live_budget


@pytest.fixture(autouse=True)
def temp_budget_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".live_call_budget.json"
    monkeypatch.setattr(live_budget, "BUDGET_FILE", path)
    return path


def test_starts_at_zero() -> None:
    assert live_budget.calls_used() == 0


def test_record_call_increments_and_persists(temp_budget_file: Path) -> None:
    assert live_budget.record_call("a") == 1
    assert live_budget.record_call("b") == 2

    data = json.loads(temp_budget_file.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert [call["label"] for call in data["calls"]] == ["a", "b"]


def test_blocks_at_cap(temp_budget_file: Path) -> None:
    temp_budget_file.write_text(json.dumps({"count": 50, "calls": []}), encoding="utf-8")

    with pytest.raises(live_budget.LiveBudgetExhaustedError, match="live API budget exhausted"):
        live_budget.record_call("one too many")
    assert live_budget.calls_used() == 50


async def test_budgeted_client_hook_refuses_before_sending(temp_budget_file: Path) -> None:
    temp_budget_file.write_text(json.dumps({"count": 50, "calls": []}), encoding="utf-8")
    client = live_budget.make_budgeted_anthropic("hook-test")

    hooks = client._client.event_hooks["request"]
    with pytest.raises(live_budget.LiveBudgetExhaustedError):
        await hooks[0](object())
    assert client.max_retries == 0
