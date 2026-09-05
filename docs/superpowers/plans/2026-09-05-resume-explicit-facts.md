# TASK-002.5C — Resume Explicit Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make item-level grounding non-fatal when reliable facts remain and deterministically recover only explicitly present Office tools and supported credentials from recognized resume source text.

**Architecture:** Keep the existing grounded extraction pipeline, but make item-level quarantine non-fatal whenever usable grounded facts remain. Add a small source-text recovery pass after initial grounding/normalization for a bounded vocabulary, anchoring every recovered item to the real source span. Suppress umbrella Office labels only when atomic Office tokens were recovered; leave soft skills untouched.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/Alembic, pytest, TypeScript/Next.js, existing structured-output provider.

## Global Constraints

- Do not merge `main`.
- Do not change TASK-002 confirmation workflow or unrelated frontend/UI.
- Do not build a complete skill ontology; soft skills remain source-grounded raw/canonical values.
- Do not infer credentials, scores, pass/fail, or Office tools absent from source.
- Do not add a migration unless schema genuinely changes; this behavior uses existing fields.
- Run focused tests, full backend pytest, frontend tests if touched, type-check, lint, and `git diff --check`.

### Task 1: Reproduce and lock the item-level 502 regression

**Files:**
- Test: `apps/api/tests/test_resume_reliability.py`
- Modify: `apps/api/app/main.py` only if the failing test identifies the upload exception boundary.

- [ ] Add a provider/API regression with multiple source-grounded skills plus one unsupported skill whose evidence is absent from the PDF source.
- [ ] Run the focused test and confirm the current behavior returns 502 from the exception path rather than a DRAFT Profile with a structured warning.
- [ ] Trace whether `ground_resume_extraction`, `_raise_if_unreliable`, `process_resume_extraction`, or `upload_resume` is converting an item warning into the whole-resume failure.

### Task 2: Implement the smallest item-level rejection fix

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [ ] Preserve `ValidationWarning(code="UNSUPPORTED_FACT", ...)` and the existing all-facts-rejected failure behavior.
- [ ] Make an unsupported item non-fatal whenever at least one accepted grounded fact remains; retain the accepted items and never pass rejected items to `create_draft_profile`.
- [ ] Keep all-failed/systemically unusable extraction as a 502 response, with the documented prior exception path covered by tests.
- [ ] Run the focused regression and the existing evidence-validation tests.

### Task 3: Add bounded deterministic explicit-fact recovery

**Files:**
- Modify: `apps/api/app/main.py` or create `apps/api/app/resume_explicit_facts.py` if the helper is clearer.
- Modify: `apps/api/app/resume_normalization.py` only for deterministic alias/umbrella handling if needed.
- Test: `apps/api/tests/test_resume_reliability.py`

- [ ] Add failing tests for source `Word、Excel、PPT` with an LLM result that returns only `办公软件`, and for explicit credential omissions.
- [ ] Implement recovery only in recognized skills/credentials source sections or explicit source lines, using the existing source-span anchoring helper.
- [ ] Recover `Word`, `Excel`, `PPT`→`PowerPoint`, `PowerPoint`, and `Microsoft PowerPoint` only when the exact supported token is present in source.
- [ ] Recover `CET-4`, `CET-6`, `大学英语四级`, `大学英语六级`, `普通话二级甲等`, `IELTS`, `TOEFL`, and `JLPT`, preserving explicitly adjacent scores and leaving status unset unless explicitly supplied.
- [ ] Keep recovered evidence text and start/end offsets anchored to the actual source span.
- [ ] Suppress `办公软件`/`办公技能` only when one or more atomic Office tools are present; do not suppress or expand a generic umbrella with no atomic source tokens.
- [ ] Quarantine any recovery candidate that cannot be anchored; do not use fuzzy matching or source-free inference.
- [ ] Run all explicit-fact tests and Golden Resume tests.

### Task 4: Final verification and delivery

**Files:**
- Update: `docs/review/TASK-002.5C_INTENDED_VS_IMPLEMENTED.md`

- [ ] Run focused backend tests and full backend pytest.
- [ ] Run frontend tests, type-check, and lint if frontend files changed.
- [ ] Run `git diff --check` and inspect branch/status.
- [ ] Document exact 502 root cause, item rejection, deterministic recovery, umbrella suppression, migration decision, and live-model smoke availability.
- [ ] Commit as `fix: stabilize explicit resume facts` and push `feature/resume-profile-normalization` without merging main.
