# Resume Extraction Reliability Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normalized Profile stable when repeated LLM extraction returns missing, merged, aliased, or individually unsupported facts.

**Architecture:** Keep raw extracted values and source evidence as the grounding boundary. Run deterministic canonicalization only after raw grounding, then detect missing recognized sections and make at most one narrow, section-only repair extraction. Quarantine unsupported items with structured warnings and fail the whole extraction only when the conservative unsupported-item threshold is exceeded.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, PostgreSQL/Alembic, pytest, existing OpenAI structured output provider.

## Global Constraints

- Do not add a second full-resume AI reviewer.
- Do not weaken evidence anchoring or use fuzzy semantic matching.
- Preserve TASK-002 Draft → Confirmed workflow, PostgreSQL migration history, trust boundary, user editable fields, and unrelated scope.
- Do not implement Career Preferences, JD, Gap Analysis, RAG, or TASK-003.
- Run focused tests, full backend pytest, frontend tests/type-check/lint if touched, and `git diff --check`.

### Task 1: Baseline and grounding contract

**Files:**
- Modify: `apps/api/app/resume_schemas.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [ ] Add failing tests for raw alias grounding, item-level quarantine, and unsupported-fact persistence exclusion.
- [ ] Run focused tests and confirm the failure is caused by missing raw/canonical or quarantine behavior.
- [ ] Add explicit raw value/evidence metadata to extracted facts without changing the public Profile API contract.
- [ ] Validate raw values against the source before normalization; keep canonical aliases traceable to the original evidence.
- [ ] Quarantine unsupported items and return structured warnings. Use a conservative threshold: if more than 25% of extracted items are unsupported, or all extracted items are unsupported, fail the extraction; otherwise retain grounded items.
- [ ] Run focused tests and full backend tests.

### Task 2: Section completeness and targeted repair

**Files:**
- Create: `apps/api/app/resume_sections.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/resume_schemas.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [ ] Add failing tests for recognized non-empty sections whose normalized output is missing, especially CAMPUS, relevant courses, and credentials.
- [ ] Implement deterministic section detection using source text and recognized headings.
- [ ] Emit stable flags such as `MISSING_SECTION_CONTENT:CAMPUS`.
- [ ] Add a narrow provider interface that receives only the missing source section and performs at most one repair call per upload.
- [ ] Ground repair facts against the section-only source, normalize them, and merge only valid facts; reject repair facts that reference text outside that section.
- [ ] Run targeted repair tests and full backend tests.

### Task 3: Atomic Office and language/credential normalization

**Files:**
- Modify: `apps/api/app/resume_normalization.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/resume_schemas.py`
- Test: `apps/api/tests/test_resume_reliability.py`
- Test: `apps/api/tests/golden_resumes/*.json`

- [ ] Add failing regression tests for explicit Office lists, generic 办公软件, English ability variants, scored CET facts, and no inferred pass/fail.
- [ ] Preserve explicit Word/Excel/PPT atomic tools and canonicalize only supported aliases.
- [ ] Keep generic 办公软件 generic when no named tool exists.
- [ ] Normalize language ability to language skills and credentials to certifications with optional score/status fields only when explicitly present.
- [ ] Keep raw evidence and supported aliases available to the validator.
- [ ] Run Golden Set tests and confirm normalized semantic facts are stable.

### Task 4: Evaluation and documentation

**Files:**
- Modify: `apps/api/app/resume_evaluation.py`
- Create/Modify: `apps/api/tests/test_repeated_resume_eval.py`
- Modify: `docs/review/TASK-002.5_INTENDED_VS_IMPLEMENTED.md`

- [ ] Add at least five deterministic repeated-output evaluations per fictional resume using semantically varied raw outputs.
- [ ] Report consistency for major, courses, Office skills, CAMPUS, language abilities, credentials, hallucinations, and grounding failures.
- [ ] Decide whether a narrow AI reviewer is justified from the measured failures; do not add one if deterministic checks are sufficient.
- [ ] Record root causes, thresholds, known remaining instability, and smoke-test status.

### Task 5: Final verification and delivery

**Files:**
- No unrelated files.

- [ ] Run focused backend tests.
- [ ] Run full backend pytest.
- [ ] Run frontend tests, type-check, lint, and build only if frontend files changed.
- [ ] Run `git diff --check` and inspect `git status`.
- [ ] Commit as `feat: harden resume extraction reliability` and push `feature/resume-profile-normalization` without merging main.
