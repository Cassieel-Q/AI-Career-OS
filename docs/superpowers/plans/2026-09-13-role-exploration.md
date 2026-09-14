# Basic Role Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, evidence-grounded role exploration snapshot comparing a confirmed Profile and saved Career Preferences with six immutable built-in AI role profiles.

**Architecture:** The backend owns a versioned six-role catalog, strict provider-only and persisted Pydantic models, deterministic evidence/preference/reference checks, and a one-to-one latest snapshot. An OpenAI-compatible provider supplies only role codes, levels, grounded reasons/concerns, and references; the application derives names and persists only validated JSON. A small frontend module and page section expose readiness, create/read behavior, six cards, and the fixed exploratory disclaimer.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Alembic, existing OpenAI-compatible provider conventions, Next.js/React/TypeScript, Node test runner.

## Global Constraints

- Only the six frozen role codes are valid: `AI_PRODUCT_MANAGER`, `AI_APPLICATION_ENGINEER`, `AI_SOLUTION_CONSULTANT`, `LLM_ALGORITHM_ENGINEER`, `AI_DATA_ANALYST`, and `AI_PRODUCT_OPERATIONS`.
- Every generated result contains all six roles exactly once; no percentage, salary, hiring-probability, company-count, demand-count, or other live-market fields are added.
- `RECOMMENDED`, `POSSIBLE`, and `LOW_PRIORITY` are the only exploration levels; at most three roles may be `RECOMMENDED`.
- Evidence references are Profile child-row UUIDs and preference references are values from the Profile's two saved, ordered preferences; cross-Profile or missing references are rejected before persistence.
- A result is generated only for a `CONFIRMED` Profile with an existing Career Preferences row; exploration never mutates Profile or preferences.
- Stored JSON is strict (`extra="forbid"`) and validated before write and again on read; provider failures and invalid output map to stable safe HTTP errors without logging source values, model JSON, secrets, or personal data.
- Provider output contains no role name; the application derives display names and `role_profile_version` from the immutable catalog.
- Resume/Profile extraction and Career Preferences implementation remain frozen; no TASK-005 code, target-role selection, JD ingestion, market profile, gap analysis, history table, child reason/concern tables, pgvector, or public API redesign is introduced.
- No real resume or personal data is used in fixtures, tests, logs, commits, or documentation. Synthetic evaluation contexts remain fictional and structurally varied.
- Do not set `TEST_DATABASE_URL` to `DATABASE_URL` and do not run destructive cleanup against the application database; absent `TEST_DATABASE_URL` is a safe integration-test skip.
- Work only on `feature/role-exploration`; do not merge main, rewrite history, or force-push.

---

### Task 1: Role catalog, strict schemas, ORM, and migration

**Files:**
- Create: `apps/api/app/role_profiles.py`
- Create: `apps/api/app/role_exploration_schemas.py`
- Modify: `apps/api/app/models.py`
- Create: `apps/api/alembic/versions/005_role_explorations.py`
- Create: `apps/api/tests/test_role_exploration_contracts.py`
- Modify: `apps/api/tests/test_alembic_revisions.py`

**Interfaces:**
- Produce `ROLE_PROFILE_VERSION: str = "v1"`, `ROLE_PROFILES: tuple[RoleProfile, ...]`, and `ROLE_PROFILE_BY_CODE` keyed by the six `RoleCode` values.
- Produce strict Pydantic enums/models: `RoleCode`, `ExplorationLevel`, `CodingIntensity`, `EntryBarrier`, `RoleExplorationProviderItem`, `RoleExplorationProviderPayload`, `RoleExplorationItem`, `RoleExplorationResult`, `RoleExplorationRequest`, `RoleExplorationRead`.
- Produce SQLAlchemy `RoleExploration` with UUID `id`, unique indexed `profile_id` foreign key to `user_profiles.id` with `ON DELETE CASCADE`, `role_profile_version`, JSON `result`, and UTC `created_at`/`updated_at`; add `UserProfile.role_exploration` one-to-one relationship without changing existing public profile schemas.

