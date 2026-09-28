# P0 Completion Sprint v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement TASK-007 through TASK-014 as one runnable, evidence-grounded product loop after the frozen UIX-001 workflow.

**Architecture:** Extend the existing FastAPI modular monolith with relational derived-state tables, strict injectable OpenAI-compatible providers, deterministic normalization/aggregation/ranking/workload checks, and explicit invalidation fingerprints. Extend the existing Next App Router WorkflowShell with focused downstream steps and a dashboard projection.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, pytest, Next.js App Router, React, TypeScript, Node built-in test runner, existing OpenAI-compatible client.

## Global Constraints

- Work only in `G:\myself\ai-career-OS-p0-completion-sprint` on `feature/p0-completion-sprint`.
- Start from `70a373199f6085a2ebb6ed466e0966b69ab00858`.
- Do not merge or push `main`; leave the sprint branch and worktree clean.
- Preserve the UIX-001 route architecture and frozen upstream business rules.
- Evidence must be copied from a supplied JD/profile source; no fabricated facts or frequencies.
- Code owns schema validation, source binding, normalization, aggregation, states, ranking, invalidation, override, and workload limits.
- Never use `TEST_DATABASE_URL == DATABASE_URL`; never reset, drop, or stamp a real database.
- Every production behavior change follows a failing test first and ends with a focused test run and coherent commit.

### Task 0: Sprint setup and shared derived-state foundation

**Files:**
- Create: `docs/superpowers/specs/2026-09-19-p0-completion-sprint-design.md`
- Create: `docs/superpowers/plans/2026-09-19-p0-completion-sprint.md`
- Create: `apps/api/alembic/versions/008_p0_completion_sprint.py`
- Modify: `apps/api/app/models.py`, `apps/api/tests/test_alembic_revisions.py`
- Test: `apps/api/tests/test_p0_models.py`

**Interfaces:**
- `MarketProfile`, `MarketRequirement`, `MarketRequirementEvidence`, `GapAnalysis`, `Gap`, `GapPriority`, `Roadmap`, `RoadmapWeek`, and `RoadmapTask` SQLAlchemy models.
- `derived_state_fingerprint(target_role, job_descriptions)` returns a stable SHA-256 string.
- `invalidate_target_derived_state(db, target_role_id)` marks market profile, gap analysis, and roadmap rows invalidated without touching task history.

- [x] Write failing model and migration-chain tests that require revision `008_p0_completion_sprint`, one Alembic head, unique current parent links, and supported status fields.
- [x] Run `pytest apps/api/tests/test_p0_models.py apps/api/tests/test_alembic_revisions.py -q` and observe the missing revision/model failure.
- [x] Add the eight tables with UUID primary keys, explicit foreign keys, indexes, status strings, JSON only for bounded ID lists, and a linear migration from `007_job_descriptions`.
- [x] Implement the fingerprint and invalidation helpers with transaction-safe updates.
- [x] Re-run the focused tests and `python -m compileall apps/api/app apps/api/alembic`.
- [x] The shared persistence foundation shipped with `feat(task-007): parse normalize and aggregate job descriptions` (`75e4cdf`); no separate foundation commit was created.

### Task 1: TASK-007 JD parse, normalize, aggregate

**Files:**
- Create: `apps/api/app/jd_analysis_schemas.py`, `apps/api/app/jd_analysis_provider.py`, `apps/api/app/market_profile_service.py`, `apps/api/app/market_profile_routes.py`
- Modify: `apps/api/app/main.py`, `apps/api/app/models.py`, `apps/api/app/job_description_service.py`
- Test: `apps/api/tests/test_market_profile.py`, `apps/api/tests/test_jd_analysis_provider.py`

**Interfaces:**
- `JDExtractionItem(name, category, evidence_text)` and `JDExtraction(jd_id, items)` strict Pydantic contracts.
- `JDAnalysisProvider.analyze(target_role, job_descriptions) -> list[JDExtraction]`.
- `normalize_requirement(value, category) -> str | None`.
- `aggregate_requirements(extractions, sample_count) -> list[AggregatedRequirement]`.
- `generate_market_profile(db, target_role_id, provider) -> MarketProfileRead`.

