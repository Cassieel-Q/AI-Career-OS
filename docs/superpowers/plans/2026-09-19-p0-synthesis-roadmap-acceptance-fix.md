# P0 v0.1 Synthesis + Roadmap Acceptance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing atomic P0 derived-state chain into a grounded capability-level decision flow and remove the reproducible Roadmap 502 blocker without changing `main`.

**Architecture:** Keep the 008 schema and atomic `MarketRequirement`/evidence rows. Add a pure deterministic capability projection in the backend response, make Gap/Priority/Roadmap consume that projection, and bind browser generation to the current step's deliberate Next action. Add safe provider diagnostics and a guarded client generation flow.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest, Next.js App Router, React, TypeScript, Node test runner.

## Global Constraints

- Work only on `feature/p0-completion-sprint`; do not merge or push `main`.
- Do not read or print personal JD/Profile content or secrets.
- Do not rewrite migration `008`; add no migration unless tests prove the response projection cannot represent the required behavior.
- Code owns counts, frequencies, source IDs, evidence binding, validation, invalidation, ranking, and workload.
- LLM output may name/summarize only grounded capability clusters; it cannot invent evidence or counts.
- Every product behavior change begins with a failing test.

### Task 1: Deterministic capability projection

**Files:** `apps/api/app/jd_analysis_schemas.py`, `apps/api/app/market_profile_service.py`, `apps/api/tests/test_market_profile.py`.

- [x] Add failing tests that group atomic rows into bounded capabilities, preserve atomic IDs and evidence, and compute prevalence from distinct source JDs.
- [x] Run the focused tests and observe the missing capability fields/behavior.
- [x] Implement pure grouping and response serialization without changing persisted atomic rows.
- [x] Run the focused tests; the projection is included in the acceptance correction commit.

### Task 2: Capability-level Gap, Priority, and Roadmap input

**Files:** `apps/api/app/gap_schemas.py`, `apps/api/app/gap_service.py`, `apps/api/app/priority_service.py`, `apps/api/app/roadmap_service.py`, `apps/api/app/roadmap_provider.py`, focused backend tests.

- [x] Add failing tests that providers receive capability-level bounded inputs and roadmap payload is compact.
- [x] Add capability IDs and grounded atomics to API contracts; validate proposal IDs against capabilities and evidence refs against confirmed Profile facts.
- [x] Feed deterministic priorities and bounded roadmap context; retain persisted links through existing IDs where possible.
- [x] Run focused tests; capability-level Gap, Priority, and Roadmap input are included in the acceptance correction commit.

### Task 3: Roadmap 502 diagnosis and recovery

**Files:** `apps/api/app/roadmap_provider.py`, `apps/api/app/roadmap_service.py`, `apps/web/app/p0-steps.tsx`, `apps/web/app/roadmap.ts`, tests.

- [x] Add failing tests for schema/provider/workload categories and one guarded client generation attempt.
- [x] Preserve safe provider category diagnostics, normalize response content, validate exact schema fields, and never expose secrets/content.
- [x] Add explicit Retry state and duplicate-submit guard.
- [x] Run focused tests; the reproducible provider authentication path is classified explicitly.

### Task 4: Generate-on-transition workflow

**Files:** `apps/web/app/workflow-page.tsx`, `apps/web/app/workflow-navigation.ts`, `apps/web/app/p0-steps.tsx`, frontend tests.

- [x] Add failing tests for JD Next→POST→Market and Market Next→POST→Gap with no second click, plus passive GET no POST.
- [x] Register next actions on JD and Market steps; render synthesized clusters and nested atomics/evidence; keep retry/error behavior local.
- [x] Run focused frontend tests; transition single-flight coverage is included in the acceptance correction commit.

### Task 5: Full verification and handoff

- [x] Run focused backend/frontend tests, full pytest/npm tests, TypeScript, ESLint, compileall, Alembic heads, OpenAPI route sanity, and `git diff --check`.
- [x] Run G: production build first; the known Next `EISDIR` boundary was reproduced, then a temporary C copy passed and was cleaned.
- [x] Verify branch, final HEAD, clean worktree, and no main merge/push.
- [x] Update handoff records and commit the acceptance correction.

## Verification record

- Branch remains `feature/p0-completion-sprint`; `main` and `origin/main` were not modified.
- Existing Alembic revision `008_p0_completion_sprint` remains the sole code head; no migration was needed for the response-level capability projection.
- The configured roadmap provider was probed with synthetic identifiers only and returned an authentication-class failure; no Profile/JD content or secret was printed.
- Generation endpoints use PostgreSQL row locks for same-target/analysis serialization, and Roadmap validates task and week focus links against the current priority gap set.
