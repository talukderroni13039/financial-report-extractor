# What can go wrong when you use an AI model: examples from your project
Week 1 · Financial Report Extractor

Hi there,

This week's idea: **an AI model is not a normal function.** A normal function gives the same output for the same input and never invents things. A model can do both, and it can return a clean, well-formed answer that is still wrong. Five problems follow.

Each problem has an example, a picture, the words people use for it, where it shows up in *your* project, and **possible solutions**. These are options. Use whatever fits.

There is nothing to write back. Read it, open your code, and see what you recognise. If it helps to talk any of it through, just say.

> The AI outputs below are **made-up examples** of what a model *could* return. They show the type of problem. Your own runs may look different.

---

## 1. Valid shape is not valid meaning (the retry loop needs checks that can say "no")

**Example**

```
 TRANSCRIPT (input)                    WHAT THE MODEL RETURNS (output)
 ┌─────────────────────────────┐       ┌──────────────────────────────────┐
 │ "Total revenue was          │       │ revenue.amount: 4200000          │
 │  $4.2 billion, up 8%."      │ ────► │                  ▲               │
 └─────────────────────────────┘       │   a valid float >= 0, but 1000x  │
                                       │   too small                      │
                                       └──────────────────────────────────┘
        Pydantic: ✅ accepted   →   no retry   →   API returns 200
```

The JSON has the right fields and the right types. It looks fine. But the number is wrong, and nothing in the program notices.

This is how the retry loop works:

```
   ┌──────────────┐
   │ Send text +  │
   │ schema       │
   └──────┬───────┘
          ▼
   ┌──────────────┐    NO     ┌───────────────────────────────┐
   │ Model answers├──────────►│ Do your checks accept it?     │
   └──────────────┘           └───────┬───────────────┬───────┘
          ▲                      YES  │               │ NO
          │                          ▼               ▼
          │                   ┌────────────┐  ┌───────────────────────┐
          │                   │ Use result │  │ Send the ERROR TEXT   │
          └───────────────────┴────────────┘  │ back to the model     │
                  (try again, up to max_retries)└──────────┬───────────┘
                                                           ▼ after N tries
                                                  ┌──────────────────┐
                                                  │ GIVE UP: now what?│
                                                  └──────────────────┘
```

The loop only helps with problems your checks can detect. If every wrong answer looks valid, the loop never runs.

**Words**
- **Validation**: checking the model's answer against rules.
- **Semantic validation**: checking the *meaning* ("is this value really in the source?"), not only the type.
- **Grounding**: every fact in the output can be found in the input.
- **Max retries**: the limit on tries. After the last one the program needs a plan.

**Why it is dangerous:** a schema checks the *shape* of an answer, not whether it is *true*. A wrong revenue number that is a valid `float` goes straight into a dashboard or a trading model.

**In your project:**
- The retry loop is set on purpose: `max_retries` defaults to 2, and `DECISIONS.md` explains that this means up to 3 attempts (`anthropic_client.py:45-48`). That is the right tool, and the reason is written down.
- The checks that can trigger a retry are `amount >= 0` (`llm_extraction.py:20-26`), the currency pattern (`:27-31`) and `low <= high` (`:63-67`). Nothing checks that a number or name appears in the transcript. We haven't run it, but a segment figure, or a number with the wrong number of zeros, would be accepted.
- After the last retry, the caller gets a generic "Could not extract a valid earnings report" (`anthropic_client.py:69-82`). The log keeps `error_type` and `status_code`, not which field broke which rule. So "model kept writing bad data" and "network problem" look alike.

**Possible solutions**

*A. Make the model show its proof, then check the proof in code.* Ask for the exact words next to each number. A validator checks that those words really are in the transcript. A rejection goes back to the model as a retry.

```python
class Revenue(BaseModel):
    amount: float = Field(ge=0, ...)
    quote: str = Field(description="Exact words from the transcript that state this figure, e.g. '$4.2 billion'")

class EarningsReport(BaseModel):
    ...
    @model_validator(mode="after")
    def revenue_quote_in_text(self, info: ValidationInfo):
        text = " ".join((info.context or {}).get("source_text", "").split())
        if self.revenue and " ".join(self.revenue.quote.split()) not in text:
            raise ValueError(f"revenue.quote not found in the transcript: {self.revenue.quote!r}. Copy it exactly.")
        return self

# anthropic_client.py: give the validator the transcript
await self._client.messages.create_with_completion(..., response_model=EarningsReport,
                                                   validation_context={"source_text": text})
```
Check the `validation_context` name and `ValidationInfo` in the Instructor and Pydantic docs for your installed versions (links at the end).

