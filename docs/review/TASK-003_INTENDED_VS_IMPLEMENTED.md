# TASK-003 intended vs implemented review

Date: 2026-09-12  
Branch: `feature/career-preferences`  
Scope: final cross-layer verification of the Career Preferences vertical slice. No implementation change was needed.

## Verification evidence

| Check | Result |
|---|---|
| Backend focused tests (`apps/api`: `python -m pytest tests/test_career_preferences.py tests/test_profiles.py tests/test_profile_service.py tests/test_alembic_revisions.py -q`) | **PASS** — 44 passed, 6 warnings |
| Backend full tests (`python -m pytest tests -q`) | **PASS** — 284 passed, 2 skipped (PostgreSQL integration; no dedicated `TEST_DATABASE_URL`) |
| Python bytecode compile (`python -m compileall -q app`) | **PASS** — exit 0 |
| Alembic history | **PASS** — `003_credential_details -> 004_career_preferences (head)` |
| Alembic offline SQL | **PASS** — `career_preferences`, priority checks, distinctness, and `weekly_hours BETWEEN 1 AND 60` rendered using an offline placeholder URL |
| Frontend tests (`apps/web`: `npm.cmd test`) | **PASS** — 23 passed, 0 failed |
| Frontend type-check | **UNVERIFIED** — `tsc` is not present in the checkout's partial `node_modules` (`npm.cmd run type-check` exits 1) |
| Frontend lint/build | **UNVERIFIED** — `next` is not present in the checkout's partial `node_modules` (`npm.cmd run lint` exits 1); no G-drive filesystem error was reproduced, so no alternate build tree was created |
| `git diff --check` | **PASS** — exit 0 |
| Scope/security inspection | **PASS** — no tracked `.env`, key, PEM, or PDF files; no Resume extraction or Role Exploration/TASK-004 changes; `TEST_DATABASE_URL` was not set or substituted from `DATABASE_URL` |

## Requirement mapping

| Intended requirement | Implementation and tests | Status |
|---|---|---|
| Exactly five supported priorities | `apps/api/app/profile_schemas.py` enum and `apps/web/app/career-preferences.ts` options; schema/label tests | **PASS** |
| Ordered selection of exactly two distinct priorities | Pydantic length/duplicate validator; `toggleCareerPreference`; API/UI tests preserve order and removal promotion | **PASS** |
| Weekly preparation hours are strict integer 1–60 inclusive | `StrictInt` + bounds; frontend digits/integer/range guard; boundary/invalid tests; migration check constraint | **PASS** |
| Dedicated one-to-one persistence | `CareerPreference`, unique `profile_id`, migration `004_career_preferences`; metadata and upsert tests | **PASS** |
| Confirmed-only create/update; DRAFT returns 409 and is never auto-confirmed | `upsert_career_preferences` locks and checks `ProfileStatus.CONFIRMED`; API test | **PASS** |
| Profile GET rehydrates optional preferences and remains backwards-compatible | `ProfileRead.preferences` nullable, `_preferences_read`, `normalizeProfile`, rehydration tests | **PASS** |
| No duplicate rows; second PUT updates the same row | Locked lookup plus unique constraint; API test and PostgreSQL integration test (test skipped without dedicated URL) | **PASS** in SQLite/API; **POSTGRES UNVERIFIED** |
| Existing Profile facts are unchanged by preference writes | Dedicated endpoint only mutates `career_preferences`; regression test compares fact collections | **PASS** |
| Safe persistence failures | SQLAlchemy error boundary rolls back and emits stable HTTP 503; query/commit failure regressions | **PASS** |
| Confirmed-only UI visibility/editability | `profileCanEditCareerPreferences` gates section and handlers; helper tests; page implementation in `apps/web/app/page.tsx` | **PASS** (DOM rendering not directly tested) |
| Five Chinese labels, visible ordinals, max-two disabled behavior | Options, card rendering, `aria-pressed`, disabled guard, scoped CSS; frontend helper tests | **PASS** (DOM coverage gap noted below) |
| Weekly-hours input and Save state | Numeric input `min=1 max=60 step=1`; validity guard disables Save until valid; page handlers | **PASS** (DOM coverage gap noted below) |
| Disabled placeholder exactly `下一步：探索适合我的岗位` | Disabled button with no navigation/request handler in `page.tsx`; source inspection | **PASS** |
| Profile-boundary rehydration and safe load/save errors | GET/upload/profile-save/confirm hydration; shared `readApiPayload`; frontend tests | **PASS** |
| No Resume extraction changes, unrelated tables, Role Exploration, or TASK-004 | Branch diff limited to preference model/migration/API, profile page/helpers/styles/tests, and TASK-003 docs | **PASS** |

## Remaining gaps and limitations

- PostgreSQL persistence/migration integration is not executable in this environment because `TEST_DATABASE_URL` is absent. The tests correctly skip and do not fall back to the configured application `DATABASE_URL`; running against a dedicated isolated PostgreSQL URL remains required before production deployment.
- TypeScript type-check, Next lint, and production build remain unverified because `tsc` and `next` binaries are missing from the partial frontend dependency tree. Existing frontend unit tests and source/tsconfig inspection passed.
- Prior Task 4 review noted a non-blocking DOM-test gap: no React DOM harness currently asserts section suppression, card `disabled`/`aria-pressed` transitions, or Save-button transitions. This is test coverage debt, not a demonstrated runtime defect.

## Review decision

No Critical or Important defect was proven by this verification. No implementation fix was made; Task 5 is documentation-only. TASK-004 Role Exploration was not started.