- [ ] **Step 1: Write failing contract tests** for all six catalog codes/version, exact catalog completeness, `extra="forbid"`, provider payload shape, result/read serialization, UUID reference fields, recommendation-level enum, request-body rejection of unknown keys, ORM relationship, and Alembic revision `005_role_explorations` down-revision `004_career_preferences` with one-to-one uniqueness.
- [ ] **Step 2: Run the focused tests** with `cd apps/api; python -m pytest tests/test_role_exploration_contracts.py tests/test_alembic_revisions.py -q`; confirm failure because the catalog/models/migration do not exist.
- [ ] **Step 3: Implement the minimal immutable catalog and schemas.** Keep role display metadata and capability descriptions code-owned; provider items must require a role code, level, at least one bounded reason, bounded concerns, at least one evidence UUID, and optional preference refs. The persisted result must add the derived role name and catalog version while retaining only bounded, grounded fields.
- [ ] **Step 4: Add the ORM relationship and Alembic migration** using existing model/migration conventions, with no history or child tables and a unique `profile_id` constraint/index.
- [ ] **Step 5: Re-run the focused tests** and add a migration-head assertion that the new revision is the latest without changing prior revisions.
- [ ] **Step 6: Commit** with `git add apps/api/app/role_profiles.py apps/api/app/role_exploration_schemas.py apps/api/app/models.py apps/api/alembic/versions/005_role_explorations.py apps/api/tests/test_role_exploration_contracts.py apps/api/tests/test_alembic_revisions.py && git commit -m "feat: add role exploration contracts"`.

### Task 2: OpenAI-compatible provider contract and safe prompt

**Files:**
- Create: `apps/api/app/role_exploration_provider.py`
- Create: `apps/api/tests/test_role_exploration_provider.py`

**Interfaces:**
- Produce immutable context dataclasses `RoleExplorationFact`, `RoleExplorationPreference`, and `RoleExplorationContext` containing copied Profile child IDs/values, ordered saved preferences, and catalog profiles.
- Produce `RoleExplorationProvider` protocol with `explore(context: RoleExplorationContext) -> RoleExplorationProviderPayload`, `get_role_exploration_provider()`, and `set_role_exploration_provider()` for test injection.
- Produce `OpenAIRoleExplorationProvider` using backend-only `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_ROLE_EXPLORATION_MODEL` fallback `OPENAI_MODEL`/`gpt-4o-mini`, strict JSON-object response parsing, existing DeepSeek-compatible settings, and safe exception taxonomy.

- [ ] **Step 1: Write failing provider tests** for missing configuration, deterministic test injection, prompt inclusion of IDs/preferences/catalog codes without raw output logging, JSON-object extraction, malformed JSON, timeout, and the prohibition on role names/market claims/new roles in the requested contract.
- [ ] **Step 2: Run `cd apps/api; python -m pytest tests/test_role_exploration_provider.py -q`** and observe the expected missing-module failures.
- [ ] **Step 3: Implement the provider protocol and context builder.** Reuse only transport/error conventions from the existing provider; do not edit Resume provider classes. The prompt must state that source facts are copied verbatim, no facts/proficiency/credentials may be inferred, output is exactly the six role codes with bounded explanations and UUID/value references, and no probability/percentage/salary/live-market claim is allowed.
- [ ] **Step 4: Implement strict JSON parsing** into `RoleExplorationProviderPayload`, converting upstream/network/timeout/invalid-object conditions into internal typed exceptions that the service can map safely.
- [ ] **Step 5: Re-run provider tests** and verify logs contain only event names/counts/configuration-safe metadata.
- [ ] **Step 6: Commit** with `git add apps/api/app/role_exploration_provider.py apps/api/tests/test_role_exploration_provider.py && git commit -m "feat: add role exploration provider"`.