*B. Add plausibility checks.* For example: revenue must be at least some floor, guidance for a period should be within a sane range of the reported revenue, `revenue.period` should equal `report.period`. These catch the 1000x case without any extra field.

*C. Decide what happens after the last retry, and keep the reason.* Catch the Instructor exception, log which fields were rejected, and return a message that says "the model could not produce a valid report" instead of a general failure.

```python
from instructor.exceptions import InstructorRetryException

except InstructorRetryException as exc:
    logger.warning("extraction rejected after retries", extra={"detail": str(exc)[:500]})
```
Check the exception name and what it carries in the Instructor docs.

**How to check it works:** make a fake model answer with `amount=4200000` for "$4.2 billion" (a test with your `tests/fakes.py` client works). The report should be rejected, not returned with status 200.

---

## 2. The model does arithmetic that code does exactly (model vs code)

**Example**

```
 TEXT: "$4.2 billion"  →  MODEL must write 4 2 0 0 0 0 0 0 0 0  (9 zeros)
                          one zero too many or too few = 10x wrong

 TEXT: "$350 million"  →  350000000
 TEXT: "£1.5B"         →  1500000000
```

Models are good at reading messy text. They are less reliable at long exact numbers, and the same input may not give the same answer every time.

```
  ┌─────────────────────────────┐     ┌─────────────────────────────┐
  │ MODEL (language)            │     │ CODE (exact, repeatable)    │
  │ • find the figure in text   │     │ • "billion" → × 1_000_000_000│
  │ • say which unit it used    │     │ • rounding, sums, ranges    │
  └─────────────────────────────┘     └─────────────────────────────┘
```

**Words**
- **Non-deterministic**: the same input can give different outputs.
- **Normalisation**: turning "$4.2B" and "4.2 billion" into one standard form.

**Why it is dangerous:** every job you give the model is a place where it can be wrong, and you cannot unit-test it. A multiplication in code is right every time.

**In your project:** the prompt (`extraction_prompt.py:10-11`) and the field descriptions (`llm_extraction.py:22-25`, `:50-52`) ask the model to write the full number. Your `test_live_amount_normalization` (`tests/live/test_live_extraction.py:66`) shows it worked on that input. A single input does not show how often it works.

**Possible solutions**

*A. The model reports what the text says. Code multiplies.*

```python
Unit = Literal["ones", "thousand", "million", "billion", "trillion"]
MULTIPLIER = {"ones": 1, "thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}


class Revenue(BaseModel):
    value: float = Field(ge=0, description="The number as written, e.g. 4.2 for '$4.2 billion'")
    unit: Unit

    @property
    def amount(self) -> float:
        return self.value * MULTIPLIER[self.unit]
```

*B. Keep the model's full number, and let code cross-check it.* If you use the quote from section 1, a small function can parse "$4.2 billion" and compare it with `amount`. A mismatch is a validation error, so it triggers a retry.

**How to check it works:** run `$4.2 billion`, `$350 million`, `1.85B` and `EUR 2.3 billion` (from your sample files). The amounts should be exact every time, and a unit test on the multiplier needs no API call.

---

## 3. An empty answer looks like success (unknown handling and quiet failure)

**Example**

```
 INPUT  "Shopping list: eggs, milk, bread, coffee."
        ──► MODEL ──►  { company_name: null, revenue: null, guidance: [], risks: [] }
                                       │
                                       ▼
                      API: 200 OK    "success"

 INPUT  "...we will not be providing guidance..."   (a real transcript)
        ──► MODEL ──►  { revenue: {...}, guidance: [], risks: [...] }
                                       │
                                       ▼
                      API: 200 OK    "success"   (and this one is right)
```

Both answers look the same to the program: an empty `guidance` list. In one case the list is empty because management said nothing. In the other it is empty because there was nothing to read.

**Words**
- **Null / unknown**: an honest "not in the text". Allowing it is the right design.
- **Quiet failure**: the system fails but reports "all good".
- **Forced default**: the schema or prompt fills in a value the text does not support.

