# Run in VS Code & test with Postman

## 1. One-time setup

1. Install [uv](https://docs.astral.sh/uv/), VS Code, and the VS Code extensions **Python** + **Ruff**.
2. Open the repo folder in VS Code, then in the terminal (PowerShell):
   ```powershell
   uv sync                          # creates .venv
   Copy-Item .env.example .env.dev  # skip if .env.dev already exists
   ```
   Put your key in `.env.dev`: `ANTHROPIC_API_KEY=...` (never commit this file).
3. `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv` (already the default via `.vscode/settings.json`).

## 2. Run the API from VS Code

- **Debugger (F5):** open *Run and Debug* and pick **API (dev, reload)** → press F5.
  Breakpoints work in `src/`. `API (uat)` loads `.env.uat` instead (create it first).
- **Or the terminal:**
  ```powershell
  $env:APP_ENV = "dev"; uv run uvicorn src.main:app --reload --port 8000
  ```
- Check it's up: <http://localhost:8000/health> and Swagger UI at <http://localhost:8000/docs>.

**Or run it in Docker:**
```powershell
docker build -t financial-report-extractor .
docker run --rm --env-file .env.dev -p 8000:8000 financial-report-extractor
```

## 3. Test with Postman

**Import the ready-made collection:** Postman → *Import* → `postman/financial-report-extractor.postman_collection.json`.
For the file requests, re-select the file in *Body → form-data* (Postman stores file paths per machine).

**Or build a request by hand:**

| Setting | Value |
|---|---|
| Method / URL | `POST http://localhost:8000/api/v1/earnings-reports/extract` |
| Body | **form-data** (not raw/JSON) |
| Text input | key `text`, type *Text*, value = transcript |
| File input | key `file`, type *File* (hover the key cell to switch type), choose a `.txt`/`.pdf` |

Send **either** `text` **or** `file`, never both. Do not set a `Content-Type` header yourself;
Postman adds the multipart boundary.

## 4. Test files (`samples/test_files/`)

| File | Expected result |
|---|---|
| `01_full_quarter_with_guidance.txt` | 200: revenue 1850000000, 2 guidance items, 3 risks (one high) |
| `02_no_guidance.txt` | 200: revenue 612000000, `guidance: []` |
| `03_euro_company.txt` | 200: currency `EUR`, revenue 2300000000 |
| `04_short_one_liner.txt` | 200: revenue 4200000000 (amount normalisation) |
| `05_empty.txt` | 400 `INVALID_INPUT` (empty transcript) |
| `06_not_a_transcript.txt` | 200 with mostly null/empty fields (nothing invented) |
| `07_latin1_encoded.txt` | 200: latin-1 fallback decoding, currency `GBP` |
| `samples/q3_2026_acme_call.pdf` | 200: `source_type: "pdf"` |
| any `.docx` / `.png` | 415 `UNSUPPORTED_FILE_TYPE` |

Every 200 response is `{success, data, meta}`; every error is `{success: false, error: {code, message}, meta}`.
Check the `X-Request-ID` response header and match it in the server logs.

> Each successful extract is one or more **real, billed** Claude calls (~2.5K input tokens per small transcript).
> Error cases (400/413/415/422) never reach the LLM.

## 5. Run the tests in VS Code

- *Testing* sidebar (beaker icon) → run all; this runs the mocked suite only, with no API cost.
- Or `uv run pytest`. Live tests: `uv run pytest -m live --no-cov` (real calls, budget-capped at 50).
