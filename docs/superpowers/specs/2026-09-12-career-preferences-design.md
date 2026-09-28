# TASK-003 Career Preferences Design

**Status:** Approved for implementation

**Date:** 2026-09-12

**Branch:** `feature/career-preferences`

## Goal

After a user confirms a Profile, collect exactly two ranked career-decision
priorities and the user's weekly preparation time. Persist the preferences as
a dedicated one-to-one record, expose them through the existing Profile read,
and provide a small editable frontend section without starting Role
Exploration.

## Scope and non-goals

The supported priorities are `COMPENSATION`, `LESS_CODING`,
`FAST_EMPLOYMENT`, `CURRENT_FIT`, and `LONG_TERM_GROWTH`. Selection order is
meaningful: the first item is `priority_1` and the second is `priority_2`.
`weekly_hours` is an integer from 1 through 60 inclusive.

This slice does not add personality tests, salary/location/company/industry
preferences, free-text interviews, weighting sliders, LLM calls, Role
Exploration, or changes to Resume/Profile fact extraction.

## Backend architecture

`CareerPreference` is a SQLAlchemy model with a UUID primary key and a unique
foreign key to `user_profiles.id`. It stores the two priority values,
`weekly_hours`, and the repository-standard timezone-aware creation/update
timestamps. The relationship is optional from `UserProfile` so existing
profiles remain valid without a preference row.

Migration `004_career_preferences` creates the table after
`003_credential_details`. Database constraints enforce the foreign-key and
unique profile relationship, supported priority values, distinct priorities,
and the inclusive weekly-hours range. The revision identifier remains below
Alembic/PostgreSQL identifier limits.

Pydantic request validation happens before the service layer. The request has
`priority_order`, exactly two supported enum values with no duplicates, and a
strict integer `weekly_hours` in the allowed range. The service obtains the
profile with a row lock, returns 404 for a missing profile, returns 409 when
the profile is still `DRAFT`, and performs create-or-update on the single
preference row only for a `CONFIRMED` profile. Database failures are mapped to
the existing safe persistence error category without exposing internals.

The response schema represents the stored order as `priority_order` and
includes the preference row id, profile id, weekly hours, and timestamps.
`ProfileRead` gains an optional `preferences` object. A profile with no row
returns `preferences: null`; no existing Profile fact fields are changed.

## Frontend architecture and interaction

The existing profile page keeps its current upload/edit/confirm workflow. A
career-preferences section is rendered only when `profile.status` is
`CONFIRMED`; DRAFT profiles do not expose an active preference workflow.

The section renders five labeled buttons/cards. A click toggles a priority. A
new choice is appended until two choices are selected. The rendered ordinal is
derived from array order, so removing the first choice automatically promotes
the former second choice to number one. The weekly-hours control accepts an
integer and displays the 1–60 validation boundary. Save is disabled unless
there are exactly two distinct choices and a valid weekly-hours value.

Saving calls `PUT /api/v1/profiles/{profile_id}/preferences`, replaces the
local preference state with the response, and surfaces only the API's safe
error message. Profile refresh reads the optional `preferences` object from
`GET /api/v1/profiles/{profile_id}`. A later save updates the same persisted
record. No automatic navigation or Role Exploration request is made; a disabled
next-step placeholder is optional and will not implement TASK-004.

## Data flow

```text
CONFIRMED Profile
      |
      v
five choices + weekly hours (local state)
      |
      v
PUT /api/v1/profiles/{id}/preferences
      |
      v
locked profile lookup -> validate state -> upsert one CareerPreference row
      |
      v
stored preference response + optional Profile GET rehydration
```

Profile fact collections are not sent to or rewritten by the preference
endpoint. A failed preference write leaves the existing profile facts and the
previous preference row unchanged through the transaction boundary.

## Verification design

Backend tests cover confirmed creation, DRAFT conflict, missing profiles,
strict request validation, order preservation, weekly-hours bounds, repeated
PUT without duplicate rows, unchanged Profile facts, GET rehydration, and
request/session boundary persistence. SQLite in-memory fixtures remain for
fast tests; PostgreSQL integration continues to skip when
`TEST_DATABASE_URL` is absent and never uses `DATABASE_URL` for destructive
cleanup.

Frontend tests cover rendering only after confirmation, ordered selection,
two-choice maximum, removal promotion, disabled/enabled Save states, API
rehydration, edit-and-resave, and safe DRAFT behavior. Existing Resume/Profile
tests remain part of the full regression suite.

The completion gate includes focused and full backend tests, frontend tests,
type-check, lint, Python compile, `git diff --check`, Alembic offline SQL and
revision-chain checks, plus an NTFS production build when the known G: drive
filesystem issue affects the build.

## Scope guard

Only files needed for the dedicated preference model, migration, profile
serialization/service/API contract, focused tests, and the minimal frontend
interaction may change. Resume extraction, Profile fact semantics, public
features outside this slice, and Role Exploration remain frozen.