**Why it is dangerous:** a pipeline that reads 10,000 transcripts will see some PDFs that are the wrong document, a page of legal text, or a half-extracted file. If "found nothing" and "nothing there" look the same, a company can silently show up as "no risks, no guidance".

**In your project:**
- ✅ Making everything optional, and telling the model "never infer" (`llm_extraction.py:87-106`, `extraction_prompt.py:8-9`), is the right way to allow "unknown". `test_live_no_guidance_is_not_invented` (`test_live_extraction.py:56`) tests the important case.
- `docs/RUN_AND_TEST.md:156` expects the shopping-list file to give "200, mostly null / empty lists". That is the model behaving well, but the API still reports success.
- Currency has a default in two places: the prompt says "default to USD" (`extraction_prompt.py:21`) and the schema has `default="USD"` (`llm_extraction.py:28`, `:30`). That conflicts with "never infer" in rule 1. If the transcript gives no currency, the output says USD with full confidence.

**Possible solutions**

*A. Let the model say what kind of document it saw.*

```python
class EarningsReport(BaseModel):
    is_earnings_call: bool = Field(
        description="False if the text is not an earnings call transcript"
    )
    ...
```
The service can then return a clear "not an earnings transcript" error.

*B. Check for an empty result in the service.* If `revenue is None and not guidance and not risks`, return a distinct status ("nothing found, please check the file") instead of a plain success. A transcript that says "no guidance" still has revenue, so it goes through.

*C. Currency can be unknown too.* Make `currency: str | None = None`, say "null if not stated" in the prompt, and let the caller decide what to do with `None`.

**How to check it works:** `06_not_a_transcript.txt` should produce the "not a transcript" response. `02_no_guidance.txt` should still return revenue and an empty guidance list.

---

## 4. One field holds three kinds of numbers (units and meaning in the schema)

**Example**

```
 "revenue of $4.4B to $4.6B"          → low 4400000000     high 4600000000
 "EPS of $3.10 to $3.20"              → low 3.1            high 3.2
 "operating margin ~24 percent"       → low 24   or 0.24 ? high 24  or 0.24 ?
                                           ▲
                    same two fields, three units, no label for the unit
```

**Words**
- **Schema design**: the schema is the contract with the model. If two things mean different things, they need different fields or a field that says which.
- **Free text vs enum**: free text lets the model choose any wording, so "operating margin", "Op. margin" and "OM" all appear.

**Why it is dangerous:** a person who reads `low: 24` next to `low: 4400000000` knows what each means. A program that compares guidance with next quarter's actual numbers does not.

**In your project:** `Guidance.metric` is a free string (`llm_extraction.py:44-47`). `low` and `high` are plain floats (`:48-57`). The prompt gives an EPS example of `3.10` (`extraction_prompt.py:11`), while the field says "full number in currency units" (`llm_extraction.py:50`). Your sample `01_full_quarter_with_guidance.txt` has revenue, a fiscal-year range and an "approximately 24 percent" margin in one file. We haven't run it, so it is a risk and not an observed result. Likewise `Revenue.period` and `EarningsReport.period` are free strings with no check that they agree.

**Possible solutions**

*A. Fix the list of metrics and say the unit.*

```python
class Guidance(BaseModel):
    metric: Literal["revenue", "eps", "operating_margin", "gross_margin", "other"]
    unit: Literal["currency", "per_share", "percent"]
    ...

    @model_validator(mode="after")
    def percent_is_0_to_100(self):
        if self.unit == "percent" and any(
            v is not None and not 0 <= v <= 100 for v in (self.low, self.high)
        ):
            raise ValueError("percent guidance must be between 0 and 100, e.g. 24 for 24 percent")
        return self
```

*B. Add a consistency check on periods.* A validator that `revenue.period == period` (or both are normalised) catches mixes of "Q3 2026" and "FY2026".

**How to check it works:** run `01_full_quarter_with_guidance.txt`. Each guidance row should carry a unit, and the margin should read 24 every time.

---

## 5. "It works" without numbers (evaluation)

**Example: what an eval looks like.** You write the correct answers for a set of transcripts (the **ground truth**), run the model, and compare field by field. The table is made-up:

