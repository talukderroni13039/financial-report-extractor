# financial-report-extractor

Extracts structured financial data (revenue, guidance, risks) from earnings call transcripts
using Claude (`claude-haiku-5-5`) + Instructor + Pydantic v2, exposed as a FastAPI service.

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

**200 — `ApiResponse[EarningsReportResult]`**

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
