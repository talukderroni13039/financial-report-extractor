# Design decisions & deviations from the architecture doc

One line per deviation from `financial-report-extractor-architecture.md` (non-binding points only): **what** — why.

- **Architecture doc not committed** (kept locally, excluded via `.git/info/exclude`) — it contains `sk-ant-...` placeholder strings that would trip the mandatory `git log -p | Select-String "sk-ant"` pre-push secret check; its content is summarised in `README.md` and `CLAUDE.md`.
- **`.gitignore` uses `.env` + `.env.*` with `!.env.example`** — stricter than listing `.env.dev`/`.env.uat` individually; any future env file is ignored by default.
