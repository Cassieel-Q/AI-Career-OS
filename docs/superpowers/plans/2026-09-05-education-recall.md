# Education Recall Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recognized non-empty Education sections reliably produce grounded partial or complete Education records without silently disappearing.

**Architecture:** Keep the current full-resume extraction, section detection, source grounding, normalization, and persistence contracts. Add Education-specific stage diagnostics with redacted payloads, use at most two section-only Education repairs after the first pass, and sanitize unsupported optional Education fields individually so supported fields survive. Use the existing `Education` schema mapping (`institution`, `degree`, `field_of_study`, `dates`, `relevant_courses`) without a database migration.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest, existing OpenAI structured-output provider.

## Global Constraints

- Do not merge `main`.
- Do not start TASK-003.
- Fix Education recall only; do not broaden soft-skill ontology or add a full-resume reviewer.
- Education repairs are section-only and capped at two attempts after the first pass.
- Every retained Education field must be grounded in source text; do not infer school, major, degree, or dates.
- Preserve TASK-002.5C/D hard-fact recovery, section grounding, Profile serialization, and persistence behavior.
- Do not add a migration unless the schema genuinely changes.
- Diagnostics must not include resume text, raw evidence, or secrets.

---

### Task 1: Reproduce and instrument the Education failure path

**Files:**
- Test: `apps/api/tests/test_resume_reliability.py`
- Inspect/modify: `apps/api/app/main.py`
- Inspect: `apps/api/app/resume_sections.py`, `apps/api/app/profile_service.py`

- [x] **Step 1: Add a first-pass Education recall regression.**

Use a recognized non-empty Education section and a provider whose full extraction returns no Education. Assert the first pass produces an Education-missing diagnostic and invokes an Education section repair.

- [x] **Step 2: Add an Education-only second-repair regression.**

Make the first `extract_section(..., "EDUCATION")` return an empty result and the second return a grounded Education item. Assert exactly two Education repair calls occur and the final result retains the item.

- [x] **Step 3: Add stage diagnostic regressions.**

Cover empty first pass, empty repair, ungrounded repair, and unresolved Education. Assert the warning codes are present and their `raw_value`/`evidence_text` do not contain any source excerpt. Keep existing section-local unsupported-fact tests to prove grounding failures remain quarantined.

- [x] **Step 4: Trace persistence separately.**

Add or extend an API test with a repaired Education provider and assert the POST response includes the repaired Education institution/optional fields. This distinguishes extraction/merge loss from ORM-to-ProfileRead serialization loss.

### Task 2: Preserve grounded partial Education fields

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] **Step 1: Add a partial Education regression.**

Use an Education item with grounded institution and field-of-study but no degree/dates, and assert it survives normalization, merge, and serialization.

- [x] **Step 2: Add an unsupported optional-field regression.**

Return a grounded institution plus an unsupported degree or major. Assert the supported institution remains, the unsupported field becomes `None`, and the Education item is not discarded.

- [x] **Step 3: Implement field-level Education grounding.**

After the item anchor is established in `ground_resume_extraction`, retain each optional text field only when its value is explicitly present in the same source text passed to grounding. Preserve `relevant_courses` filtering. Emit a normal structured unsupported-field warning for dropped optional fields without affecting the supported Education item.

### Task 3: Add bounded Education-only retry and safe diagnostics

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/resume_sections.py` only if needed for Education section lookup
- Test: `apps/api/tests/test_resume_reliability.py`

- [x] **Step 1: Define redacted Education stage diagnostics.**

Use `ValidationWarning` with category `education`, a stable stage code, a non-sensitive raw marker such as `EDUCATION`, and an empty evidence field. Emit `EDUCATION_SECTION_NOT_DETECTED`, `EDUCATION_FIRST_PASS_EMPTY`, `EDUCATION_REPAIR_EMPTY`, `EDUCATION_REPAIR_UNGROUNDED`, `EDUCATION_DROPPED_DURING_NORMALIZATION`, and `EDUCATION_DROPPED_DURING_MERGE` only at the corresponding observed boundary.

- [x] **Step 2: Specialize the Education repair prompt.**

When `OpenAIResumeProvider.extract_section` receives `EDUCATION`, request only explicit school/institution, degree, major/field-of-study, start/end/date text, and relevant courses, mapped to the existing `Education` fields. Explicitly prohibit skills, experiences, credentials, career implications, and inference. Keep the generic section prompt for other section keys.

- [x] **Step 3: Cap Education repair attempts.**

Keep one repair for every non-Education missing section. For Education, allow the initial targeted repair plus exactly one additional Education-only retry when the section remains missing. Ground each response against the Education section text before merging; never rerun the full resume extraction.

- [x] **Step 4: Preserve partial results on exhaustion.**

If the recognized Education section remains non-empty but no grounded Education item survives after both repairs, retain other grounded Profile facts and append `EDUCATION_EXTRACTION_INCOMPLETE` with redacted diagnostic fields. Do not reinterpret the section as absent and do not raise solely because Education failed when other grounded facts remain.

- [x] **Step 5: Verify merge/dedup and serialization.**

Run the repair result through `_merge_repair`, `_dedupe_education`, `normalize_resume_extraction`, `create_draft_profile`, and `ProfileRead`; add assertions that repeated same-institution merges preserve supported optional fields and never drop the Education record.

### Task 4: Final verification and delivery

**Files:**
- Create: `docs/review/TASK-002.5E_INTENDED_VS_IMPLEMENTED.md`

- [x] **Step 1: Run focused backend tests.**

Run `..\\.venv\\Scripts\\python.exe -m pytest tests/test_resume_reliability.py tests/test_resume.py tests/test_resume_normalization.py -q` from `apps/api`.

- [x] **Step 2: Run full backend and frontend checks.**

Run `..\\.venv\\Scripts\\python.exe -m pytest -q` from `apps/api`; run `npm test`, `npm run type-check`, and `npm run lint` from `apps/web` if frontend source is unchanged as a regression gate.

- [x] **Step 3: Run repository checks.**

Run `git diff --check`, inspect `git status --short --branch`, confirm no migration/schema/frontend workflow changes, and record that live 5-run model acceptance is not claimed unless executed separately.

- [ ] **Step 4: Commit and push.**

Commit with `fix: harden education extraction recall` and push only `feature/resume-profile-normalization` without force push or merging `main`.
