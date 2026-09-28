# Institution Recovery and Latency Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover one explicit, unambiguous school/institution from a recognized Education section without inference, and bound/observe resume parsing latency and LLM usage.

**Architecture:** Keep the existing full extraction, section-local repair, grounding, normalization, Profile persistence, and API contracts. Add a deterministic Education-section candidate scanner that returns exact absolute source spans, merge only separately grounded partial Education fields, and use a fixed per-resume LLM budget with explicit OpenAI timeout/retry configuration. Emit timing and institution diagnostics through redacted logs/warnings only.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, OpenAI Python SDK 1.59.7, pytest, Python logging.

## Global Constraints

- Do not merge `main`.
- Do not start TASK-003.
- Do not change schema, models, migrations, API response contracts, frontend, or persistence semantics.
- Restrict deterministic institution search to the detected Education section.
- Recover only an exact source substring when exactly one high-confidence candidate exists; never infer, rewrite, or silently choose between multiple candidates.
- Do not add another full LLM extraction or increase the existing Education repair allowance.
- Enforce a maximum of 5 LLM calls per resume: 1 initial extraction plus at most 4 section repairs.
- Default OpenAI timeout is 30 seconds and default automatic retries are 0; accepted retry configuration remains bounded at 0–2.
- Timing logs and institution diagnostics must not contain resume text, evidence excerpts, credentials, API keys, or connection secrets.
- No migration is required unless the existing schema is proven insufficient; this plan assumes it is sufficient.

---

### Task 1: Reproduce and specify institution failure paths

**Files:**
- Modify: `apps/api/tests/test_resume_reliability.py`
- Inspect/modify: `apps/api/app/main.py`
- Inspect: `apps/api/app/resume_sections.py`, `apps/api/app/profile_service.py`

- [x] **Step 1: Add the deterministic recovery RED tests.**

Add tests where the recognized Education section contains one explicit Chinese or English school token but the initial `ResumeExtractionResult` has no Education item. Assert the desired recovered institution, exact `source[evidence_start:evidence_end]`, and an `INSTITUTION_RECOVERED` diagnostic. Add separate tests for no school-like token, two distinct school candidates, and a school-like token outside Education; assert no invented Education item and the appropriate redacted diagnostic.

- [x] **Step 2: Add partial-field merge RED tests.**

Return an Education item whose institution is wrong or ungrounded while its degree, field, dates, or courses appear in the Education evidence. Assert deterministic institution recovery produces one Education item and keeps only the independently grounded optional fields. Assert a field found only in Work/Skills is not copied into Education.

- [x] **Step 3: Add latency/config/budget RED tests.**

Use a fake OpenAI constructor to capture `timeout` and `max_retries`, test defaults and valid environment overrides, and reject values outside the bounded range. Use a provider that returns unresolved sections and assert section repair calls stop at four after one initial call is accounted for. Capture timing logs and assert all required field names are present while resume text and a sentinel secret are absent.

- [x] **Step 4: Run the new tests before implementation.**

Run from `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_resume_reliability.py -q
```

Expected: the new deterministic recovery, config, timing, and budget assertions fail for the missing behavior; existing TASK-002.5C/2.5D tests continue to identify the preserved baseline.

### Task 2: Implement conservative section-local institution recovery

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] **Step 1: Add redacted institution diagnostic construction.**

Create a helper that returns `ValidationWarning` with category `education.institution`, a constant marker such as `INSTITUTION`, and empty `evidence_text`. Emit `INSTITUTION_NOT_EXTRACTED` when the model supplied no Education item, `INSTITUTION_NOT_GROUNDED` when supplied institutions were rejected by grounding, `INSTITUTION_RECOVERED` after a deterministic recovery, and `INSTITUTION_RECOVERY_AMBIGUOUS` when multiple distinct candidates exist.

- [x] **Step 2: Add high-confidence candidate scanning.**

Scan only `source_text[section.start:section.end]`. Recognize exact tokens ending in `大学`, `学院`, `职业技术学院`, `学校`, `研究院`, `University`, `College`, `Institute`, or `School`, with line/token boundaries and bounded context trimming for deterministic phrases such as `毕业于` or `graduated from`. Store the original substring and absolute start/end positions; deduplicate repeated identical candidates by normalized text. Return zero, one, or multiple candidates without choosing a candidate when the set is ambiguous.

