# Design decisions & deviations from the architecture doc

One line per deviation from `financial-report-extractor-architecture.md` (non-binding points only): **what** — why.

- **Architecture doc not committed** (kept locally, excluded via `.git/info/exclude`) — it contains API-key placeholder strings that would trip the mandatory pre-push secret grep; its content is summarised in `README.md` and `CLAUDE.md`.
- **`.gitignore` uses `.env` + `.env.*` with `!.env.example`** — stricter than listing `.env.dev`/`.env.uat` individually; any future env file is ignored by default.
- **Coverage uses `core = "sysmon"`, line (not branch) coverage** — the default C tracer takes ~60 s to import pypdf's glyph tables on this machine; sysmon on Python 3.12 has no branch support.
- **`LLM_MAX_RETRIES` default is 2 (doc: 3 in dev)** — in Instructor `max_retries=N` means up to N+1 calls, so 2 = 3 attempts max; keeps cost bounded.
- **`ExtractorClient` Protocol also exposes a `model` property** — the service needs the model name for `EarningsReportResult.model` without depending on Anthropic or env vars.
- **User message wraps the transcript in `<transcript>` tags and the prompt says to ignore instructions inside it** — standard prompt-injection hygiene for untrusted documents.
- **No `temperature` sent** — Claude Haiku 5.5 rejects non-default sampling parameters (400).
- **Live-call budget counted at the HTTP layer** (httpx request hook on a dedicated `AsyncAnthropic` with SDK retries off) — counts every attempt incl. Instructor re-asks exactly; also used by `scripts/capture_llm_fixture.py`.
- **`main.create_app()` factory** — lets tests build isolated apps (e.g. temporary failing routes) without touching the global `app`.
- **Global handler also registered for `RequestValidationError` and Starlette `HTTPException`** — still one handler function; otherwise FastAPI's default 422/404 bodies would break the "every error uses `ErrorResponse`" rule. Validation messages never echo submitted values.
- **`/health` returns the `ApiResponse` envelope** (`data.status`, `data.environment`) — binding rule "every endpoint uses the envelope" wins over the doc's bare `{status, environment}` example.
- **Request-ID middleware is pure ASGI and honours a safe incoming `X-Request-ID`** (≤128 chars, `[A-Za-z0-9._-]`) — avoids `BaseHTTPMiddleware` overhead/contextvar issues and supports tracing across services; the handler also sets the header so 500s carry it.
- **Dockerfile copies the `uv` binary from `ghcr.io/astral-sh/uv:0.13.1` into `python:3.12-slim-bookworm`** — the combined `uv:…-python3.12-bookworm-slim` tag does not exist for this uv version; runtime stage has no uv, runs as non-root `app`, includes a `HEALTHCHECK`, and defaults `APP_ENV=uat` (overridable).
- **Upload size is enforced in the service after Starlette has spooled the multipart body** — the doc's design; it bounds processing and LLM cost, but a hard request-body limit should also be set at the reverse proxy / ingress in deployed environments.
- **`.dockerignore` also excludes `tests/`, `samples/`, `scripts/`, docs** — smaller image; only `src/` + the venv ship.
- **Added `tests/fakes.py`, `tests/pdf_factory.py`, `tests/live_budget.py`, `scripts/capture_llm_fixture.py`** — fake `ExtractorClient`, in-memory text PDFs (no PDF-writing dependency), the 50-call budget guard, and the one-shot fixture capture.
- **Extra mocked tests beyond the doc** (Anthropic client error mapping, middleware/handler, budget guard) — needed for the ≥80% coverage gate and to prove the budget guard blocks at 50.
- **JSON structured logs (`core/logging_config.py`) with request ID via contextvar** — doc only had `basicConfig`; task requires structured logging. Third-party HTTP/SDK loggers are capped at WARNING so request bodies are never logged.
