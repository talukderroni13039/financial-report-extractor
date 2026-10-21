# financial-report-extractor

Extracts structured financial data (revenue, guidance, risks) from earnings call transcripts
using Claude (`claude-haiku-5-5`) + Instructor + Pydantic v2, exposed as a FastAPI service.

## Quick start (Windows / PowerShell)

Prerequisites: [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you), optionally Docker.

```powershell
git clone https://github.com/talukderroni13039/financial-report-extractor.git
cd financial-report-extractor
uv sync                                   # creates .venv from uv.lock

Copy-Item .env.example .env.dev           # then set ANTHROPIC_API_KEY in .env.dev
$env:APP_ENV = "dev"
uv run uvicorn src.main:app --reload      # http://localhost:8000/docs
```

Try it:

```powershell
curl.exe -F "file=@samples/q3_2026_acme_call.pdf" http://localhost:8000/api/v1/earnings-reports/extract
curl.exe -F "text=Acme revenue for Q3 2026 was 4.2 billion dollars." http://localhost:8000/api/v1/earnings-reports/extract
curl.exe http://localhost:8000/health
```

Running from VS Code and testing with Postman (plus ready-made test files): see
[`docs/RUN_AND_TEST.md`](docs/RUN_AND_TEST.md). What to do next: [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md).

### Configuration

`main.py` loads `.env.{APP_ENV}` (`APP_ENV` defaults to `dev`); variables already set in the
process (e.g. by Docker `--env-file`) win. Only the API key is required — everything else has a
safe default in code. There is no settings class: modules call `os.getenv` at call time.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `dev` | Selects `.env.dev` / `.env.uat`; reported by `/health` |
| `LOG_LEVEL` | `INFO` | Root log level (JSON logs to stdout) |
| `ANTHROPIC_API_KEY` | — | **Required** for real extraction calls |
| `LLM_MODEL` | `claude-haiku-5-5` | Claude model |
| `LLM_MAX_TOKENS` | `4000` | Max output tokens per call |
| `LLM_MAX_RETRIES` | `2` | Instructor re-asks on validation failure (N re-asks = up to N+1 calls) |
| `LLM_TIMEOUT_SECONDS` | `60` | Anthropic HTTP timeout |
| `MAX_UPLOAD_MB` | `10` | Max upload size |
| `MAX_TEXT_CHARS` | `300000` | Max transcript length sent to the LLM |

### Run in UAT / Docker

```powershell
$env:APP_ENV = "uat"; uv run uvicorn src.main:app          # local, loads .env.uat

docker build -t financial-report-extractor .
docker run --rm --env-file .env.uat -p 8000:8000 financial-report-extractor
curl.exe http://localhost:8000/health    # data.environment == "uat"
```

The image is multi-stage (uv builder → `python:3.12-slim`), runs as a non-root user, and
`.dockerignore` excludes every `.env*` file — secrets only arrive via `--env-file` / env vars.

## Development

```powershell
uv run pytest                      # mocked unit + integration tests, coverage ≥ 80% enforced
uv run pytest -m live --no-cov     # 5 live tests against the real API (costs money)
uv run ruff check .; uv run ruff format .; uv run mypy src
uv run pre-commit install          # optional git hooks (ruff + mypy)
uv run python -m scripts.capture_llm_fixture   # re-capture tests/fixtures/llm_response.json (1 real call)
```

- Tests never call the API: `app.dependency_overrides[get_llm_client]` swaps in a fake that
  returns the saved real response in `tests/fixtures/llm_response.json`.
- Live tests (`@pytest.mark.live`) are excluded by default and never run in CI. Every real HTTP
  attempt is counted in `tests/.live_call_budget.json` (gitignored); at 50 calls they fail with
  "live API budget exhausted" instead of calling.
- CI (`.github/workflows/ci.yml`): ruff, ruff format check, mypy strict, mocked tests.

## Project layout

```
src/
├── main.py                 # env loading, app factory, middleware, handler, routers
├── api_router.py           # /api/v1 — includes every domain router
├── core/                   # dependencies (all DI), exceptions, exception_handlers, middleware,
│                           # logging_config, health, schemas/api_response.py (envelope)
├── domains/earnings_reports/
│   ├── routers/api_endpoints.py
│   ├── schemas/llm_extraction.py, earnings_report_result.py
│   ├── services/extraction_service.py
│   └── prompts/extraction_prompt.py
├── llm/base.py (ExtractorClient Protocol), anthropic_client.py
└── utils/file_reader.py
```

Request flow: middleware (request ID, timing) → router → `ExtractionService` (validate input,
read file in a threadpool, enforce limits) → `ExtractorClient` (Instructor + Claude, retries) →
`ApiResponse[EarningsReportResult]`. Any exception → one global handler → `ErrorResponse`.
See `CLAUDE.md` for conventions and `docs/DECISIONS.md` for deviations from the original design.

