"""Make ONE real extraction call and save it as tests/fixtures/llm_response.json.

Counts against the 50-call live budget. Usage:
    uv run python -m scripts.capture_llm_fixture
"""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.llm.anthropic_client import AnthropicExtractorClient
from tests.live_budget import calls_used, ensure_budget_available, make_budgeted_anthropic

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


async def main() -> None:
    load_dotenv(f".env.{os.getenv('APP_ENV', 'dev')}")
    ensure_budget_available()

    client = AnthropicExtractorClient(make_budgeted_anthropic("capture_llm_fixture"), max_retries=1)
    transcript = (FIXTURES / "sample_transcript.txt").read_text(encoding="utf-8")
    report, usage = await client.extract(transcript)

    payload = {
        "model": client.model,
        "report": report.model_dump(mode="json"),
        "usage": usage.model_dump(),
    }
    (FIXTURES / "llm_response.json").write_text(json.dumps(payload, indent=2) + "\n", "utf-8")
    print(f"Saved fixture. Live calls used: {calls_used()}")


if __name__ == "__main__":
    asyncio.run(main())