- [x] Add failing tests for fewer than three JDs, grounded evidence, alias normalization, deterministic counts/frequency, duplicate JD extraction, and target-role/sample fingerprint binding.
- [x] Run the focused tests and confirm failure before implementation.
- [x] Implement strict provider JSON parsing using `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`, and `OPENAI_MAX_RETRIES`; map timeout/connection/schema errors to safe provider exceptions.
- [x] Implement the explicit six-role alias map and deterministic aggregation; reject any evidence text that cannot be found in its source JD.
- [x] Persist one market profile and child requirement/evidence rows transactionally; reject `POST` when the current collection has fewer than three JDs.
- [x] Invalidate market/gap/priority/roadmap rows from JD create, update, and delete paths.
- [x] Add `GET` and `POST` route handlers with safe 409 not-ready and 502 retryable provider responses.
- [x] Run `pytest apps/api/tests/test_market_profile.py apps/api/tests/test_jd_analysis_provider.py apps/api/tests/test_job_descriptions.py -q`.
- [x] Commit `feat(task-007): parse normalize and aggregate job descriptions`.

### Task 2: TASK-008 evidence trace

**Files:**
- Modify: `apps/api/app/market_profile_schemas.py`, `apps/api/app/market_profile_routes.py`
- Create: `apps/web/app/market-profile.ts`
- Test: `apps/api/tests/test_evidence_trace.py`, `apps/web/tests/market-profile.test.mts`

**Interfaces:**
- `MarketProfileRead` includes each requirement with `source_jd_ids` and compact evidence rows.
- `GET /api/v1/market-requirements/{requirement_id}/evidence` returns only source URL, JD ID, and copied evidence text.
- `getMarketProfileRequest` and `getRequirementEvidenceRequest` use the existing request/error conventions.

- [x] Add failing API and TypeScript tests for focused evidence lookup, no raw-JD dump by default, source binding, and invalidated profile rejection.
- [x] Implement response schemas and a requirement evidence endpoint that verifies the requirement belongs to a valid current market profile.
- [x] Implement typed browser request helpers and safe user-facing error mapping.
- [x] Run focused backend/frontend evidence tests and commit `feat(task-008): add evidence trace` (`d873036`); the backend evidence endpoint and persistence were bundled with the preceding TASK-007 commit.

### Task 3: TASK-009 gap analysis

**Files:**
- Create: `apps/api/app/gap_schemas.py`, `apps/api/app/gap_provider.py`, `apps/api/app/gap_service.py`, `apps/api/app/gap_routes.py`
- Modify: `apps/api/app/main.py`, `apps/api/app/models.py`
- Test: `apps/api/tests/test_gap_analysis.py`, `apps/api/tests/test_gap_provider.py`

**Interfaces:**
- `GapState = MATCHED | PARTIAL | MISSING | UNCERTAIN`.
- `GapAnalysisProvider.compare(requirements, confirmed_profile) -> list[GapProposal]`.
- `create_gap_analysis(db, profile_id, provider) -> GapAnalysisRead`.

- [x] Add failing tests for confirmed-profile-only comparison, every allowed state, missing/partial evidence semantics, no opaque fit score, and upstream invalidation.
- [x] Implement strict gap provider contracts and safe fallback to `UNCERTAIN` when comparison evidence is insufficient.
- [x] Implement service-side validation, profile fingerprint binding, persisted rationale/evidence refs, and invalidation-aware reads.
- [x] Add `GET/POST /api/v1/profiles/{profile_id}/gap-analysis` and run checkpoint A tests.
- [x] Commit `feat(task-009): add evidence-grounded gap analysis`.

### Task 4: TASK-010 deterministic priorities and TASK-011 user override

