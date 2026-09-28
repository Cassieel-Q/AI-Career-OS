# v0.2 proof evaluation harness

`seed_cases.json` contains fifteen synthetic curated cases for manual expected-output comparison. The cases cover JD grounding, experience selection, unsupported claims, red-team risk, company retrieval, adaptive follow-ups, interview gap types, and artifact-producing actions.

Run the offline check from `apps/api`:

```text
pytest tests/test_v02_evals.py -q
```

The harness reports grounding, unsupported-requirement, experience-selection, red-team recall, interview-retrieval, follow-up, gap-type, and proof-action metrics (plus the original six compatibility fields). It never calls a provider and never reads user data.
