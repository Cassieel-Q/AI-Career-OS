# AI Career OS Pixel UI and Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved professional Chinese copy and restrained pixel UI across the existing job, resume, interview, review, and coaching flow.

**Execution record:** The implementation and browser results are recorded in `docs/superpowers/qa/2026-10-07-pixel-ui-copy-verification.md`. The checkboxes below preserve the original task breakdown; verification evidence and the known limits take precedence over them. The code, tests and QA evidence are committed together after the final gate.

**Architecture:** Keep all API paths, data models, and persisted business decisions. Add shared design tokens, a four-stage progress model derived from existing server responses, and a small task-progress component driven by actual client request transitions. Update existing mission and proof views in place, with pure state helpers for decisions and tests.

**Tech Stack:** Next.js 15, React 18, TypeScript, existing Node test runner, FastAPI and pytest, local browser.

## Global Constraints

- Approved source: `docs/superpowers/specs/2026-10-07-ai-career-os-pixel-ui-copy-design.md` at `9f71c7a`.
- Palette: canvas `#f3efe5`, surface `#fffefa`, muted surface `#e9eef8`, primary `#3159b8`, hover `#24489a`, soft primary `#dce6ff`, ink `#172033`, muted ink `#5c6475`, border `#23304a`, disabled `#cbc7be`, danger `#b84444`, warning `#a66b18`, success `#2f6f62`.
- Long text uses readable sans-serif; pixel treatment stays on shells, short labels, buttons, status and progress nodes.
- Four stages exactly: `岗位`, `简历`, `模拟面试`, `面试记录`; no game vocabulary or new product concept.
- No database migration or API contract change. Use existing persisted mission, resume, interview session, and outcome data.
- No fake percentage. Preserve raw input and confirmed results on failures and retries. Async actions need a bounded timeout and actionable retry.
- Mobile progress uses two rows; tap targets at least 44 px; reduced motion suppresses transitions and blinking.
- Work only in `.worktrees/pixel-ui-copy`; the dirty main checkout remains untouched.

## File map

- `apps/web/app/globals.css`: design tokens, shared pixel primitives, responsive/focus/motion rules.
- `apps/web/app/mission-copy.ts`: shared user-facing stage and state wording.
- `apps/web/app/mission-progress.ts`: pure four-stage derivation from persisted data and lock reasons.
- `apps/web/app/mission-progress.tsx`: accessible progress navigation.
- `apps/web/app/task-progress.tsx`: request-stage feedback and retry presentation.
- `apps/web/app/mission-shell.tsx`, `proof-shell.tsx`: consistent global progress on mission and interview/review routes.
- `apps/web/app/mission-create.tsx`, `missions-home.tsx`, `mission-profile-confirm.tsx`, `mission-page.tsx`: mission copy, source/optimization/final resume and preview behavior.
- `apps/web/app/proof-steps.tsx`, `proof-route.tsx`, `proof-state.ts`: interview question/evaluation/review/coaching behavior and progress data.
- `apps/web/app/mission-state.ts`, `missions.ts`: display labels and existing API request timeout where needed.
- `apps/web/tests/*.test.mts`: state, copy, failure/retry and regression tests.
- `docs/superpowers/qa/2026-10-07-pixel-ui-copy-verification.md`, `docs/qa/pixel-ui/*.png`: evidence and screenshots.

---

### Task 1: Baseline, copy guard, and design primitives

**Files:** Create `apps/web/app/mission-copy.ts`, `apps/web/tests/mission-copy.test.mts`; modify `apps/web/app/globals.css`, `apps/web/app/layout.tsx`, `apps/web/app/mission-state.ts`, `apps/web/app/missions.ts`.

**Interfaces:** `MISSION_STAGE_LABELS`, `missionActionCopy`, `missionStatusCopy` become the source for repeated user labels. CSS exposes the exact palette in Global Constraints.

- [ ] **Step 1: Confirm baseline.** Run `npm run type-check` and `npm test` from `apps/web`; run `py -3 -m pytest -q` from `apps/api`. Record pass counts and pre-existing failures in the QA note.
- [ ] **Step 2: Write a failing copy test.** Assert the four stage labels, revised `targetResumeBulletStatusLabel("REJECTED") === "未采用"`, and scan active mission/proof UI files for banned user-visible phrases such as `你想`, `只需要`, `AI 会`, `面试拷问`, `准备链`. Run `node --experimental-strip-types --test tests/mission-copy.test.mts`; expect failure on current copy.
- [ ] **Step 3: Implement shared labels and replace active-view copy.** For example, `export const MISSION_STAGE_LABELS = ["岗位", "简历", "模拟面试", "面试记录"] as const;`. Keep backend enum strings in code only. Replace metadata and active mission/proof text; do not alter persisted values.
- [ ] **Step 4: Apply global palette and primitives.** Set the tokens exactly as listed above and restyle `.mission-*`, `.proof-*`, `.workflow-*` shells, cards, badges, inputs and buttons with 2 px borders, small stepped corners and offset hard shadows. Add `:focus-visible`, hover/pressed, disabled and `prefers-reduced-motion` rules. Keep textarea/content typography plain.
- [ ] **Step 5: Run the focused copy test, type check and Web suite.** Fix any existing test expectations intentionally affected by new copy, then commit `feat(ui): establish pixel tokens and professional copy`.