**Files:**
- Create: `apps/api/app/priority_schemas.py`, `apps/api/app/priority_service.py`, `apps/api/app/priority_routes.py`
- Modify: `apps/api/app/gap_service.py`, `apps/api/app/main.py`
- Test: `apps/api/tests/test_priorities.py`, `apps/api/tests/test_priority_override.py`

**Interfaces:**
- `rank_gaps(gaps, preferences, weekly_hours) -> list[PriorityDecision]`.
- `GET/PUT /api/v1/profiles/{profile_id}/priorities`.
- `PriorityUpdate(order: list[UUID])` validates a permutation of current gap IDs and stores `user_rank` separately.

- [x] Add failing tests for stable factor-based ordering, top-three NOW cap, NEXT/NOT_NOW lanes, tie breaks, editable ordering, and persistence across regeneration.
- [x] Implement fixed lookup weights and explainable factor storage; make user order win without overwriting system rank.
- [x] Add invalidation checks when the gap analysis fingerprint changes.
- [x] Run checkpoint A backend tests, API OpenAPI import sanity, and commit `feat(task-010-011): prioritize gaps and persist user override`.

### Task 5: TASK-012 four-week roadmap and daily tasks

**Files:**
- Create: `apps/api/app/roadmap_schemas.py`, `apps/api/app/roadmap_provider.py`, `apps/api/app/roadmap_service.py`, `apps/api/app/roadmap_routes.py`
- Modify: `apps/api/app/main.py`, `apps/api/app/models.py`
- Test: `apps/api/tests/test_roadmap.py`, `apps/api/tests/test_roadmap_provider.py`

**Interfaces:**
- `RoadmapProvider.plan(target_role, priorities, weekly_hours) -> RoadmapProposal`.
- `validate_roadmap_workload(tasks, weekly_hours, weeks=4) -> None`.
- `POST /api/v1/profiles/{profile_id}/roadmap` and `GET` return four weeks with actionable tasks.

- [x] Add failing tests for weekly-hours budget, task actionability, linked gaps, measurable outcomes, and provider retry errors.
- [x] Implement strict task schema and workload validation at `weekly_hours * 60 * 4 * 1.15`.
- [x] Persist revisioned roadmap/week/task rows and bind them to the current user priority fingerprint.
- [x] Add safe loading/not-ready/provider errors and run checkpoint B backend tests.
- [x] Commit `feat(task-012): generate validated four week roadmap`.

### Task 6: TASK-013 progress and manual replan

**Files:**
- Modify: `apps/api/app/roadmap_schemas.py`, `apps/api/app/roadmap_service.py`, `apps/api/app/roadmap_routes.py`, `apps/api/app/main.py`
- Test: `apps/api/tests/test_progress_and_replan.py`

**Interfaces:**
- `PATCH /api/v1/roadmap-tasks/{task_id}` accepts `TODO`, `IN_PROGRESS`, `DONE`, or `SKIPPED`.
- `POST /api/v1/profiles/{profile_id}/roadmap/replan` creates a new revision from remaining gaps, current priority state, completed/skipped tasks, and remaining weeks.

- [x] Add failing tests for status transitions, completion percentage, progress not invalidating market evidence, replan history, and over-budget replans.
- [x] Implement task status updates, progress aggregation, and explicit replan-only revision creation.
- [x] Preserve superseded roadmap/task history and return a clear next revision.
- [x] Run checkpoint B tests and commit `feat(task-013): add progress and manual replanning`.

### Task 7: TASK-014 dashboard and downstream WorkflowShell

