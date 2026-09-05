# Resume Acceptance Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose safe, actionable provider failure diagnostics and ensure recognized work, internship, project, and campus sections are checked against compatible grounded experience types.

**Architecture:** Keep the existing PostgreSQL/profile/API contract and bounded provider retry configuration. Wrap each provider or extraction-processing boundary with an internal failure record containing only stage, exception class, safe upstream status, elapsed time, and LLM call count; translate it to a fixed HTTP response at the upload boundary. Make section completeness evaluate each recognized Experience/CAMPUS section using exact `source_section` matches when present and conservative evidence-in-section/type fallback otherwise.

**Tech Stack:** FastAPI, OpenAI Python SDK, httpx, Pydantic, pytest, existing section-aware resume extraction pipeline.

## Global Constraints

- Do not merge `main`.
- Do not start TASK-003.
- Do not change schema, models, migrations, frontend, or profile workflow.
- Do not increase `OPENAI_MAX_RETRIES` or broaden the resume parser beyond the requested failure taxonomy and experience completeness behavior.
- Never log resume text, evidence, prompts, API keys, authorization headers, raw provider bodies, or raw exception strings.
- Preserve evidence grounding, deterministic Office/credential recovery, institution recovery, CAMPUS classification, and the five-operation application LLM budget.
- Do not invent work, internship, project, or campus facts.

---

### Task 1: Lock the two acceptance regressions with failing tests

**Files:**
- Modify: `apps/api/tests/test_resume_reliability.py`
- Modify: `apps/api/tests/test_resume.py`
- Inspect: `apps/api/app/main.py`
- Inspect: `apps/api/app/resume_sections.py`

- [x] **Step 1: Add section-level completeness tests.**

Cover a CAMPUS item not satisfying a WORK section, a grounded WORK item satisfying WORK alongside CAMPUS, a CAMPUS-only result for an internship section, an unrelated WORK item for a project section, and a combined internship/work heading accepting either compatible type. Assert repair providers are called only for the missing compatible section and that all returned facts remain source-grounded.

- [x] **Step 2: Add safe provider failure response/log tests.**

Use providers that raise `TimeoutError`, `ConnectionError`, an OpenAI `APIStatusError` with a synthetic 503 response/body, and `pydantic.ValidationError`. Assert timeout returns 504, connection/upstream/structured output return safe 502 details, logs include stage/type/status/elapsed/call count, and no resume/evidence/secret/provider-body text is present.

- [x] **Step 3: Run only the new tests and verify they fail for the current implementation.**

Run from `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume_reliability.py -k "experience or provider_failure" -q
.\.venv\Scripts\python.exe -m pytest tests\test_resume.py -k "provider_failure" -q
```

Expected: the section tests expose the current `result.experiences` false-positive and the provider tests expose the generic `Resume extraction provider failed` response or missing safe diagnostics.

### Task 2: Implement safe provider failure taxonomy

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] **Step 1: Add internal safe failure classification.**

Classify timeout exceptions before connection exceptions, then upstream HTTP status exceptions, structured-output/Pydantic validation errors, and finally unexpected processing errors. Extract status only from a validated integer `status_code`/response status in the 100–599 range. Store only safe metadata on the internal failure object.

- [x] **Step 2: Wrap initial extraction, repair provider calls, and grounding/normalization boundaries.**

Use exact stages `initial_extraction`, `education_repair_1`, `education_repair_2`, `experience_repair`, `campus_repair`, `other_section_repair`, and `grounding_normalization`. Count the initial call and each repair before reporting failure, keep repair limits unchanged, validate repair results through `ResumeExtractionResult`, and let the upload boundary handle the safe response.

- [x] **Step 3: Emit only redacted diagnostics and fixed HTTP details.**

Log `provider_failure`, failure type, stage, exception class, safe upstream status, elapsed milliseconds, and total LLM calls without interpolating exception text. Return 504 for timeout, 502 with provider-unavailable detail for connection/upstream failures, 502 with invalid-structured-output detail for schema failures, and a safe 500 processing detail for unexpected internal failures.

- [x] **Step 4: Run provider failure tests and the existing extraction tests.**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume.py tests\test_resume_reliability.py -k "provider or extraction" -q
```

Expected: all taxonomy tests pass and existing evidence/repair/institution tests remain green.

### Task 3: Implement type-aware experience completeness

**Files:**
- Modify: `apps/api/app/resume_sections.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] **Step 1: Add conservative heading-to-type mapping.**

Map work headings to `WORK`, internship headings to `INTERNSHIP`, project headings to `PROJECT`, and combined internship/work headings to `{WORK, INTERNSHIP}`. Keep CAMPUS independent. When `source_section` exists, require normalized exact heading equality; otherwise require a compatible `experience_type` and evidence anchored inside the section.

- [x] **Step 2: Replace the collection-level Experience check.**

Iterate recognized sections and emit `MISSING_SECTION_CONTENT:EXPERIENCE` when no grounded compatible item belongs to the section. Preserve existing Education, Skills, Courses, Credentials, Language, and CAMPUS checks. Let the existing bounded repair loop consume the warning and recompute completeness after the repair.

- [x] **Step 3: Run the section regressions and full extraction suite.**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume_reliability.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all section/type, repair, grounding, Office, credential, institution, and persistence tests pass with no schema or migration changes.

### Task 4: Final review, verification, commit, and push

**Files:**
- Inspect: `apps/api/app/main.py`
- Inspect: `apps/api/app/resume_sections.py`
- Inspect: `apps/api/tests/test_resume.py`
- Inspect: `apps/api/tests/test_resume_reliability.py`

- [x] **Step 1: Run repository verification.**

Run backend focused/full pytest, frontend tests/type-check/lint only if relevant (frontend is expected untouched), `git diff --check`, and `git status --short --branch`. Confirm no schema, model, migration, API contract, or frontend files changed.

- [x] **Step 2: Request a focused code review.**

Review the final diff against this plan, with special attention to log redaction, exception ordering, stage/call accounting, exact source-section matching, and no invented experience facts. Resolve critical/important findings before delivery.

- [ ] **Step 3: Commit and push the current feature branch.**

```powershell
git add apps/api/app/main.py apps/api/app/resume_sections.py apps/api/tests/test_resume.py apps/api/tests/test_resume_reliability.py docs/superpowers/plans/2026-09-05-resume-acceptance-hotfix.md
git commit -m "fix: harden resume acceptance failures"
git push origin feature/resume-profile-normalization
```

Do not merge `main`, force-push, or modify the database.
