# Implementation audit — AI Career OS evaluation readiness

Date: 2026-10-09 (PT / Guadalcanal UTC+11).  
Audit target: local worktree `G:\myself\ai-career\.worktrees\aioscareer-combine` @ `dea66f0572b2ac3b19885e2b2d3eff0ec5a5144b` on `feat/aioscareer-combine` (branched to `feature/eval-benchmark-v1` for this work).  
**GitHub remote does not currently carry this integration tip** (`origin/feat/aioscareer-combine` absent at handoff). Treat remote `main` as **not** the evaluation object.

Tags used below: **已实现** / **需要扩展** / **未运行**.

## 1. Actual product flow (missions path)

**已实现** — Browser product line is `/missions`, not legacy `/workflow` or `/proof` pages.

| Step | Web entry | API entry | Notes |
|---|---|---|---|
| Create / list missions | `apps/web/app/missions/` (`page.tsx`, `new/`) | `POST/GET /profiles/{id}/job-missions` in `mission_routes.py:53-59` | |
| JD paste → role understood | `missions/[missionId]/role` | create/reanalyze via `mission_service.create_mission` / `reanalyze_mission`; provider `MissionProvider.parse_jd` `mission_provider.py:76,1285` | Soft extraction fallbacks exist in `mission_service.py:103` |
| Identity correction | role UI | `PATCH /job-missions/{id}/identity` `mission_routes.py:78` | Downstream must use corrected identity — **需要扩展** eval coverage |
| Resume bind (master / PDF / text) | `mission-page.tsx` / profile confirm | resumes endpoints under `mission_routes.py` (upload/text/confirm) | Fact gate `RESUME_REQUIRED` |
| Experience selection | resume stage UI | `POST/GET/PUT .../experience-selection` `mission_routes.py:98-114`; provider `select_experiences` `mission_provider.py:80,1309` | Enum `KEEP_AND_HIGHLIGHT/KEEP/DEEMPHASIZE/OMIT` enforced ~`mission_provider.py:968-1022` |
| Target rewrite | resume stage | `POST .../target-resumes`, `PATCH /target-resume-bullets/{id}` `mission_routes.py:128-157` | Multi-bullet merge for review, Studio split — **需要扩展** fidelity checks |
| Resume Studio + PDF | `missions/.../resume/studio` + `apps/web/app/resume-studio/` | `resume_studio_routes.py:41-128` | Typst templates; confirm before PDF |
| Interview pack preview | interview page | `POST .../interview-pack` `mission_routes.py:171` | Pack ≠ live session |
| Mock interview session | interview UI / `proof-flow.ts` | `proof_routes.py:66-82` `/resume-claims/{id}/interview-sessions`, `/interview-sessions/{id}/turns` | Real model may stop before 5 turns (QA evidence) |
| Outcome | `missions/.../outcome` | mission read APIs | |
| Real interview records | `apps/web/app/interview-records/` | `interview_record_routes.py:28-57` | Distinct from mock sessions |

Background claim/proof/red-team paths remain available (`mission_routes.py:93,161`; `proof_routes.py`) but are **not** the linear missions UX. Eval should trigger them only when the product does.

## 2. Reusable services / providers / APIs for eval hooks

| Component | Path | Eval use | Status |
|---|---|---|---|
| `OpenAIMissionProvider` | `mission_provider.py:121+` | JD parse, selection, rewrite, red-team, interview pack | **已实现** product; **需要扩展** frozen-fixture adapters for live eval |
| `OpenAIJDAnalysisProvider` | `jd_analysis_provider.py:69` | Alternate JD analysis path | Confirm call sites before choosing as EVAL-JD entry (**需要扩展** audit of which path missions actually use) |
| `job_description_service` | `job_description_service.py` | JD CRUD / hash | Supporting, not primary missions parse |
| `resume_studio_service` / `resume_studio_render` | studio modules | PDF / revision eval | **已实现** |
| `interview_record_service` | interview record module | Real-record evaluate | **已实现** product; human usability **未运行** |
| Knowledge packs | `knowledge/interview_skills/curated/` (19 curated md) | Interview citation grounding | **已实现** files; citation wiring quality **需要扩展** (known `mission_provider` ref-key mismatch reported by other lane; not patched in this task) |
| Old harness | `evals/schema.py`, `seed_cases.json`, `tests/test_v02_evals.py` | Deterministic label compare | **已实现** after NOT_RUN fix; was silently auto-passing |

