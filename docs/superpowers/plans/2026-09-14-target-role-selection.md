# TASK-005 Target Role Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one user-selected, replaceable Target Role bound to the current Role Exploration snapshot.

**Architecture:** Add strict backend contracts and a one-to-one `target_roles` persistence resource. The service validates the requested canonical role against the current six-role snapshot under a database lock, derives display metadata from the code-owned catalog, and exposes idempotent GET/PUT routes. Add pure frontend helpers and a dedicated action on each existing exploration card without introducing downstream workflow UI.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Alembic, PostgreSQL-oriented constraints, Next.js/React/TypeScript, Node test runner.

## Global Constraints

- Only the six frozen `RoleCode` values are valid; `LOW_PRIORITY` remains selectable.
- Selection requires a confirmed Profile, saved preferences, and a current Role Exploration snapshot.
- Exactly one active Target Role exists per Profile; PUT replaces the current selection and no history is stored.
- Target Role stores the canonical role code and current exploration/version binding; display names remain catalog-derived.
- Preference invalidation deletes Role Exploration and cascades deletion of its bound Target Role.
- No LLM call, role reranking, JD ingestion, Market Profile, Gap Analysis, multiple plans, or history is added.
- PostgreSQL is the production persistence target; SQLite fixtures are only fast tests.
- No personal data, secrets, live-market claims, or real resumes are added to tests, logs, commits, or docs.
- Use TDD: each production behavior gets a failing test before implementation.
- Work only in `G:\myself\ai-career-OS-target-role-selection` on `feature/target-role-selection`.

---

### Task 1: Strict contracts, ORM model, and migration

**Files:**
- Create: `apps/api/app/target_role_schemas.py`
- Modify: `apps/api/app/models.py`
- Create: `apps/api/alembic/versions/006_target_roles.py`
- Modify: `apps/api/tests/test_alembic_revisions.py`
- Create: `apps/api/tests/test_target_role_contracts.py`

**Interfaces:**
- `TargetRoleInput` with strict `role_code: RoleCode` and `extra="forbid"`.
- `TargetRoleRead` with `id`, `profile_id`, `role_code`, `role_name`,
  `role_profile_version`, `role_exploration_id`, `selected_at`, and `updated_at`.
- SQLAlchemy `TargetRole` with unique `profile_id` and unique
  `role_exploration_id`, cascading foreign keys, and timestamp fields.

- [ ] **Step 1: Write failing contract tests.** Assert request unknown-key rejection, six-code validation including `LOW_PRIORITY` as a valid enum value, read serialization, ORM field/relationship shape, migration `006_target_roles` down-revision `005_role_explorations`, unique profile/exploration constraints, and a single latest Alembic head.

- [ ] **Step 2: Run the focused contract tests and verify the expected red failure.**

  Run from `apps/api`:

  ```powershell
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m pytest tests/test_target_role_contracts.py tests/test_alembic_revisions.py -q
  ```

  Expected: failure because the target-role module, model, migration, and new head assertions do not exist yet.

- [ ] **Step 3: Implement the minimal schemas, relationship, and migration.** Reuse `RoleCode` and `ROLE_PROFILE_VERSION`; derive no display data inside the input schema. Add `UserProfile.target_role` as a one-to-one relationship. Create `target_roles` with the two unique indexes and `ON DELETE CASCADE` FKs.

- [ ] **Step 4: Run the focused contract tests and verify green.**

  ```powershell
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m pytest tests/test_target_role_contracts.py tests/test_alembic_revisions.py -q
  ```

- [ ] **Step 5: Commit the independently testable contract slice.**

  ```powershell
  git add apps/api/app/target_role_schemas.py apps/api/app/models.py apps/api/alembic/versions/006_target_roles.py apps/api/tests/test_target_role_contracts.py apps/api/tests/test_alembic_revisions.py
  git commit -m "feat: add target role contracts"
  ```

### Task 2: Deterministic service and API routes

**Files:**
- Create: `apps/api/app/target_role_service.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_target_role_service.py`
- Create: `apps/api/tests/test_target_role_api.py`

**Interfaces:**
- `select_target_role(db: Session, profile_id: UUID, role_code: RoleCode) -> TargetRoleRead`
- `get_target_role(db: Session, profile_id: UUID) -> TargetRoleRead`
- `PUT /api/v1/profiles/{profile_id}/target-role`
- `GET /api/v1/profiles/{profile_id}/target-role`

- [ ] **Step 1: Write failing service/API tests.** Cover confirmed-profile and saved-preference gates, missing exploration, selection of each code including `LOW_PRIORITY`, replacement, same-role idempotence, invalid code and unknown request keys, role absent from current snapshot, response name/version derivation, GET empty state, persistence error mapping, unchanged Profile/Preferences/Exploration, and stale snapshot rejection.