### Task 3: Deterministic validation, snapshot service, and API routes

**Files:**
- Create: `apps/api/app/role_exploration_service.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_role_exploration_service.py`
- Create: `apps/api/tests/test_role_exploration_api.py`

**Interfaces:**
- Produce `create_role_exploration(db: Session, profile_id: UUID) -> RoleExplorationRead` and `get_role_exploration(db: Session, profile_id: UUID) -> RoleExplorationRead`.
- Internal validation must accept only the exact six-code set once, enforce at most three recommendations and allowed levels, check evidence UUIDs against current Profile education/skills/experiences/certifications, check preference refs against the two saved ordered priorities, reject numeric probability/percentage/hiring/demand/market claims, derive `role_name`/version from the catalog, and persist `model_dump(mode="json")` only after validation.
- Add `POST /api/v1/role-explorations` with body `{ "profile_id": "<uuid>" }` and `GET /api/v1/profiles/{profile_id}/role-exploration`; distinguish 404 profile/not-generated, 409 unconfirmed/missing preferences, 502 invalid provider output, 503 provider-not-configured/persistence failure, and 504 timeout. GET revalidates stored JSON.

- [ ] **Step 1: Write failing service/API tests** covering confirmed-state and preference gates, exact-role/duplicate/unknown/level/recommendation checks, invalid/cross-Profile evidence, invalid preference refs, market-claim rejection, latest-snapshot upsert, GET revalidation, provider/persistence/timeout mappings, unchanged Profile/preferences, and API request extra-key rejection.
- [ ] **Step 2: Run the focused tests** with `cd apps/api; python -m pytest tests/test_role_exploration_service.py tests/test_role_exploration_api.py -q`; confirm failure before implementation.
- [ ] **Step 3: Implement service loading and safe context construction.** Query only the requested Profile and its saved confirmed preferences; copy values into provider context, never mutate source rows, and keep logs to section/status/count keys.
- [ ] **Step 4: Implement deterministic validation and one-to-one upsert.** Catch provider typed errors separately from `HTTPException`; rollback SQLAlchemy failures and return safe 503s; validate persisted snapshots again during reads.
- [ ] **Step 5: Wire the two routes in `main.py`** following existing dependency/response conventions without changing Resume/Profile/Career Preferences routes or public models.
- [ ] **Step 6: Run focused tests plus `python -m compileall apps/api/app`** and commit with `git add apps/api/app/role_exploration_service.py apps/api/app/main.py apps/api/tests/test_role_exploration_service.py apps/api/tests/test_role_exploration_api.py && git commit -m "feat: add role exploration service api"`.

### Task 4: Backend synthetic evaluation and regression coverage

**Files:**
- Create: `apps/api/tests/test_role_exploration_evaluation.py`
- Modify: `apps/api/tests/conftest.py` only if a non-destructive fixture helper is needed
- Modify: `docs/review/TASK-004_INTENDED_VS_IMPLEMENTED.md`

**Interfaces:**
- Use three fictional contexts (product/operations + low coding + fast employment; Python/development + current fit; algorithm/data + long-term growth) and a fourth different section/order context where useful.
- Inject a fake provider that returns all six valid codes and references only fixture child UUIDs/preferences; assert structural grounding, preference participation, Office/technical skills normalization input, explicit credentials preservation, unsupported-credential absence, and no probability precision.

- [ ] **Step 1: Add failing evaluation tests** using only synthetic database rows and fake provider payloads; assert each context has six roles exactly once, valid refs, no market fields, and unchanged source Profile/preferences.
- [ ] **Step 2: Run the evaluation tests** and confirm they fail until the service contract is complete.
- [ ] **Step 3: Implement only test fixtures/helpers** needed to exercise the already-defined service; never add acceptance-resume values or special cases.
- [ ] **Step 4: Run backend focused suites, migration tests, and existing grounding/provider/persistence regression tests** with no application DB URL substitution.
- [ ] **Step 5: Write `docs/review/TASK-004_INTENDED_VS_IMPLEMENTED.md`** listing the approved six-role scope, implemented routes/schema/version, evidence/preference rules, frontend boundary, tests, and explicit non-goals; include no personal data.
- [ ] **Step 6: Commit** with `git add apps/api/tests/test_role_exploration_evaluation.py apps/api/tests/conftest.py docs/review/TASK-004_INTENDED_VS_IMPLEMENTED.md && git commit -m "test: evaluate role exploration grounding"`.

