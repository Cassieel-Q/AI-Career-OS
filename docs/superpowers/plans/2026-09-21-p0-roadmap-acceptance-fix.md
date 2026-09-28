# P0 Roadmap Acceptance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make DeepSeek Roadmap generation satisfy the frozen strict schema and present a Chinese, mutually-exclusive Roadmap/Priority workflow UI without changing the gap domain or database schema.

**Architecture:** Keep `chat.completions.create` with `response_format={"type":"json_object"}` and parse JSON locally through the existing strict Pydantic models. Strengthen the provider contract and retain safe validation metadata; classify timeout responses without increasing the configured 30-second timeout. Isolate user-facing labels/state mapping in small frontend helpers, then render exactly one Roadmap state at a time and keep internal enum fields out of copy.

**Tech Stack:** FastAPI, SQLAlchemy, OpenAI-compatible Python client, Pydantic v2, Next.js 15, React 18, TypeScript, Node test runner, pytest.

## Global Constraints

- Do not merge, push `main`, rewrite migration 008, or modify Gap domain semantics.
- Do not print API keys, DATABASE_URL, Profile content, JD content, or provider response content.
- Preserve strict `RoadmapProposal`/`RoadmapWeekProposal`/`RoadmapTaskProposal` validation and evidence/gap binding.
- Keep DeepSeek on JSON object mode; do not switch to provider-specific Pydantic parse helpers.
- Keep single-flight behavior and the configured timeout/retry values unless a reproduced runtime failure proves a narrow change is required.

### Task 1: Capture the provider contract regression

**Files:**
- Modify: `apps/api/tests/test_roadmap_provider.py`

**Interfaces:**
- Consumes: `OpenAIRoadmapProvider.plan` and `RoadmapProviderInvalidResponseError`.
- Produces: tests for the observed extra `week` wrapper, valid JSON object parsing, malformed JSON, schema-invalid JSON, request contract, and timeout classification.

- [x] **Step 1: Write failing tests** for a four-week response whose entries are wrapped as `{"week": {...}}`, a valid exact response, malformed JSON, schema-invalid JSON, and a timeout exception. Assert the error contains only safe `loc`/`type` metadata and never payload text.
- [x] **Step 2: Run the focused provider tests** with `apps/api/.venv/Scripts/python.exe -m pytest tests/test_roadmap_provider.py -q`; the new contract/prompt/metadata assertions must fail before implementation.

### Task 2: Fix the provider adapter contract

**Files:**
- Modify: `apps/api/app/roadmap_provider.py`
- Test: `apps/api/tests/test_roadmap_provider.py`

**Interfaces:**
- Consumes: the existing chat completions JSON object response.
- Produces: explicit four-week/no-wrapper/no-extra-key prompt and safe validation metadata on `RoadmapProviderInvalidResponseError`.

- [x] **Step 1: Add safe validation metadata** by accepting `validation_errors: list[dict[str, object]] | None`, and on `ValidationError` retain only each error’s `loc` and `type`.
- [x] **Step 2: Replace the system contract** with explicit JSON-only requirements: top-level `weeks`, exactly weeks 1–4 in order, no nested `week` wrapper, exact week/task keys, integer `week_number`/`estimated_minutes`, copied confirmed gap IDs, no invented IDs, and no markdown/commentary.
- [x] **Step 3: Run the focused provider tests** and confirm valid output parses while all malformed/schema-invalid cases fail safely.

### Task 3: Add frontend labels and Roadmap state helpers

**Files:**
- Create: `apps/web/app/priority-ui.ts`
- Create: `apps/web/app/roadmap-ui.ts`
- Modify: `apps/web/tests/p0-workflow.test.mts`
- Modify: `apps/web/tests/workflow-actions.test.mts`

**Interfaces:**
- `priority-ui.ts` exports `priorityLaneLabel`, `priorityStateLabel`, `priorityDecisionReason`, and `priorityMarketSummary`.
- `roadmap-ui.ts` exports `RoadmapUiState`, `roadmapUiState`, `roadmapErrorMessage`, and `taskStatusLabel`.

- [x] **Step 1: Add failing node tests** asserting NOW/NEXT/NOT_NOW and MISSING/PARTIAL/MATCHED/UNCERTAIN map to Chinese labels, the decision/market summaries contain no raw enum strings, and `roadmapUiState` returns exactly one of READY/GENERATING/SUCCESS/ERROR for every combination.
- [x] **Step 2: Run `npm test -- --test-name-pattern='priority|roadmap state'`** from `apps/web`; the new imports/helpers must fail before implementation.
- [x] **Step 3: Implement the helpers** using the existing `PriorityRead` and `RoadmapRead` shapes; unknown states map to `证据不足` and unknown task statuses map to `待开始`.
- [x] **Step 4: Run the focused tests** and confirm they pass.

### Task 4: Render localized Priority and mutually-exclusive Roadmap UI

**Files:**
- Modify: `apps/web/app/p0-steps.tsx`
- Modify: `apps/web/app/roadmap.ts`
- Modify: `apps/web/app/globals.css`
- Test: `apps/web/tests/p0-workflow.test.mts`, `apps/web/tests/workflow-actions.test.mts`

**Interfaces:**
- `roadmap.ts` throws a categorized `RoadmapRequestError` for timeout/invalid-response/unavailable/network failures without exposing backend debug detail.
- `p0-steps.tsx` renders one Roadmap state branch and never renders READY plus ERROR together.

- [x] **Step 1: Add failing request tests** for HTTP 502 and 504 classification and user-safe Chinese messages.
- [x] **Step 2: Run the focused frontend tests** and confirm they fail before the categorized error class exists.
- [x] **Step 3: Implement categorized errors** in `roadmap.ts`; use 504 as timeout, 502 as invalid response, 503 as unavailable, and network failures as network; preserve normal successful payload parsing.
- [x] **Step 4: Replace raw Priority card fields** with Chinese lane/state labels, a concise derived decision explanation, market prevalence summary, and fixed-space Chinese ordering controls. Do not render `system_reason`, raw `state`, raw `lane`, severity, or other debug enums.
- [x] **Step 5: Render Roadmap branches READY/GENERATING/ERROR/SUCCESS from `roadmapUiState`; localize headings and task status/replan copy, keep Retry, and keep the CTA disabled while generating.
- [x] **Step 6: Add CSS grid/min-width rules** so priority cards and their disabled controls retain a stable layout on narrow viewports.
- [x] **Step 7: Run focused frontend tests** and confirm all pass.

### Task 5: Real provider and application verification

**Files:**
- No product files beyond Tasks 1–4.

- [x] **Step 1: Run the real Roadmap request** against the configured DeepSeek runtime with a rollback-only session; record duration, HTTP status, finish reason, content presence, JSON parse, strict validation, and persistence outcome as metadata only.
- [x] **Step 2: Verify the controlled timeout path** maps `APITimeoutError` to application HTTP 504 while leaving the 30-second production setting unchanged.
- [x] **Step 3: Run backend tests, frontend tests, type-check, lint, `compileall`, and `git diff --check`.
- [x] **Step 4: Run the production build from `G:` first; if and only if the known Next.js EISDIR issue reproduces, use a temporary C: copy, then remove it.
- [x] **Step 5: Review `git diff`, confirm no migration/product architecture changes, verify branch/status, and report the final commit and `P0 v0.1 FINAL ACCEPTANCE FIX` marker.
