# Source-Surface Grounding Acceptance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve explicit section-first resume facts by grounding every returned field independently against its detected source section while keeping fail-closed provenance and the bounded extraction budget.

**Architecture:** Keep section-first extraction and the public profile contract unchanged. Replace single-line targeted evidence localization with section-scoped, field-level source anchors; build evidence spans from exact source substrings and rebase them to absolute resume offsets. Make planning priority-aware and use deterministic recovery coverage before allocating semantic calls, then add count-only targeted diagnostics.

**Tech Stack:** FastAPI, Pydantic v2, Python, pytest, existing section detection/grounding/normalization helpers.

## Global Constraints

- Keep section-first extraction; full-resume `provider.extract` remains only the no-section compatibility fallback.
- Every targeted source fact must remain source-surface/verbatim; application code owns canonicalization, evidence, offsets, and provenance.
- Primary fields must anchor inside the detected section; unsupported optional fields are dropped individually.
- Preserve deterministic Office, credential/score, language, institution, and CAMPUS recovery.
- Keep `MAX_LLM_CALLS_PER_RESUME` bounded; do not add a migration, change schema/API/frontend, or use the real application database for tests.
- Do not merge `main`, force-push, or start TASK-003.

### Task 1: Reproduce the acceptance grounding failures

**Files:**
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] Add focused tests that return lean targeted facts whose primary and optional values occur on different lines, assert the current single-line behavior fails, and cover semantic paraphrase rejection and CAMPUS completeness.

- [x] Run the new tests from `apps/api` and record the expected failures before changing production code.

### Task 2: Implement section-scoped field-level grounding

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] Update targeted prompts to require every source-fact string to be copied verbatim and prohibit semantic rewriting, while retaining lean output without evidence or offsets.

- [x] Replace single-line localization with a full detected-section candidate and add deterministic helpers that anchor primary, scalar optional, and list optional fields independently in that section.

- [x] Keep only anchored fields, emit `UNSUPPORTED_FACT` warnings for unsupported optional fields, and retain the primary fact when optional anchoring fails.

- [x] Build each accepted fact's evidence from the exact source substring spanning accepted anchors; rebase targeted offsets from the original section slice to absolute resume offsets without fabricating evidence.

- [x] Run the focused regression tests and then the existing reliability suite.

### Task 3: Make section planning priority-aware and observable

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] Use deterministic output in `build_section_extraction_plan`; prioritize EDUCATION, EXPERIENCE, and CAMPUS, then include only semantic sections not sufficiently covered by deterministic recovery.

- [x] Keep deterministic Office/Credentials/Language results from consuming unnecessary targeted calls and preserve the five-call cap plus budget warnings.

- [x] Add count-only targeted diagnostics containing section key, extracted count, grounded count, and warning count; never log resume text, field values, evidence, or secrets.

- [x] Run planning, budget, hard-fact, CAMPUS, and observability tests.

### Task 4: Full verification and handoff

**Files:**
- Modify only files required by Tasks 1–3 and the implementation plan.

- [x] Restore the unrelated generated `apps/web/next-env.d.ts` change, if still present, without changing frontend behavior.

- [x] Run focused backend tests, full backend pytest, frontend tests, frontend type-check, lint, build, and `git diff --check`; do not use the real application database for pytest. Frontend build was attempted and remains blocked by the existing Windows/Next dependency tree error.

- [x] Inspect `git diff`, commit as `fix: preserve source-grounded section facts`, push `feature/resume-profile-normalization` without force, and verify branch/status/remote SHA.
