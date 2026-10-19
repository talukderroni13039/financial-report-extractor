# Next steps

Status (2026-10-19): extraction API complete on `feature/extraction`; ruff/mypy/mocked tests green
(99.7% coverage); 5 live tests passed; live API budget used: 6/50.

## Do now
1. **Open a PR** `feature/extraction` → `main` on GitHub and confirm the CI workflow passes.
2. **Create `.env.uat`** (gitignored) with at least `APP_ENV=uat`, `LOG_LEVEL=INFO`, and a **separate UAT key**
   `ANTHROPIC_API_KEY=...`, then smoke-test: `docker run --rm --env-file .env.uat -p 8000:8000 financial-report-extractor`.
3. **Set spend limits + email alerts** per workspace (dev, UAT) in the Claude Console.
4. `uv run pre-commit install` on every dev machine.
5. Try the `samples/test_files/` set through Postman (see `docs/RUN_AND_TEST.md`) and review output quality.

## Before production
- **Authentication:** the API is open. Add an API-key header or OAuth/JWT (new dependency in `core/dependencies.py`).
- **Request size limit at the proxy/ingress** (e.g. 10 MB): uploads are checked only after Starlette has buffered them.
- **Rate limiting** per client, since each request costs money.
- **Deployment:** push the image to a registry (GHCR/ECR), and run it behind HTTPS with the `/health` probe.
- **Monitoring:** ship JSON logs to your log platform; alert on 5xx, `LLM_TIMEOUT`, `EXTRACTION_FAILED` rates and token usage.

## Product / quality improvements
- **Eval set:** 20–50 real transcripts with expected values to measure extraction accuracy before changing prompt/model.
- **Long transcripts:** chunking or summarisation for inputs above `MAX_TEXT_CHARS`.
- **Scanned PDFs:** optional OCR (e.g. Tesseract) instead of returning 422.
- More fields if needed (EPS, margins, segment revenue), which means extending `schemas/llm_extraction.py` + prompt.
- Persist results (follow "How to add a database later" in `CLAUDE.md`).

## Housekeeping
- `docs/DECISIONS.md` lists every deviation from the original architecture doc. Review and accept them.
- The architecture doc is kept locally only (excluded via `.git/info/exclude`) because its key placeholders trip the secret grep.
- The step 1 commit contains the API-key placeholder prefix in a docs note (no real key; verified),
  so the pre-push secret grep over `git log -p` matches it. Squash-merge the PR to keep `main` free of it.