### Task 5: Frontend request helpers, state gates, and six-card rendering

**Files:**
- Create: `apps/web/app/role-exploration.ts`
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/tests/profile-flow.test.mts` (or add a test file only if the package script includes it)

**Interfaces:**
- Produce TypeScript unions/types matching backend read JSON, `ROLE_EXPLORATION_LEVEL_LABELS`, `profileCanExploreRoles(profile)`, `getRoleExplorationRequest(profileId)`, `createRoleExplorationRequest(...)`, and safe response/error helpers using the existing `readApiPayload` conventions.
- Extend the page to rehydrate a latest snapshot only when Profile is confirmed and saved preferences exist; ignore a not-generated GET, enable the existing next-step action only when ready, POST on click, render six cards with level/reasons/concerns/evidence refs/preference refs, and show the fixed no-real-JD disclaimer. A changed unsaved preference draft clears stale exploration UI; no target-role/JD controls are added.

- [ ] **Step 1: Write failing Node tests** for readiness gates, exact request body, 404/not-generated behavior, safe error messages, Chinese level labels, six-card view data, evidence/preference visibility, disclaimer, and rehydration after refresh.
- [ ] **Step 2: Run `cd apps/web; npm test -- --runInBand` (or the repository's existing test script)** and confirm the new assertions fail.
- [ ] **Step 3: Implement pure request/types/readiness helpers** with no API keys, source-text logging, or client-side role scoring.
- [ ] **Step 4: Integrate page state and rendering** using existing Profile confirmation/preferences state; preserve existing Resume/Profile/Career Preferences UI and editing locks.
- [ ] **Step 5: Add minimal responsive styles** for cards, badges, lists, evidence/reference labels, and disclaimer while keeping the page's existing visual language.
- [ ] **Step 6: Re-run frontend tests, `npm run type-check`, and `npm run lint`** and commit with `git add apps/web/app/role-exploration.ts apps/web/app/page.tsx apps/web/app/globals.css apps/web/tests/profile-flow.test.mts && git commit -m "feat: add role exploration ui"`.

### Task 6: Whole-branch verification and handoff

**Files:**
- Modify only verification/status artifacts if needed; do not modify implementation to silence a failing test without a defect diagnosis.

- [ ] **Step 1: Run backend focused and full suites** (`cd apps/api; python -m pytest -q`), frontend tests/type-check/lint, `python -m compileall apps/api/app`, migration history/offline checks, and `git diff --check`.
- [ ] **Step 2: Run frontend production build** from an NTFS check clone such as `C:\temp\ai-career-os-devcheck` if the G: filesystem causes the known Next.js issue; sync the feature branch after implementation commits and run `npm.cmd ci` and `npm.cmd run build`. Do not alter the source worktree's branch history.
- [ ] **Step 3: Dispatch the final whole-branch reviewer** with a package from `git merge-base main HEAD` through `HEAD`; resolve all Critical/Important findings with one fix agent and re-run covering tests.
- [ ] **Step 4: Inspect `git status --short --branch`, confirm only intended implementation/docs/test files are changed, and push `git push origin feature/role-exploration` without force.
- [ ] **Step 5: Report implementation files, catalog/schema/API/evidence/preferences/frontend behavior, verification evidence, commit SHA, push status, remaining blockers/scope deviations, and end with exactly `TASK-004 READY FOR REVIEW` only if every gate passes.