### Task 2: Persisted global four-stage progress

**Files:** Create `apps/web/app/mission-progress.ts`, `apps/web/app/mission-progress.tsx`, `apps/web/tests/mission-progress.test.mts`; modify `apps/web/app/mission-shell.tsx`, `apps/web/app/mission-page.tsx`, `apps/web/app/proof-shell.tsx`, `apps/web/app/proof-state.ts`.

**Interfaces:** `deriveMissionProgress({mission, targetConfirmed, hasInterviewPack, session, outcome})` returns four `{key,label,status,href,reason}` entries; status is `complete | current | available | locked`. `MissionProgress` renders those entries in a labelled nav. Resume completion comes from persisted target resume confirmation; interview and review completion come from persisted session/outcome, never localStorage.

- [ ] **Step 1: Write failing pure-state tests.** Cover fresh mission, bound resume, confirmed target resume, active interview, completed five-round session, locked reason, and refresh-equivalent re-derivation from the same server fixture. Run `node --experimental-strip-types --test tests/mission-progress.test.mts`; expect missing export failure.
- [ ] **Step 2: Implement derivation.** Map existing `mission.workflow_state`, `mission.resume_source`, latest target resume and server session to stages; completed steps stay navigable, current click is inert, future locked steps have a specific missing prerequisite.
- [ ] **Step 3: Render semantic navigation.** Use `<nav aria-label="岗位进度"><ol>...` with a button or link for available/completed nodes and a disabled button plus visible reason for locked nodes. Set `aria-current="step"` only on current stage.
- [ ] **Step 4: Feed the same progress into mission and proof shells.** Read mission state from existing mission API on proof routes; when server reads fail, retain the visible page and expose retry. Do not derive completion from in-memory `busy` state.
- [ ] **Step 5: Verify focused tests, type check, and mobile no-overflow rendering; commit `feat(ui): add persisted four-stage progress`.

### Task 3: Truthful async stage feedback and recovery

**Files:** Create `apps/web/app/task-progress.tsx`, `apps/web/app/task-progress.ts`, `apps/web/tests/task-progress.test.mts`; modify `apps/web/app/mission-create.tsx`, `mission-page.tsx`, `proof-route.tsx`, `proof-steps.tsx`, `missions.ts` and `proof-flow.ts` only as needed.

**Interfaces:** `TaskKind = "jd" | "resume-parse" | "resume-optimize" | "interview-questions" | "interview-score"`; each kind has named stages. `TaskProgress({kind, activeStep, completedSteps, error, onRetry})` shows checks, active square, pending squares and explicit error. Only completed awaited operations advance stages.

- [ ] **Step 1: Write failing stage tests.** Verify known stage names, no percentage field, error mode offers retry, and request timeout converts to actionable error while preserving user text.
- [ ] **Step 2: Implement task-stage state.** Use `setTaskStage` immediately before real awaited calls and mark completion only after fulfilled responses. Reuse the existing API clients, with `AbortController` timeout if a call can otherwise hang.
- [ ] **Step 3: Wire JD, resume parse/optimization, question generation and score submission.** Keep existing input state mounted; expose `重新识别` or `重新生成` after failure. A retry reuses the exact current input and must not reset persisted resume decisions.
- [ ] **Step 4: Verify focused tests, type check and Web suite; commit `feat(ui): show real request stages and recoverable errors`.

### Task 4: Mission list, JD and resume source

**Files:** Modify `apps/web/app/missions-home.tsx`, `mission-create.tsx`, `mission-page.tsx`, `mission-profile-confirm.tsx`, `globals.css`; test `apps/web/tests/mission-flow.test.mts` and new focused source-state test.

**Interfaces:** Existing mission and profile APIs unchanged. Source mode remains `master | upload | paste` and all three draft inputs persist while the user switches modes.

- [ ] **Step 1: Add failing tests for copy, source switching and preserved paste/file selection.** Include invalid JD and API failure preserving pasted text.
- [ ] **Step 2: Render `岗位档案` list with company, role, resume/interview status and updated time; keep card navigation separate from delete.** Use the approved empty state and button names.
- [ ] **Step 3: Render `添加目标岗位` with fixed labels; keep raw JD visible through parsing and confirmation.** Show company, role, seniority, location and `保存岗位` action after parsing.
- [ ] **Step 4: Render three fully selectable source cards with visible `已选择`, PDF filename/parse state, and safe mode switching.** Keep confirmation language about real resume facts; remove `Profile`/`Master` terminology from user copy.
- [ ] **Step 5: Run focused tests and type check; commit `feat(ui): refine job and resume source screens`.

