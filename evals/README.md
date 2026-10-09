# Evaluation harnesses

## Privacy

- Do **not** commit real resumes, phone numbers, raw provider transcripts, or browser recordings.
- Public / synthetic fixtures live under `evals/` and `evals/benchmark/fixtures/`.
- Consented private samples and raw run blobs go in gitignored `evals/benchmark/private/` and `evals/benchmark/runs/`.
- Git-tracked reports may contain redacted aggregates only.

## Legacy v0.2 proof compare (`evals/schema.py`)

`seed_cases.json` holds fifteen **synthetic** curated cases for structured-label comparison.

```text
# from apps/api
pytest tests/test_v02_evals.py -q
```

Missing actual outputs are `NOT_RUN` and do **not** pass. Providing `actual_by_id` is required for a real comparison. Passing seed tests with `actual == expected` only proves the comparator math — not product quality.

## Benchmark package (`evals/benchmark`)

Phase-1 offline fixtures are intentionally small (2 per suite). Manifest `plan_vs_actual` records the full target sizes (30 JD / 30 match / 90 rewrite / 50 interview questions). **Do not claim those targets exist yet.**

From repo root with the worktree venv:

```powershell
python -m evals.benchmark.validate
python -m evals.benchmark.run --suite all --mode offline
python -m evals.benchmark.run --suite jd --mode live
python -m evals.benchmark.run --suite rewrite --mode baseline
python -m evals.benchmark.report --run-id <RUN_ID>
```

| Mode | Behavior |
|---|---|
| `offline` | Fixed fixtures only; never calls providers |
| `live` | Intended to call product providers; currently exits `NOT_RUN` without real key + consented corpus |
| `baseline` | Intended frozen direct-LLM prompts; currently `NOT_RUN` until pack exists |
| `report` | Reads an existing run; never calls models |

Results:

- Raw: `evals/benchmark/runs/<RUN_ID>.json` (gitignored)
- Summary: `evals/benchmark/reports/<RUN_ID>.summary.json` (may be committed if redacted)

## Result interpretation

| Claim | Allowed? |
|---|---|
| Offline harness validate/run/report works | Yes, with fixture counts |
| 15 seed cases prove model quality | **No** |
| 30 JD / 90 rewrite product metrics | Only after real corpus + ratings |
| Prior API 614/5/3 or Web 194/194 | Engineering QA, not EVAL suite scores |
