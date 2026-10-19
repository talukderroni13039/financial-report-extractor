# CLAUDE.md

## Project summary
FastAPI service that extracts structured financial data (revenue, guidance, risks) from earnings
call transcripts (raw text, `.txt`, `.pdf`) using Claude (`claude-haiku-5-5`) via Instructor + Pydantic v2.
One endpoint: `POST /api/v1/earnings-reports/extract`, plus `GET /health`.

## Commands (PowerShell)
```powershell
uv sync                                                      # install (Python 3.12, locked by uv.lock)
$env:APP_ENV = "dev"; uv run uvicorn src.main:app --reload   # run dev  (loads .env.dev)
$env:APP_ENV = "uat"; uv run uvicorn src.main:app            # run uat  (loads .env.uat)
uv run pytest                                                # mocked tests + coverage (zero API calls)
uv run pytest -m live --no-cov                               # live tests — costs money, counts against budget
uv run ruff check .                                          # lint
uv run ruff format .                                         # format
uv run mypy src                                              # type check (strict)
uv run pre-commit install                                    # optional: git hooks (ruff + mypy)
docker build -t financial-report-extractor .
docker run --rm --env-file .env.uat -p 8000:8000 financial-report-extractor
```

## Architecture rules
- `src/main.py` — loads `.env.{APP_ENV}` FIRST, configures logging, builds the app, registers middleware,
  the global exception handler and `api_router`. No endpoints.
- `src/api_router.py` — `APIRouter(prefix="/api/v1")` that only includes domain routers.
- `src/core/` — cross-cutting code, no business logic: `dependencies.py` (ALL DI providers),
  `exceptions.py` (`AppError` + subclasses), `exception_handlers.py` (ONE handler function),
  `middleware.py` (request ID + timing), `logging_config.py` (JSON logs), `health.py`,
  `schemas/api_response.py` (`ApiResponse[T]`, `ErrorResponse`, `ResponseMeta`).
- `src/domains/<domain>/` — one package per business feature, subfolders:
  `routers/` (HTTP only), `schemas/` (Pydantic), `services/` (business logic), `prompts/` (prompt text only).
  No domain-level `dependencies.py` or `constants.py`.
- `src/llm/` — `base.py` (`ExtractorClient` Protocol), provider implementations (`anthropic_client.py`).
- `src/utils/` — pure helpers with no LLM/HTTP knowledge (e.g. `file_reader.py`).
- **Layer rule:** router → service → client. Routers never call the LLM and contain no business logic.
  Services depend on the `ExtractorClient` Protocol (never on Anthropic directly) and never raise
  HTTP-specific errors (`HTTPException`) — they raise `AppError` subclasses.
- Config: no settings class. Read env with `os.getenv("X", default)` **at call time**, with a safe default.

## Naming conventions
- Modules: snake_case with role suffixes — `*_service.py`, `*_prompt.py`, `*_client.py`, `api_endpoints.py`,
  `*_result.py` (API payload schema), `llm_extraction.py` (Instructor `response_model`).
- Classes: PascalCase. `*Result` = domain data placed in `ApiResponse.data` (e.g. `EarningsReportResult`).
  `*Error` = `AppError` subclasses. `*Service`, `*Client`.
- DI providers: `get_<thing>()` in `core/dependencies.py`.

## Response contract
- Every endpoint declares `response_model=ApiResponse[<DomainResult>]` and returns
  `ApiResponse(data=..., meta=ResponseMeta.from_request(request))`. Never return raw dicts.
- Every expected error is raised as an `AppError` subclass (`status_code` + `code`) and rendered by
  `core/exception_handlers.global_exception_handler` as `ErrorResponse`. Unknown exceptions → 500
  `INTERNAL_ERROR`, generic message, traceback only in logs. `X-Request-ID` header on every response.

## How to add a new feature
1. Create `src/domains/<new_domain>/` with `__init__.py` and `routers/`, `schemas/`, `services/`, `prompts/` (each with `__init__.py`).
2. `schemas/`: request/LLM models + a `<Thing>Result` for `ApiResponse.data`; re-export in `schemas/__init__.py`.
3. `prompts/<thing>_prompt.py`: prompt text constants only.
4. `services/<thing>_service.py`: class taking its dependencies (Protocols) in `__init__`; raises `AppError` subclasses.
5. New LLM call shape? Add a Protocol to `llm/base.py` and implement it in `llm/`.
6. `routers/api_endpoints.py`: `router = APIRouter(prefix="/<things>", tags=[...])`, thin endpoint using `Depends`.
7. Add DI providers (`get_<thing>_service`, singletons via `lru_cache`) to `core/dependencies.py`.
8. Include the router in `src/api_router.py`.
9. Add new error types to `core/exceptions.py` (subclass `AppError`, set `status_code` + `code`).
10. Tests: `tests/unit/` (schemas, service with a fake client) and `tests/integration/` (TestClient +
    `app.dependency_overrides`). Optional live tests in `tests/live/` with `@pytest.mark.live`.
11. Update README (contract + error codes) and `docs/DECISIONS.md` if you deviate from these rules.

## How to add a database later
- `src/core/database.py` — engine + session factory; session provider in `core/dependencies.py`.
- `src/domains/<domain>/models/` — SQLAlchemy ORM tables. `schemas/` stays Pydantic. **Never mix them.**
- `src/domains/<domain>/repositories/` — query layer; flow becomes service → repository → DB.
- `alembic/` + `alembic.ini` at the repo root (standard Alembic layout).

## Testing rules
- Default `uv run pytest` is fully mocked (`addopts` excludes `-m live`): `tests/fakes.py`
  `FakeExtractorClient` via `app.dependency_overrides[get_llm_client]` (see `tests/conftest.py`),
  reusing `tests/fixtures/llm_response.json`. Build test PDFs with `tests/pdf_factory.build_pdf`.
- `tests/conftest.py` sets `APP_ENV=test` before importing the app, so no real key is loaded.
- Re-capture the fixture only via `uv run python -m scripts.capture_llm_fixture` (1 budgeted call).
- Live tests: `@pytest.mark.live`, max 5 cases, `max_retries=1`, short transcript fixtures.
- **Hard budget: 50 real Anthropic calls total**, tracked in `tests/.live_call_budget.json` (gitignored) by
  `tests/live_budget.py` (httpx request hook on the live client), which counts every HTTP attempt and
  fails with "live API budget exhausted" at 50. Never reset or edit that file to get more calls.
- Coverage ≥ 80% on `src/` (enforced by `--cov-fail-under=80`). Never run live tests in CI.

## Security and cost rules
- API key only in `.env.dev` / `.env.uat` (gitignored) and read only via `os.getenv("ANTHROPIC_API_KEY")`.
- Never print, log, echo or commit keys or env files; never log transcript content.
- `.env.example` holds placeholders only. Non-secret vars always have safe code defaults.
- Keep `MAX_TEXT_CHARS` / `MAX_UPLOAD_MB` enforced before every LLM call.

## Do not
- Add a settings/config class or a DI container library.
- Put business logic or validation in routers, or call the LLM from a router.
- Return raw dicts from endpoints or raise `HTTPException` from services.
- Call the real API in non-live tests, or run live tests in CI.