### Task 5: Resume comparison and final export

**Files:** Modify `apps/web/app/mission-page.tsx`, `mission-state.ts`, `export-resume-checks.ts`, `globals.css`; create `apps/web/app/resume-decision.ts`, `apps/web/tests/resume-decision.test.mts`.

**Interfaces:** `resolveExclusiveBulletDecision(bullets, selectedId, nextStatus)` identifies the selected bullet and sibling IDs to reject for the same `source_experience_id`. Existing `updateResumeBullet` endpoint persists each result. Fact confirmation remains a separate operation.

- [ ] **Step 1: Write failing tests for accept/edit/reject exclusivity, status labels, and factual synthetic project export guard.** Verify a failed sibling update surfaces an error and refreshes persisted state before continuing.
- [ ] **Step 2: Implement mutual exclusion and stable status labels `已接受`/`已编辑`/`未采用`.** Accepting one rewrite rejects siblings before showing completion; editing is independent from fact confirmation.
- [ ] **Step 3: Link left and right columns.** Hovering a rewrite highlights matching source text; activating a source item scrolls/focuses corresponding rewrite. On mobile pair source and rewrite in readable order.
- [ ] **Step 4: Add actual `已处理 n / m 项` progress, suggested-project warning, final original/target toggle that preserves scroll, centralized export checklist, and final actions.** Export includes only confirmed accepted real material.
- [ ] **Step 5: Verify focused tests, export tests, type check and Web suite; commit `feat(ui): finish resume comparison and export flow`.

### Task 6: Interview preview, five rounds, review and coaching

**Files:** Modify `apps/web/app/mission-page.tsx`, `proof-steps.tsx`, `proof-shell.tsx`, `proof-route.tsx`, `globals.css`; add `apps/web/tests/interview-presentation.test.mts`.

**Interfaces:** Keep existing `startInterview`, `submitInterviewAnswer`, `generateProofGuidance` calls and persisted server session. Track presentation phase locally while each accepted turn is persisted; the next question displays only after an explicit `进入下一题` action.

- [ ] **Step 1: Write failing tests for expandable question cards, question/answer equality of width, answer preservation on score failure, explicit next-question transition, five-round completion, review turn count and two coaching actions.
- [ ] **Step 2: Build expandable preview cards with topic, summary and focus; keep `开始模拟面试` visible at the bottom.** No automatic answer submission or route reset.
- [ ] **Step 3: Separate score display from next-question reveal.** While awaiting score keep the submitted answer visible; show score, strengths, gaps and reference answer; then offer `进入下一题`. On round five offer review navigation.
- [ ] **Step 4: Render `面试复盘` with overall judgment and every persisted turn.** Keep only `继续追问` and `生成项目补强指南`; guidance shows background, personal actions, decisions, result, learning and outputs using existing response fields.
- [ ] **Step 5: Run focused tests, type check and Web suite; commit `feat(ui): refine interview and review screens`.

### Task 7: Full verification, browser QA, and delivery

**Files:** Create `docs/superpowers/qa/2026-10-07-pixel-ui-copy-verification.md`, `docs/qa/pixel-ui/*.png`; update tests if a real regression is found.

- [ ] **Step 1: Run `npm run type-check`, `npm test`, `npm run build`, `py -3 -m pytest -q`, and `py -3 -m compileall -q app` in the isolated tree.** Record exact counts and environment limits.
- [ ] **Step 2: Start API and Web against isolated test data.** Use two different JD fixtures and two different resume fixtures. Complete JD confirmation, resume source, per-bullet decisions, final confirm/PDF, preview, five answers, review, follow-up questions and project guide for each path. Inspect refresh recovery and an intentionally failed API request without losing inputs.
- [ ] **Step 3: Browser-inspect desktop and mobile pages, keyboard focus, reduced-motion and overflow.** Save screenshots for list, JD, source, comparison, final, preview, question, review and coaching, including mobile views.
- [ ] **Step 4: Fix observed UI regressions, rerun affected and full gates, inspect `git diff --check` and source copy scan, then commit verified code and QA evidence.** Report changed files, screenshots, test output, limits and commit hash.

## Self-review

- Spec sections 3–4 map to Task 1; sections 5–6 to Tasks 2–3; sections 7–10 to Tasks 1 and 4–6; sections 11–13 to Tasks 1–7.
- Existing API and model boundaries remain intact. API tests verify contract compatibility; two browser fixtures verify end-to-end behavior.
- No implementation step depends on uncommitted main-checkout changes.