## 3. Existing offline regression (pre-benchmark)

- `evals/seed_cases.json`: 15 synthetic proof-chain cases.
- `apps/api/tests/test_v02_evals.py`: previously called `compare_cases(cases)` with **no actuals**, yet asserted all passed because `actual = actual or expected`.
- **Fix in this branch**: missing actual → `status=NOT_RUN`, `passed=False`; empty `{}` is compared, not substituted.
- API full suite prior QA: **614 passed / 5 skipped / 3 failed** (known baseline failures listed in `docs/qa/combine/2026-10-09-resume-ui-content.md`). Web 194/194. These are engineering gates, **not** EVAL-JD/MATCH/REWRITE product metrics.

## 4. Files added by TASK-EVAL-001 (phase 1)

| Area | Paths |
|---|---|
| Docs | `docs/evaluation/implementation-audit.md`, `annotation-guidelines.md`, `findings-and-backlog.md`, handoff md (untracked→tracked as needed) |
| Benchmark package | `evals/benchmark/` (`validate.py`, `run.py`, `report.py`, `metrics.py`, `paths.py`, `io_util.py`, fixtures, manifests, schemas, tests) |
| Schema fix | `evals/schema.py`, `apps/api/tests/test_v02_evals.py` |
| README | `evals/README.md` |
| Gitignore | private/runs isolation dirs |

**No Alembic migration required** for phase 1 offline harness.

## 5. Keys, isolation, privacy

| Need | Status |
|---|---|
| `OPENAI_API_KEY` / provider base URL for live | **未运行** if missing/placeholder — runner returns `NOT_RUN` |
| Consented real resumes (n=10 plan) | **未运行** — none committed; use `evals/benchmark/private/` (gitignored) |
| Human raters / dual annotation | **未运行** |
| Raw model I/O, browser recordings | Must stay under gitignored `evals/benchmark/runs/`, `.runtime/`, or `private/` |
| Reports in git | Redacted summaries only under `evals/benchmark/reports/` |

## 6. Suite readiness matrix

| Suite | Planned | Actual fixtures (phase 1) | Offline harness | Live / human |
|---|---:|---:|---|---|
| EVAL-JD | 30 | 2 synthetic | **已实现** deterministic field match | **未运行** |
| EVAL-MATCH | 30 | 2 synthetic | **已实现** label + confusion | **未运行** |
| EVAL-REWRITE | 90 | 2 synthetic (1 intentional fact-error) | **已实现** flag check; scores UNRATED | **未运行** |
| EVAL-INTERVIEW | 10 cases / 50 Q | 2 synthetic Q | **已实现** grounding flags | **未运行** |
| EVAL-E2E | browser paths | 0 new | scaffolding only | **未运行** (prior combine QA is separate evidence) |
| Direct LLM baseline | paired A/B | 0 | mode exists → `NOT_RUN` | **未运行** |

## 7. Call-site risks for future live wiring

1. **JD entry ambiguity**: missions use `MissionProvider.parse_jd`; separate `jd_analysis_provider` exists — live EVAL-JD must pin one call chain with line-level evidence.
2. **Experience why / decision alignment** (`_align_experience_why`, `mission_provider.py:605+`): Chinese copy can disagree with `OMIT` — product bug risk, eval should assert decision↔why consistency.
3. **Interview intel refs**: curated packs use `skill_id` / `source_refs`; older enrichment paths expected `id/source/ref` (reported elsewhere). Live interview citation suite must not treat demo/generic packs as target-company intel (`f0425844c` already filters retrieval defaults).
4. **Studio vs source-archive preview skew**: integration QA noted contact-info checklist on archive preview while Studio revision is delivery source of truth.
5. **Reference-answer fact pollution**: QA saw “分析 50 篇内容” → “访谈 50 位创作者”; rewrite/interview fixtures include a synthetic negative for this class.

## 8. Migration necessity

None for evaluation scaffolding. Production PostgreSQL upgrade path remains **未运行** per project status docs — out of scope for eval infra.
