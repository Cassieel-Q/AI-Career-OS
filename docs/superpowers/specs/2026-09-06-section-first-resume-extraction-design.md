# Section-First Resume Extraction Design

Date: 2026-09-06  
Branch: `feature/resume-profile-normalization`  
Scope: TASK-002.5G

## Problem and root cause

The current upload path extracts PDF text and then unconditionally calls
`ResumeProvider.extract()` with the full resume. Only after that result is
grounded, normalized, and checked for completeness does the application call
`extract_section()` for missing sections. The section detector therefore does
not protect the normal path from the provider's slow full-resume structured
request. With the current provider latency, the mandatory full call repeatedly
exceeds the configured timeout.

The existing deterministic section detector, grounding code, normalization,
hard-fact recovery, and section repair provider are reusable. The change is to
move section detection before provider extraction and make targeted extraction
the primary path.

## Goals and boundaries

- Make recognized, non-empty resume sections the input units for normal
  extraction.
- Preserve the public/final `ResumeExtractionResult` shape and the existing
  profile persistence/API/frontend contracts.
- Preserve source grounding, evidence spans, provenance, Office recovery,
  credential recovery, institution recovery, experience classification, and
  the PostgreSQL schema.
- Keep the application-level LLM operation budget at five and
  `OPENAI_MAX_RETRIES` default at zero.
- Do not add a migration, change frontend behavior, start TASK-003, merge
  `main`, or modify the database.

## Pipeline

The upload flow becomes:

```text
PDF
  -> deterministic detect_sections()
  -> deterministic hard-fact recovery
  -> bounded targeted section extraction
  -> section-local evidence grounding and rebasing
  -> normalization and merge
  -> completeness diagnostics
  -> DRAFT Profile
```

`EDUCATION`, `EXPERIENCE`, and `CAMPUS` sections are extracted independently.
Work, internship, and project headings determine the compatible experience
type; combined work/internship headings allow either compatible type. Each
provider call receives only the corresponding `ResumeSection.text`.

`SKILLS`, `LANGUAGE`, `CREDENTIALS`, and `COURSES` use the existing
deterministic recovery first. A section gets a targeted semantic call only if
the section contains information not covered by the deterministic recovery.
The application never sends unrelated sections to a targeted call.

The existing `OpenAIResumeProvider.extract()` method remains available for
compatibility. It is not called for a resume with recognized non-empty
sections. A resume with no recognized non-empty sections may use it as an
explicit compatibility fallback; this fallback is not followed by a repair
cascade and remains subject to the same bounded call budget and grounding
rules.

## Lean internal extraction contract

Targeted provider output uses an internal lean contract when needed. The model
returns semantic values only: institution/degree/field/dates/courses,
skill names, experience fields and type, and credential fields. Evidence
offsets, canonical aliases, and provenance are application-owned.

The application anchors every returned primary value and optional value to the
exact targeted section using existing normalized source-span helpers. It then
constructs the final `ResumeExtractionResult` with verbatim evidence excerpts,
absolute source offsets, and deterministic canonical values. A value that
cannot be anchored is rejected with a redacted warning and is never persisted.

## Failure isolation

PDF extraction, provider configuration, and a final result with no grounded
facts remain fatal failures. A timeout, connection error, upstream status
error, structured-output validation error, or unexpected processing error in a
single non-critical section becomes a structured section warning using the
existing safe provider failure taxonomy. Other sections continue processing.

Deterministic facts recovered from successful sections remain eligible for a
partial grounded Draft. A failed section is not retried or sent through the
old repair cascade. If no grounded fact remains after all deterministic and
targeted work, the existing safe no-grounded-facts failure is returned.

No raw resume text, evidence, provider body, secret, or exception message is
included in logs or API diagnostics.

## Timing and call accounting

Timing diagnostics expose section-oriented fields:

`pdf_extract_ms`, `education_llm_ms`, `experience_llm_ms`, `campus_llm_ms`,
`other_llm_ms`, `grounding_normalization_ms`, `db_persist_ms`,
`total_resume_ms`, and `total_llm_calls`.

`total_llm_calls` counts logical targeted operations (and the explicit
no-section compatibility fallback, if used). It never exceeds the existing
five-operation application budget. Transport retry configuration remains
separate and bounded.

## Verification plan

Add regression coverage for:

1. A sectioned resume never requires `provider.extract()`.
2. Education, work, campus, and project facts are extracted only from their
   own sections; CAMPUS does not satisfy WORK and PROJECT stays independent.
3. Office, credential/score, language, and explicit institution recovery remain
   deterministic, grounded, and source-span exact.
4. Unsupported provider values do not survive grounding or persistence.
5. A failed non-critical section is isolated, classified safely, and does not
   trigger a repeated repair cascade.
6. The total targeted call count is bounded.
7. Existing profile persistence, API contract, migration, and legacy loading
   tests remain green.

Run focused backend tests, full backend pytest, frontend tests, frontend
type-check, lint, build, `git diff --check`, and `git status`. No database
operation is part of this change.