**Files:**
- Create: `apps/api/app/dashboard_schemas.py`, `apps/api/app/dashboard_service.py`, `apps/api/app/dashboard_routes.py`
- Create: `apps/web/app/market-profile.ts`, `apps/web/app/gap-analysis.ts`, `apps/web/app/priorities.ts`, `apps/web/app/roadmap.ts`, `apps/web/app/dashboard.ts`
- Create: `apps/web/app/market-profile-step.tsx`, `apps/web/app/gap-analysis-step.tsx`, `apps/web/app/priorities-step.tsx`, `apps/web/app/roadmap-step.tsx`, `apps/web/app/progress-step.tsx`, `apps/web/app/dashboard-step.tsx`
- Create: `apps/web/app/workflow/[profileId]/market-profile/page.tsx`, `gaps/page.tsx`, `priorities/page.tsx`, `roadmap/page.tsx`, `progress/page.tsx`, `dashboard/page.tsx`
- Modify: `apps/web/app/workflow-state.ts`, `apps/web/app/workflow-navigation.ts`, `apps/web/app/workflow-shell.tsx`, `apps/web/app/workflow-route.tsx`, `apps/web/app/workflow-page.tsx`, `apps/web/app/globals.css`
- Test: `apps/api/tests/test_dashboard.py`, `apps/web/tests/p0-workflow.test.mts`, `apps/web/tests/dashboard.test.mts`

**Interfaces:**
- `GET /api/v1/profiles/{profile_id}/dashboard` returns target role, market readiness/sample count, top requirements/evidence summary, top gaps, confirmed priorities, current week, upcoming tasks, progress, and replan readiness.
- `WorkflowStep` extends through `dashboard`; `readWorkflowSnapshot` reads current derived records and `canEnterStep` follows invalidation state.

- [x] Add failing route/guard/component tests for not-ready states, loading/error/retry, priority override, task updates, replan CTA, and dashboard composition.
- [x] Implement the dashboard projection using existing persisted records only.
- [x] Extend the shell step indicator and dynamic route folders without changing upstream routes.
- [x] Add concise cards and focused evidence panels; keep the existing design tokens and narrow viewport behavior.
- [x] Run full frontend tests and checkpoint C API tests.
- [x] Commit `feat(task-014): add p0 dashboard and downstream workflow`.

### Task 8: Full regression and sprint handoff

**Files:**
- Modify: `docs/product/CHANGELOG.md`, `docs/technical/TECH_SPEC_v0.1.md`, `docs/superpowers/plans/2026-09-19-p0-completion-sprint.md`

- [x] Run backend full pytest with integration skip explicitly reported when no independent `TEST_DATABASE_URL` is configured.
- [x] Run frontend `npm test`, `npm run type-check`, and `npm run lint` from G:. The G: production build reproduced the known Next filesystem `EISDIR/readlink` failure; the authorized temporary C: copy passed `next build` and was deleted after verification.
- [x] Run `python -m compileall`, `git diff --check`, `alembic heads`, and OpenAPI route sanity.
- [x] Verify the final branch and worktree are clean, confirm no `main` merge/push, and list every TASK commit.
- [x] Update the changelog and plan with evidence, known non-blocking debts, and the exact handoff line:

```text
P0 COMPLETION SPRINT v0.1
READY FOR PRODUCT OWNER END-TO-END MANUAL ACCEPTANCE
```

- [x] Commit `docs: record p0 completion sprint handoff`.

## Closeout evidence

- Final implementation branch: `feature/p0-completion-sprint`.
- TASK commits: `75e4cdf`, `d873036`, `2d82d3d`, `006d3c0`, `31f1485`, `1c04314`, `3bc28d8`; hardening follow-up: `a462b10`.
- Alembic head: `008_p0_completion_sprint`.
- Backend: `411 passed, 2 skipped` with provider variables cleared; the skips are the independent PostgreSQL integration gate.
- Frontend: `62 passed`; TypeScript and ESLint passed.
- Production build: G: failed only at the known filesystem `readlink` boundary; the temporary C: validation copy passed and was cleaned.
- OpenAPI route sanity, `compileall`, and `git diff --check` passed.
- Manual Product Owner browser acceptance remains the next gate. Main was not merged or pushed, and post-P0 work was not started.

P0 COMPLETION SPRINT v0.1
READY FOR PRODUCT OWNER END-TO-END MANUAL ACCEPTANCE