- [ ] **Step 2: Run the focused tests and verify red.**

  ```powershell
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m pytest tests/test_target_role_service.py tests/test_target_role_api.py -q
  ```

  Expected: failure because the service and routes do not exist.

- [ ] **Step 3: Implement service loading and validation.** Load the confirmed Profile, preferences, and current Role Exploration; lock the exploration and target row; parse and validate stored exploration with the existing service; require the requested role code in the snapshot; copy catalog version and snapshot ID; update or insert the one-to-one row; commit atomically; map persistence failures to safe `503` errors.

- [ ] **Step 4: Wire strict request/response routes in `main.py`.** Import the new schema/service, attach `PUT` and `GET` routes, and leave existing Profile, Preferences, and Role Exploration routes unchanged.

- [ ] **Step 5: Run focused tests and compile the backend.**

  ```powershell
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m pytest tests/test_target_role_service.py tests/test_target_role_api.py -q
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m compileall app
  ```

- [ ] **Step 6: Commit the backend behavior slice.**

  ```powershell
  git add apps/api/app/target_role_service.py apps/api/app/main.py apps/api/tests/test_target_role_service.py apps/api/tests/test_target_role_api.py
  git commit -m "feat: add target role selection api"
  ```

### Task 3: Frontend request helpers, state, and selection action

**Files:**
- Create: `apps/web/app/target-role.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/tests/profile-flow.test.mts`

**Interfaces:**
- `TargetRoleCode` and `TargetRoleRead` matching the backend read JSON.
- `getTargetRoleRequest(profileId, apiUrl, request)` returning `TargetRoleRead | null` for the expected `404` empty state.
- `selectTargetRoleRequest(profileId, roleCode, apiUrl, request)` using exact PUT JSON.
- `targetRoleViewData(snapshot)` retaining safe selected code/name/version fields.

- [ ] **Step 1: Write failing Node tests.** Cover exact GET/PUT endpoints and payload, not-selected `404` to `null`, other errors, all six selectable codes, selected-state mapping, safe error propagation, and preference-change reset behavior through pure helpers.

- [ ] **Step 2: Run the focused frontend test and verify red.**

  ```powershell
  npm.cmd test -- --test-name-pattern="target role"
  ```

  Expected: failure because the new helpers and assertions do not exist.

- [ ] **Step 3: Implement pure target-role helpers.** Reuse `readApiPayload`; accept only the canonical role-code union; treat only the exact not-selected detail as empty; send no role name/version/exploration ID from the client.

- [ ] **Step 4: Integrate page state with stale-request protection.** Hydrate the Target Role after a valid Role Exploration is available; clear it when preference draft changes or saved preferences invalidate exploration; add one explicit button per card; update state only when the captured exploration identity still matches; show the current-target badge and safe loading/error text.

- [ ] **Step 5: Add minimal styles and run frontend checks.**

  ```powershell
  npm.cmd test
  npm.cmd run type-check
  npm.cmd run lint
  ```

- [ ] **Step 6: Commit the frontend behavior slice.**

  ```powershell
  git add apps/web/app/target-role.ts apps/web/app/page.tsx apps/web/app/globals.css apps/web/tests/profile-flow.test.mts
  git commit -m "feat: add target role selection ui"
  ```

### Task 4: Whole-feature verification and review artifacts

**Files:**
- Modify: `docs/review/TASK-005_INTENDED_VS_IMPLEMENTED.md`

- [ ] **Step 1: Run the full backend and frontend verification suites.**

  ```powershell
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m pytest -q
  & 'G:\myself\ai-career-OS-role-exploration\apps\api\.venv\Scripts\python.exe' -m compileall apps/api/app
  npm.cmd test
  npm.cmd run type-check
  npm.cmd run lint
  git diff --check
  ```

- [ ] **Step 2: Verify migration graph and intended diff.** Confirm `006_target_roles` is the only latest head, inspect `git diff main...HEAD --stat`, and ensure no TASK-006 files or behavior are present.

- [ ] **Step 3: Write the implementation review artifact.** Record the approved scope, API/data contract, invalidation behavior, tests, and explicit non-goals without personal data.

- [ ] **Step 4: Dispatch a focused code review against the TASK-005 base SHA.** Resolve all Critical/Important findings with tests before final verification.

- [ ] **Step 5: Run final verification after review fixes and inspect clean status.** Do not claim completion until the fresh commands show exit code 0 and the worktree contains only intended TASK-005 commits/files.