## Cost notes

- Default model `claude-haiku-5-5` (cheapest current Claude); no sampling params are sent.
- A ~1 page transcript costs ≈ 2.5K input + 350 output tokens per call (system prompt + schema
  are ~2.2K of the input). Token usage is returned in `data.usage` and logged per request.
- `MAX_TEXT_CHARS` and `MAX_UPLOAD_MB` are enforced before any LLM call; worst case per request is
  `LLM_MAX_RETRIES + 1` calls.
- Set a spend limit + email alert per workspace in the Claude Console; use separate keys for dev and UAT.

## Requirements

### Functional

| ID | Requirement |
|---|---|
| FR1 | Single endpoint `POST /api/v1/earnings-reports/extract` accepts **either** raw text **or** a file (`.txt` / `.pdf`) |
| FR2 | Exactly one input must be provided; both or neither → `400` |
| FR3 | PDF text is extracted page by page; PDFs with no extractable text (scanned images) → `422` |
| FR4 | Extracted text is sent to Claude via Instructor; output validated against `EarningsReport` |
| FR5 | On validation failure, auto-retry up to `LLM_MAX_RETRIES` times |
| FR6 | Every endpoint returns the same envelope: `success`, `data`, `meta` (request ID, processing time) |
| FR7 | All errors return the same envelope with `success: false`, `error`, `meta` |
| FR8 | `GET /health` returns service status and active environment |

### Non-functional

| Area | Requirement |
|---|---|
| Performance | p95 < 30 s; LLM call timeout via `LLM_TIMEOUT_SECONDS` |
| Cost | Upload ≤ `MAX_UPLOAD_MB`; text ≤ `MAX_TEXT_CHARS`; token usage logged per request |
| Security | API key only in env files; env files never committed; file type + size validated before processing |
| Reliability | Retries on validation failure; no stack traces leaked to clients |
| Observability | JSON logs with request ID, source type, duration, token usage; `X-Request-ID` response header |
| Testability | LLM client injected via FastAPI `Depends`; tests use `dependency_overrides` → zero API cost |
| Environments | `dev` and `uat` selected via `APP_ENV` |

## API contract

### `POST /api/v1/earnings-reports/extract`

`Content-Type: multipart/form-data` — send exactly one of:

| Field | Type |
|---|---|
| `text` | string |
| `file` | `.txt` or `.pdf` upload |

**200 — `ApiResponse[EarningsReportResult]`** (illustrative; a real captured response is in
`tests/fixtures/llm_response.json`)

```json
{
  "success": true,
  "data": {
    "source_type": "pdf",
    "file_name": "q3_2026_call.pdf",
    "model": "claude-haiku-5-5",
    "report": {
      "company_name": "Acme Corp",
      "period": "Q3 2026",
      "revenue": { "amount": 4200000000, "currency": "USD", "period": "Q3 2026" },
      "guidance": [
        { "metric": "revenue", "low": 4400000000, "high": 4600000000, "period": "Q4 2026" }
      ],
      "risks": [{ "description": "Supply chain delays in Asia", "severity": "medium" }]
    },
    "usage": { "input_tokens": 14210, "output_tokens": 812 }
  },
  "meta": { "request_id": "b7e2c1f0-4a1d-4c4e-9f2a-1d2e3f4a5b6c", "processing_time_ms": 7340 }
}
```

**Errors — `ErrorResponse` (same shape for every error)**

```json
{
  "success": false,
  "error": { "code": "INPUT_TOO_LARGE", "message": "Extracted text exceeds 300000 characters" },
  "meta": { "request_id": "b7e2c1f0-4a1d-4c4e-9f2a-1d2e3f4a5b6c", "processing_time_ms": 12 }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `INVALID_INPUT` | Both / neither input, empty text |
| 413 | `INPUT_TOO_LARGE` | File > `MAX_UPLOAD_MB` or text > `MAX_TEXT_CHARS` |
| 415 | `UNSUPPORTED_FILE_TYPE` | Not `.txt` / `.pdf` |
| 422 | `FILE_PARSE_FAILED` | Corrupt PDF, scanned PDF with no text |
| 422 | `VALIDATION_ERROR` | Malformed request (FastAPI request validation) |
| 502 | `EXTRACTION_FAILED` | LLM output invalid after retries, Anthropic API error |
| 504 | `LLM_TIMEOUT` | Claude call exceeded timeout |
| 500 | `INTERNAL_ERROR` | Unexpected bug (generic message, no stack trace) |

### `GET /health`

```json
{ "success": true, "data": { "status": "ok", "environment": "dev" }, "meta": { "request_id": "...", "processing_time_ms": 0 } }
```
