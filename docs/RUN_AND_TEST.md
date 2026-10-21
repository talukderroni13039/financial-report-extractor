# How to run and test the API (step by step, Windows + VS Code)

You do **not** run `python main.py`. The app is started with **uvicorn** through **uv**,
from the **project root folder**. Follow the steps in order.

---

## Step 1 — Open the RIGHT folder in VS Code

The project root is the folder that contains `pyproject.toml`:

```
D:\Techjays\Projects\financial_report_extractor\financial-report-extractor
```

> Careful: there are two similarly named folders. `financial_report_extractor` (underscores) is the
> **parent**. Open the inner one, `financial-report-extractor` (dashes).

In VS Code: **File → Open Folder…** → select `financial-report-extractor` → **Select Folder**.

Check: the Explorer sidebar should show `src`, `tests`, `pyproject.toml`, `README.md` at the top level.

---

## Step 2 — Open a terminal in VS Code

**Terminal → New Terminal** (or press `` Ctrl+` ``). It opens PowerShell **already in the project root**.

Check you are in the right place:

```powershell
Get-Location
# must print: D:\Techjays\Projects\financial_report_extractor\financial-report-extractor
```

If it prints something else, move there:

```powershell
cd D:\Techjays\Projects\financial_report_extractor\financial-report-extractor
```

All commands below are run **from this folder**. Never `cd` into `src`.

---

## Step 3 — One-time setup (only the first time)

```powershell
uv --version          # should print something like: uv 0.13.1
uv sync               # installs Python 3.12 + all packages into .venv
```

- If `uv` is "not recognized": close VS Code completely and open it again (it was installed after
  VS Code started). Still failing? Install it: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`, then restart VS Code.
- `.env.dev` already exists with your API key. If it ever goes missing:
  `Copy-Item .env.example .env.dev`, then open `.env.dev` and set `ANTHROPIC_API_KEY=...`.

Optional (for code highlighting / debugging): `Ctrl+Shift+P` → **Python: Select Interpreter** →
choose the one that shows `.venv` (`.\.venv\Scripts\python.exe`).

---

## Step 4 — Start the API

Pick **one** way.

### Option A — terminal command (simplest)

```powershell
$env:APP_ENV = "dev"
uv run uvicorn src.main:app --reload --port 8000
```

It is running when you see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

Leave this terminal open (the API runs inside it). Stop it with `Ctrl+C`.

### Option B — VS Code Run button (with debugger / breakpoints)

1. Click the **Run and Debug** icon in the left bar (play button with a bug), or press `Ctrl+Shift+D`.
2. In the dropdown at the top choose **API (dev, reload)**.
3. Press the green ▶ button (or `F5`).
4. Output appears in the **Debug Console / Terminal**; stop with the red ■ button (`Shift+F5`).

### Option C — Docker (no Python needed)

```powershell
docker build -t financial-report-extractor .
docker run --rm --env-file .env.dev -p 8000:8000 financial-report-extractor
```

(Docker Desktop must be running.)

---

## Step 5 — Open Swagger and try the endpoint in the browser

1. Open <http://localhost:8000/health> → you should see `"status":"ok","environment":"dev"`.
2. Open **Swagger UI**: <http://localhost:8000/docs>
3. Click **POST /api/v1/earnings-reports/extract** → **Try it out**.
4. Use **only one** of the two fields:
   - **text:** paste a transcript, e.g.
     `Initech Q1 2026: total revenue for the quarter was $4.2 billion.`
     (leave `file` empty), **or**
   - **file:** click **Choose File** → pick a file from `samples\test_files\` or `samples\q3_2026_acme_call.pdf`
     (leave `text` empty).
5. Click **Execute**. After 2–5 seconds the **Response body** shows `"success": true` and the extracted data.

Other URLs: ReDoc <http://localhost:8000/redoc>, raw OpenAPI <http://localhost:8000/openapi.json>.

---

## Step 6 — Test with Postman

### Easiest: import the ready-made collection

1. Postman → **Import** → choose file
   `D:\Techjays\Projects\financial_report_extractor\financial-report-extractor\postman\financial-report-extractor.postman_collection.json`.
2. A collection **Financial Report Extractor** appears with 7 requests.
3. Run **Health** first (should return 200).
4. For each request that sends a **file**: open it → **Body** tab → in the `file` row click
   **Select Files** and pick the file again from `samples\test_files\` (Postman can't keep file paths
   between machines).
5. Click **Send**.

### Or create a request yourself

| Where | What to set |
|---|---|
| Method + URL | `POST` · `http://localhost:8000/api/v1/earnings-reports/extract` |
| Body tab | choose **form-data** (NOT raw / JSON) |
| To send text | Key `text` · type **Text** · Value = the transcript |
| To send a file | Key `file` · hover the key cell → change **Text** to **File** · **Select Files** → pick `.txt` or `.pdf` |
| Headers | add nothing; Postman sets `Content-Type` automatically |

Send **either** `text` **or** `file`, not both (both → 400 error).

---

## Step 7 — Test files and what you should get

All files are in `samples\test_files\` (plus one PDF in `samples\`).

| File | Expected result |
|---|---|
| `01_full_quarter_with_guidance.txt` | 200, revenue `1850000000`, 2 guidance items, 3 risks |
| `02_no_guidance.txt` | 200, revenue `612000000`, `"guidance": []` |
| `03_euro_company.txt` | 200, `"currency": "EUR"`, revenue `2300000000` |
| `04_short_one_liner.txt` | 200, revenue `4200000000` |
| `05_empty.txt` | 400 `INVALID_INPUT` (empty transcript) |
| `06_not_a_transcript.txt` | 200, mostly `null` / empty lists (nothing invented) |
| `07_latin1_encoded.txt` | 200, `"currency": "GBP"` |
| `samples\q3_2026_acme_call.pdf` | 200, `"source_type": "pdf"`, revenue `4200000000` |
| any `.docx` / `.png` | 415 `UNSUPPORTED_FILE_TYPE` |

Success shape: `{ "success": true, "data": {...}, "meta": { "request_id", "processing_time_ms" } }`
Error shape: `{ "success": false, "error": { "code", "message" }, "meta": {...} }`

> Each successful extract is a **real, paid** Claude call (very cheap with Haiku, ~2.5K tokens for a small file).
> Error cases (400/413/415/422) never call Claude.

---

## Step 8 — Run the automated tests (free, no API calls)

In a **second** terminal (the first one is running the API), from the project root:

```powershell
uv run pytest            # all mocked tests + coverage, ~10 seconds
uv run ruff check .      # lint
uv run mypy src          # type check
```

Or click the **Testing** icon (beaker) in the left bar → ▶ **Run Tests**.

---

## FAQ

**Why `uv run` and not `python`?** `uv run` always uses *this* project's `.venv` (and installs anything
missing from `uv.lock` first). Plain `python` uses whichever Python is first on your PATH, which may be
a global one without the packages. The equivalent without uv is:
`.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload`

**Which environment is running?** Three places show it:
1. The startup log line: `Started in 'dev' environment | Swagger UI: http://127.0.0.1:8000/docs | env file: .env.dev (loaded) | python: ...\.venv\Scripts\python.exe`
2. The Swagger page title: **Financial Report Extractor API [dev]**
3. <http://localhost:8000/health> → `"environment": "dev"`

`APP_ENV` defaults to `dev`. For UAT: `$env:APP_ENV = "uat"` then start again (loads `.env.uat`).
`$env:APP_ENV` only lasts for that terminal window.

**Is it running from this project's venv?** The startup line prints `python: ...\financial-report-extractor\.venv\Scripts\python.exe`.
You can also run `uv run python -c "import sys; print(sys.executable)"`. In VS Code the bottom-right status bar shows the selected interpreter (`.venv`).

**Can other projects interfere?** No. Each project has its own `.venv` folder, and `uv run` picks the
`.venv` next to the `pyproject.toml` of the folder you're in. Only the **port** is shared: if another
app already uses 8000, start this one with `--port 8001`.

## Problems?

| You see | Fix |
|---|---|
| `uv : The term 'uv' is not recognized` | Restart VS Code (see Step 3). |
| `Could not import module "src.main"` / `No module named 'src'` | You are in the wrong folder. Do Step 2 (`cd` to the project root). |
| `error: No pyproject.toml found` | Wrong folder: you're in the parent `financial_report_extractor`. Do Step 2. |
| `[Errno 10048] ... address already in use` | API already running in another terminal. Stop it (`Ctrl+C`) or use `--port 8001`. |
| Browser: "This site can't be reached" | The API isn't running. Do Step 4 and keep that terminal open. |
| 502 `EXTRACTION_FAILED` | API key missing/wrong in `.env.dev`, or no credit. Check the key, then restart the API. |
| 504 `LLM_TIMEOUT` | Claude was slow; retry. |
| 400 "not both" in Swagger/Postman | You filled both `text` and `file`; clear one. |
