# TASK-002.5 Final Acceptance Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make resume section routing accept conservative numbered/decorated/bilingual headings and make each provider section call validate only the payload shape for the requested section.

**Architecture:** Keep public profile, extraction, database, and frontend contracts unchanged. Normalize only heading surfaces in `resume_sections.py`, preserving original offsets and heading text. Add strict provider-only payload envelopes in `main.py`, convert them deterministically into the existing `LeanResumeExtractionResult` pipeline, and log only detected/planned section keys and counts.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, PyMuPDF, SQLAlchemy/Alembic, existing Next.js frontend.

## Global Constraints

- Do not merge `main`, force-push, start TASK-003, or weaken source grounding.
- Do not modify DB schema/migrations, public API models, or frontend features.
- `extra="forbid"` remains enabled for all provider payloads.
- Do not log resume text, headings, names, institutions, companies, dates, evidence, model JSON, secrets, or field values.
- Do not special-case `XX`, personal names, filenames, or fixed section positions.
- Real resume PDFs are used only for final live smoke and are never committed or copied into the repository.

### Task 1: Red tests for heading normalization and safe routing logs

**Files:**
- Modify: `apps/api/tests/test_resume_reliability.py`
- Test target: `apps/api/app/resume_sections.py`, `apps/api/app/main.py`

- [ ] Add parametrized tests for numbered Chinese, Arabic, bilingual, decorated, and English experience/campus/skills headings; assert ordinary numbered body sentences are not sections.
- [ ] Add planner-priority and completeness tests using numbered headings.
- [ ] Add a caplog test asserting `resume_sections` and `resume_plan` messages contain only keys/counts.
- [ ] Run the new tests and confirm they fail because current routing/logging does not support the requested behavior.

### Task 2: Red tests for strict section payload envelopes

**Files:**
- Modify: `apps/api/tests/test_resume.py`
- Modify: `apps/api/tests/test_resume_reliability.py`

- [ ] Add strict validation tests for `EducationSectionPayload`, `ExperienceSectionPayload`, `CampusSectionPayload`, `SkillsSectionPayload`, `CredentialSectionPayload`, and `LanguageSectionPayload`.
- [ ] Add a provider test proving a credential response with malformed irrelevant `skills` cannot affect `CREDENTIALS`, while malformed credential items still fail.
- [ ] Add conversion tests proving campus payloads become `ExperienceType.CAMPUS`.
- [ ] Update contract assertions to require `items` envelopes and ensure no generic unused arrays are requested.
- [ ] Run the new tests and confirm they fail against the current generic envelope implementation.

### Task 3: Implement conservative heading normalization

**Files:**
- Modify: `apps/api/app/resume_sections.py`

- [ ] Strip only conservative leading ordinals (`1.`, `02 `, `二、`, etc.) before alias matching.
- [ ] Match exact aliases, colon inline headings, and same-key bilingual/decorated suffixes using deterministic alias equality.
- [ ] Preserve the original stripped source line as `ResumeSection.heading` and existing absolute `start`/`end` offsets.
- [ ] Keep ordinary body sentences and arbitrary suffixes out of heading detection.
- [ ] Run the heading/routing tests and confirm green.

### Task 4: Implement section-specific provider payloads and routing logs

**Files:**
- Modify: `apps/api/app/main.py`

- [ ] Define strict internal payload models with `extra="forbid"` and exact fields:
  `items` for education/experience/campus/skills/credentials, and `skills` plus `certifications` for language.
- [ ] Update section JSON contracts/prompts to those envelopes and validate against only the requested payload model.
- [ ] Convert validated payloads into `LeanResumeExtractionResult` deterministically without changing public models or grounding.
- [ ] Add safe `resume_sections detected=<keys> detected_count=<n>` and `resume_plan planned=<keys> planned_count=<n>` logs before provider calls.
- [ ] Run focused provider/routing tests and all existing grounding/error taxonomy tests.

### Task 5: Full verification and acceptance

**Files:**
- No additional implementation files unless a test exposes a TASK-002.5 regression.

- [ ] Run backend focused/full pytest, frontend tests/type-check/lint, `compileall`, `git diff --check`, and `git status`.
- [ ] Use `G:\myself\个人简历.pdf` for at least three synthetic live runs and report category/count summaries only.
- [ ] Use `G:\myself\潘佳琪-简历.pdf` exactly once for redacted category-level live smoke.
- [ ] Run synthetic persistence smoke through DRAFT, GET, harmless edit/save, GET, confirm, GET, and locked-state checks.
- [ ] Commit implementation and tests as `fix: stabilize resume section routing`, push `feature/resume-profile-normalization`, and verify local/remote SHAs.
