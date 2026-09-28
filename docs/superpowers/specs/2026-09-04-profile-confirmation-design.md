# TASK-002 Profile Confirmation & Supplement Design

## Goal

Turn the TASK-001 read-only resume extraction result into an editable,
persisted profile workflow. Resume parsing creates a `DRAFT` profile; only an
explicit confirm action can transition it to `CONFIRMED`.

## Approved scope

- Preserve the existing PDF validation, PyMuPDF extraction, provider
  configuration, Pydantic extraction, and deterministic evidence anchoring.
- Persist profiles and their education, skills, experiences, and certifications
  with SQLAlchemy and Alembic. `DATABASE_URL` is the production PostgreSQL
  connection; no SQLite-specific production semantics are introduced.
- Use SQLite in-memory only for pure service/business-rule unit tests.
- Add `GET /api/v1/profiles/{profile_id}`, `PUT /api/v1/profiles/{profile_id}`,
  and `POST /api/v1/profiles/{profile_id}/confirm`.
- Keep `proficiency` unset until the user selects exactly `AWARE`, `BASIC`,
  `PROJECT_READY`, or `PROFICIENT`.
- Preserve provenance as `AI_EXTRACTED`, `USER_ENTERED`, or `USER_EDITED`.
- Do not add role recommendations, JD, gap analysis, RAG, pgvector,
  authentication redesign, historical versions, or complex audit logging.

## User stories and acceptance criteria

### US-002.1 Review a trustworthy draft

As a user, I can inspect education, skills, experiences, and certifications
after resume parsing, with resume evidence shown for AI-extracted facts and no
invented missing values.

### US-002.2 Correct and supplement my profile

As a user, I can edit, add, and delete every supported profile item. User-added
items are valid without resume evidence and are marked as user-provided.

### US-002.3 Self-assess skills

As a user, I can assign one proficiency value from the four allowed values.
Resume parsing never assigns one automatically.

### US-002.4 Confirm the source of truth

As a user, I can explicitly confirm a valid draft. Saving changes never confirms
the profile. A confirmed profile reads back with `status=CONFIRMED`.

## Data model

`UserProfile` owns the lifecycle state and timestamps. Child rows are
`Education`, `ProfileSkill`, `Experience`, and `Certification`, each with a
stable UUID, editable fields, optional evidence, and provenance. AI-extracted
rows retain evidence; user-entered rows may have no evidence. A PostgreSQL
Alembic migration creates the tables, enum/check constraints, foreign keys,
cascade deletes, and indexes required for profile reads.

## API and state transitions

```text
POST /api/v1/resumes
  PDF -> extracted result -> validated evidence -> persisted DRAFT profile
  -> response includes profile_id and status

GET /api/v1/profiles/{id}
  -> complete persisted profile

PUT /api/v1/profiles/{id}
  DRAFT -> updated DRAFT
  CONFIRMED -> rejected as immutable for this MVP

POST /api/v1/profiles/{id}/confirm
  valid DRAFT -> CONFIRMED
  invalid DRAFT -> 422
  CONFIRMED -> idempotent read of CONFIRMED profile
```

Required validation includes non-empty primary names, valid proficiency enum
values, valid provenance values, and a profile-level rule that confirmation
cannot proceed with an empty profile across all four supported sections.

## Frontend behavior

Keep the existing single-page resume intake. After upload, render an editable
profile with four cards, evidence displayed once as secondary text, row-level
edit/delete controls, add controls, proficiency selection on each skill, and
`Save Draft` / `Confirm Profile` actions. The status badge changes visibly from
`DRAFT` to `CONFIRMED` only after the API confirms the transition.

## Test scenarios

- Resume upload creates a persisted draft with evidence and unset proficiency.
- Profile GET returns all four sections and status.
- PUT edits existing rows, adds rows, deletes rows, and leaves status DRAFT.
- User-entered rows without evidence are accepted.
- Invalid proficiency and invalid profile data are rejected.
- Confirm changes DRAFT to CONFIRMED and the confirmed profile reads back.
- TASK-001 evidence anchoring and PDF validation tests remain green.
- SQLAlchemy/Alembic/persistence/API/state-transition tests run against
  PostgreSQL as the release verification target; SQLite is limited to pure
  helper/service tests.
- Frontend type-check, lint, and production build pass.

## Risks and explicit non-goals

- If PostgreSQL is unavailable locally, implementation and SQLite unit tests may
  pass while PostgreSQL integration remains `UNVERIFIED`.
- This task does not create authentication or multi-user authorization; profile
  ownership is represented only by the profile identifier for this MVP slice.
- No recommendation endpoint or TASK-003 behavior may be added.