```
 file                         field            correct (you wrote)   model returned   result
 ───────────────────────────  ───────────────  ────────────────────  ───────────────  ──────
 01_full_quarter_...          revenue.amount   1850000000            1850000000       ✅
 01_full_quarter_...          guidance (count) 3                     3                ✅
 01_full_quarter_...          margin low       24                    0.24             ❌ unit
 02_no_guidance               guidance         []                    []               ✅
 03_euro_company              currency         EUR                   EUR              ✅
 ...
 ───────────────────────────────────────────────────────────────────────────────────────────
 revenue exact: 6/7     guidance precision 0.80  recall 0.90     risk severity agree: 5/9
```

Then read the wrong rows (**error analysis**): why `0.24`? That tells you what to fix in the prompt or schema. Run it 3 times per file as well. Haiku does not accept a temperature setting (your `DECISIONS.md` notes this), so the repeat runs show how stable the answers are.

```
   labelled      run the       compare       read the       change prompt
   files ──────► model  ─────► per field ──► wrong rows ──► or schema ───┐
     ▲                                                                    │
     └──────────────────── run again: did the numbers go up? ◄───────────┘
```

**Words**
- **Eval (evaluation)**: a repeatable test that measures AI quality with numbers.
- **Ground truth / labelled set**: examples with the correct answer written by a human.
- **Precision / recall**: of what the model returned, how much was right / of what was really there, how much it found.
- **Regression**: you change the prompt and something that worked before now breaks. An eval shows it.

**In your project:**
- ✅ `docs/NEXT_STEPS.md:22` already lists "Eval set: 20–50 real transcripts with expected values". It is planned; it does not exist yet.
- The 5 live tests (`tests/live/test_live_extraction.py:25-76`) use two fixture transcripts and one inline sentence, and check revenue, "guidance is empty" and the PDF path. They are a good smoke test. They do not give a number for guidance, risks or severity, and each runs once.
- `RUN_AND_TEST.md:151-157` already has expected values for the sample files. They can seed the labels.

**Possible solutions**

*A. A labels file.* One JSON file with the correct values for the 7 sample files plus the fixtures (revenue, currency, each guidance row with unit, risk count). About an hour of work.

*B. A script that scores each field in the right way.*

```python
# evals/run_eval.py   (calls the real model; mind your live-call budget)
labels = json.loads(Path("evals/labels.json").read_text())
for name, truth in labels.items():
    for run in range(3):
        report, _ = await client.extract(Path(f"samples/test_files/{name}").read_text())
        got = report.revenue.amount if report.revenue else None
        print(name, run, "revenue ok" if got == truth["revenue"] else f"revenue WRONG {got}")
```
Different fields need different metrics: exact match for amounts and currency, precision and recall for lists, agreement for severity.

*C. Write down 3 wrong rows.* In an `EVAL.md`: the input, what the model returned, and why.

*D. Compare with a baseline.* For example a regex that finds "revenue ... $X billion". If the model barely beats it, the model is not earning its cost.

**How to check it works:** you can answer "how accurate is the extractor on revenue, guidance and risks?" with a table, and "does it give the same answer on a second run?" with a number.

---

## Cheat sheet

| Problem | One-line test you can run on any AI project |
|---|---|
| Valid shape ≠ valid meaning | What wrong answer would still be accepted by my checks? |
| Retry loop | Is the error sent back, is there a limit, is there a plan after the limit, can I see the reason? |
| Model vs code | Is the model doing arithmetic or lookups that code does exactly? |
| Empty answer = success | Can I tell "nothing there" from "nothing found"? |
| Mixed units | Can a program read this field without knowing the metric by heart? |
| Eval | What is my number, on which files, and what do the wrong rows look like? |

## Words used in this guide
- **Validation / semantic validation**: checking the shape / the meaning of the output.
- **Grounding**: every fact in the output can be traced to the input.
- **Retry, max retries, fallback**: try again with the error message; the limit; the plan when the limit is reached.
- **Non-deterministic**: same input, different output.
- **Normalisation**: one standard form for many ways of writing a value.
- **Null / unknown, quiet failure, forced default**: an honest "not in the text"; failing while reporting success; a value the text does not support.
- **Eval, ground truth, precision, recall, regression**: measuring quality with numbers.

Useful reading (optional):
- Instructor (retries and validation): https://python.useinstructor.com/
- Pydantic validators: https://docs.pydantic.dev/latest/concepts/validators/
- LLM evals guide (Hamel Husain): https://hamel.dev/blog/posts/evals/
