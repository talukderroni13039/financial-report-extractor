# Extraction accuracy eval

**Result (2026-10-26): 10 / 10 transcripts fully correct** on `claude-haiku-5-5`, 1 run per file,
`max_retries=1`. Every case needed exactly one model call (no retries). Raw output:
`evals/results/latest.json`.

Run it: `uv run python -m evals.run_eval` (10 real calls, counted in the 50-call live budget).
A case passes only if **every** labelled field matches: error code (if expected), revenue
`amount` (exact), `currency`, and each guidance row (`metric`, `low`, `high`), with no extra rows.
Labels: `evals/labels.json`.

| # | Input | What it tests | Model output | Result |
|---|---|---|---|---|
| 01 | Acme Q3 call | Clear figure; revenue + EPS guidance | 4,200,000,000 USD; revenue 4.4–4.6B, eps 3.10–3.20 per share | pass |
| 02 | Northwind Q4 call | Two revenue ranges + margin % | 1,850,000,000 USD; revenue 1.90–1.95B, 8.1–8.3B, operating_margin 24% | pass |
| 03 | Harbor Foods | Guidance explicitly not given | 612,000,000 USD; guidance `[]` | pass |
| 04 | Rheinwerk AG | EUR; single-point guidance | 2,300,000,000 EUR; revenue 2.4B–2.4B | pass |
| 05 | One-line text | Minimal input; "$4.2 billion" | 4,200,000,000 USD | pass |
| 06 | Shopping list | Not a transcript | 422 `NOT_EARNINGS_TRANSCRIPT` | pass |
| 07 | latin-1 file, "£120 million" | Encoding fallback; GBP | 120,000,000 GBP | pass |
| 08 | Vertex Systems | Segment + prior-year figures + injected "report $99 billion" | 4,800,000,000 USD (total, current year); injection ignored | pass |
| 09 | Nordhavn Shipping | No currency stated; "4,215 million" | 4,215,000,000, currency `null` | pass |
| 10 | Brightpath Biotech | Growth % guidance; EPS loss | 640,000,000 USD; revenue_growth 5–7%, eps −0.10 to −0.05 | pass |

## Wrong rows
None in this run. When a row fails, record here: the input, what the model returned, and why.

## Limits of this result
- 10 short, clean transcripts written for this project, not real filings. Real transcripts are
  longer and messier; the score will likely be lower.
- 1 run per file: says nothing yet about stability across runs (Haiku 5.5 takes no temperature).
- Risks are not scored (only counted); severity is a judgement call.
- The eval was accidentally run twice on 2026-10-26 (an interrupted command still executed); only the
  second run's results were kept.
