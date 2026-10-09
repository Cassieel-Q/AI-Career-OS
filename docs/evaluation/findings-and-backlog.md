# Findings and backlog — EVAL phase 1

Date: 2026-10-09. Branch: `feature/eval-benchmark-v1` (from local `dea66f0`).  
Baseline is **local-only**; integration tip was not on GitHub at handoff.

## Evidence vs inference

- **Evidence**: schema bug reproduced by reading `compare_case` (`actual = actual or expected`) and `test_v02_evals.py` calling `compare_cases(cases)` with no actual map; 15/15 “passes” were self-comparisons.
- **Evidence**: prior combine QA documents Web 194/194 and API 614/5/3 with three named baseline failures.
- **Inference**: fixing the harness will surface more `NOT_RUN` until live outputs are supplied — that is desired honesty, not a product regression.

## Completed in phase 1

1. Branch + audit + annotation guidelines + findings doc.
2. `evals/schema.py` NOT_RUN semantics + regression tests.
3. `evals/benchmark` package with validate / run / report CLIs.
4. Synthetic offline fixtures (2 per suite) with explicit PLAN vs ACTUAL in manifest.
5. Live/baseline modes safe-exit as `NOT_RUN` without keys/corpus.

## NOT_RUN / NOT_EVALUABLE list (reasons)

| Item | Reason |
|---|---|
| EVAL-JD live on 30 real JDs | No authorized 30-JD corpus checked in; only 2 synthetic fixtures |
| EVAL-MATCH live × 30 | No consented resume×JD gold labels |
| EVAL-REWRITE live × 90 + human 1–5 | No raters; no consented rewrite units |
| EVAL-INTERVIEW live × 50 Q | No live session capture pack; citation wiring still pending product patch |
| EVAL-E2E browser matrix | Not executed in this task (prior QA screenshots are separate) |
| Direct LLM baseline A/B | No frozen `direct_llm_prompt.md` pack + blind raters |
| Real users (n=5) usability | Not recruited |
| API full pytest reconfirm | Deferred unless cheap; use prior 614/5/3 as QA status |
| PostgreSQL prod upgrade | Out of scope; still unverified per status docs |

## Top product improvement tasks (distinct from eval scaffolding)

1. **Reference-answer fact gate** — Block or warn when interview reference answers invent candidate actions/metrics not in confirmed Studio facts (known “50 篇内容 → 50 位创作者” class). Acceptance: fixture `syn-rewrite-002` / `syn-interview-001-q2` style cases fail closed in product, not only in eval.
2. **Unify delivery preview source** — Archive/master checklist must not contradict Studio delivery revision (contact-info false missing). Acceptance: single source-of-truth flag in UI + API.
3. **Interview intel citation keys** — Align enrichment to `skill_id` / `source_refs`; strip CURATED header lines from “要点”; never show demo/generic as target-company真实面经. Acceptance: pack generation tests with Baidu curated pack.
4. **Experience decision↔why consistency** — `OMIT` must not render “建议保留” copy (`_align_experience_why`). Acceptance: unit tests on decision/why pairs.
5. **Pin EVAL/live JD call chain** — Document and test whether missions path uses only `MissionProvider.parse_jd` vs `jd_analysis_provider`, and ensure identity edits flow into selection/rewrite.

## Eval engineering backlog

- Expand fixtures toward plan sizes **only** with authorized/synthetic-traced data.
- Add PDF text/page assertions to offline suite once Typst path is parameterized for CI.
- Store raw live outputs under gitignored `evals/benchmark/runs/` with manifest hashes.
- Wire `report` HTML/Markdown redacted digest for PR comments.