- [x] **Step 3: Merge a recovered institution with safe partial fields.**

When the initial normalized Education list is empty and a recognized Education section exists, create an `Education` item from the one candidate. For every raw Education item retained by the provider, copy degree/major/date/course values only when the value appears in that item’s evidence and can be anchored inside the Education section. Build a contiguous source evidence span covering the recovered institution and accepted fields, preserving exact source text and absolute offsets. Leave unsupported fields absent and never search other sections.

- [x] **Step 4: Place deterministic recovery before Education repair.**

Run the recovery after initial grounding/normalization and before completeness-driven LLM repair. If it succeeds, the Education completeness warning disappears and no LLM call is made solely to recover the already explicit institution. Keep the existing Education-only repair as fallback for unresolved/ambiguous cases without increasing its two-attempt limit.

- [x] **Step 5: Run the institution focused tests GREEN.**

Run the targeted test names from Task 1 and confirm exact spans, ambiguity behavior, section isolation, partial-field preservation, and all existing evidence-grounding tests pass.

### Task 3: Add explicit provider bounds, repair budget, and redacted timing

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_resume_reliability.py`
- Modify: `.env.example`

- [x] **Step 1: Parse bounded OpenAI settings.**

Add `get_openai_timeout_seconds()` with default `30.0` and a hard upper bound of `120.0` seconds, and `get_openai_max_retries()` with default `0` and allowed range `0..2`. Pass both values to `OpenAI(timeout=..., max_retries=...)`; invalid values fail with a clear configuration error. Add `OPENAI_TIMEOUT_SECONDS=30` and `OPENAI_MAX_RETRIES=0` to `.env.example`.

- [x] **Step 2: Enforce the per-resume LLM budget.**

Define `MAX_LLM_CALLS_PER_RESUME = 5` and account for the one initial full extraction plus section repairs. Preserve priority order `EDUCATION`, `CAMPUS`/`EXPERIENCE`, then other sections; stop new repair calls once four repair calls have been used and emit a redacted budget diagnostic/completeness warning for remaining sections. Keep Education at most two section-only calls.

- [x] **Step 3: Instrument timing at upload and repair boundaries.**

Measure `pdf_extract_ms`, `initial_llm_ms`, `education_repair_1_ms`, `education_repair_2_ms`, `other_section_repair_ms`, `grounding_normalization_ms`, `db_persist_ms`, `total_resume_ms`, and `total_llm_calls`. Log only fixed field names, numeric timings, counts, and safe diagnostic codes. Replace warning logging that serializes `ValidationWarning` raw/evidence fields with code/category/index/reason/source metadata only.

- [x] **Step 4: Run timing/config/budget tests GREEN.**

Run the new reliability tests, inspect captured logs for absence of source text and sentinel secrets, and verify no extra model call occurs when deterministic recovery succeeds.

### Task 4: Final verification and delivery

**Files:**
- Create: `docs/review/TASK-002.5F_INTENDED_VS_IMPLEMENTED.md`
- Update: `docs/superpowers/plans/2026-09-05-institution-recovery.md`

- [x] **Step 1: Run focused and full backend tests.**

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_resume_reliability.py tests/test_resume.py tests/test_resume_normalization.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 2: Run frontend regression gates without changing frontend scope.**

```powershell
cd apps/web
npm test
npm run type-check
npm run lint
```

Restore any auto-generated `next-env.d.ts` change before staging because frontend source is out of scope. Record any local build-environment failure separately; do not change application code to bypass it.

- [x] **Step 3: Run repository checks and document exact root cause.**

Run `git diff --check`, inspect changed paths for absence of migration/schema/API/frontend changes, and document whether the live five-run model smoke was rerun. Include the observed pre-change SDK defaults and the final deterministic/ambiguity behavior in the review record.

- [x] **Step 4: Commit and push.**

```powershell
git add apps/api/app/main.py apps/api/tests/test_resume_reliability.py .env.example docs/review/TASK-002.5F_INTENDED_VS_IMPLEMENTED.md docs/superpowers/plans/2026-09-05-institution-recovery.md
git diff --cached --check
git commit -m "fix: recover explicit education institutions"
git push origin feature/resume-profile-normalization
```

Do not merge `main`, force-push, or begin TASK-003.
