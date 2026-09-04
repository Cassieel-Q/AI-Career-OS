# Profile Confirmation & Supplement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the TASK-001 resume result as an editable `DRAFT` Profile and provide safe edit/save/confirm behavior through FastAPI and the existing Next.js page.

**Architecture:** Keep resume parsing and evidence anchoring in `app/main.py`, add a focused SQLAlchemy model/database layer and a profile service for validation and serialization, and expose only the three profile endpoints required by TASK-002. Use PostgreSQL as the production schema and Alembic migration target; use SQLite in-memory only for pure/unit or local API test fixtures, with a separate PostgreSQL integration command and explicit readiness status.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL/psycopg, PyMuPDF, pytest, Next.js 15, React 18, TypeScript, Tailwind CSS.

## Global Constraints

- Preserve TASK-001 PDF validation, PyMuPDF extraction, provider configuration, structured extraction, and deterministic evidence anchoring.
- Production/real persistence uses `DATABASE_URL` pointing to PostgreSQL through SQLAlchemy and Alembic.
- SQLite in-memory is permitted only for pure logic tests and local test fixtures; it must not define a separate production schema or behavior.
- Profile status is exactly `DRAFT` or `CONFIRMED`; only explicit confirm transitions a draft.
- Skill proficiency is unset or exactly `AWARE`, `BASIC`, `PROJECT_READY`, or `PROFICIENT`; AI extraction may never infer it.
- Provenance is exactly `AI_EXTRACTED`, `USER_ENTERED`, or `USER_EDITED`.
- User-entered facts may omit resume evidence; AI-extracted facts retain evidence where available.
- Do not add role recommendation, JD, gap analysis, RAG, pgvector, complex audit/versioning, or TASK-003 behavior.
- Do not merge `main`.

---

### Task 1: Add PostgreSQL-first profile persistence foundation

**Files:**
- Create: `apps/api/app/database.py`
- Create: `apps/api/app/models.py`
- Create: `apps/api/app/profile_schemas.py`
- Modify: `apps/api/requirements.txt`
- Modify: `.env.example`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/script.py.mako`
- Create: `apps/api/alembic/versions/001_create_profile_tables.py`
- Test: `apps/api/tests/test_profile_service.py`

**Interfaces:**
- `database.Base` is the declarative SQLAlchemy base.
- `database.get_db()` yields a SQLAlchemy `Session` created from `DATABASE_URL` and raises a clear configuration error when no real database URL is configured.
- `models.UserProfile` owns `id`, `status`, `created_at`, and `updated_at`; child models are `Education`, `ProfileSkill`, `Experience`, and `Certification`.
- `profile_schemas.ProfileUpdate` accepts complete replacement lists for the four sections; each item supports optional `id`, optional evidence, and the defined provenance.
- `profile_schemas.ProfileRead` returns `profile_id`, `status`, timestamps, and all four child lists.

- [ ] **Step 1: Write failing pure validation tests**

```python
def test_proficiency_is_unset_by_default():
    skill = ProfileSkillInput(name="Python")
    assert skill.proficiency is None


def test_invalid_proficiency_is_rejected():
    with pytest.raises(ValidationError):
        ProfileSkillInput(name="Python", proficiency="EXPERT")


def test_user_entered_fact_may_omit_evidence():
    assert ProfileSkillInput(name="SQL", source_type="USER_ENTERED").evidence_text is None
```

Run: `pytest apps/api/tests/test_profile_service.py -q`
Expected: FAIL because profile schemas do not yet exist.

- [ ] **Step 2: Add dependencies and PostgreSQL-first model/schema code**

Add `SQLAlchemy`, `alembic`, and `psycopg[binary]` to `apps/api/requirements.txt`. Define `DATABASE_URL` as the only runtime database configuration in `.env.example`. Use SQLAlchemy's generic `Uuid`, `DateTime(timezone=True)`, and explicit enum/check semantics so the PostgreSQL migration is authoritative while SQLite test fixtures exercise the same field meanings.

The schema layer must normalize blank optional strings to `None`, reject blank primary names, and reject evidence-less `AI_EXTRACTED`/`USER_EDITED` rows while allowing evidence-less `USER_ENTERED` rows. The default for skill proficiency is `None`.

- [ ] **Step 3: Run pure validation tests**

Run: `pytest apps/api/tests/test_profile_service.py -q`
Expected: PASS.

- [ ] **Step 4: Add Alembic environment and the first migration**

The migration creates `user_profiles`, `education`, `profile_skills`, `experiences`, and `certifications`; UUID primary keys; foreign keys with cascade delete; status/proficiency/source type constraints; timestamps; and profile/child indexes. `alembic/env.py` imports `database.Base` and `models` and reads `DATABASE_URL` from the environment. Do not use `Base.metadata.create_all()` as a production startup migration substitute.

- [ ] **Step 5: Verify migration syntax without claiming PostgreSQL integration**

Run: `alembic -c apps/api/alembic.ini check` with a configured PostgreSQL `DATABASE_URL` when available.
Expected: clean Alembic check; if PostgreSQL is unavailable, record `UNVERIFIED` and continue with unit work.

- [ ] **Step 6: Commit persistence foundation**

```bash
git add apps/api/app/database.py apps/api/app/models.py apps/api/app/profile_schemas.py apps/api/requirements.txt .env.example apps/api/alembic.ini apps/api/alembic apps/api/tests/test_profile_service.py
git commit -m "feat: add profile persistence foundation"
```

### Task 2: Implement profile service and API state transitions

**Files:**
- Create: `apps/api/app/profile_service.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_resume.py`
- Create: `apps/api/tests/test_profiles.py`
- Create: `apps/api/tests/conftest.py`

**Interfaces:**
- `profile_service.create_draft_profile(db: Session, extraction: ResumeExtractionResult) -> UserProfile`.
- `profile_service.get_profile(db: Session, profile_id: UUID) -> ProfileRead`.
- `profile_service.update_draft_profile(db: Session, profile_id: UUID, payload: ProfileUpdate) -> ProfileRead`.
- `profile_service.confirm_profile(db: Session, profile_id: UUID) -> ProfileRead`.
- `POST /api/v1/resumes` returns `ProfileRead` with `status="DRAFT"` and `profile_id` after evidence validation and persistence.
- `GET /api/v1/profiles/{profile_id}` returns `ProfileRead`, 404 for an unknown ID.
- `PUT /api/v1/profiles/{profile_id}` replaces child collections atomically for a draft, returns DRAFT, and rejects edits to CONFIRMED with 409.
- `POST /api/v1/profiles/{profile_id}/confirm` validates a non-empty profile, transitions DRAFT to CONFIRMED, and is idempotent for an already confirmed profile.

- [ ] **Step 1: Write failing API/service tests**

```python
def test_resume_upload_persists_draft_profile(client):
    response = upload_mock_resume(client)
    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"]
    assert body["status"] == "DRAFT"
    assert body["skills"][0]["proficiency"] is None


def test_put_adds_edits_and_deletes_items(client, persisted_profile):
    payload = replace_profile_payload(persisted_profile)
    response = client.put(f"/api/v1/profiles/{persisted_profile.id}", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"


def test_confirm_persists_confirmed_state(client, persisted_profile):
    response = client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    assert client.get(f"/api/v1/profiles/{persisted_profile.id}").json()["status"] == "CONFIRMED"
```

Run: `pytest apps/api/tests/test_profiles.py apps/api/tests/test_resume.py -q`
Expected: FAIL because profile service, database dependency overrides, and endpoints are not implemented.

- [ ] **Step 2: Implement service-level conversion and atomic replacement**

Convert validated extraction rows to `AI_EXTRACTED` child rows, preserving anchored evidence and leaving proficiency `None`. For PUT, retain IDs that are present, create new UUIDs for new rows, delete omitted rows, and derive provenance `USER_EDITED` for edits to AI rows and `USER_ENTERED` for new rows. Reject edits to confirmed profiles before mutation. Commit once per operation and refresh the complete profile.

- [ ] **Step 3: Wire the resume, read, update, and confirm endpoints**

Inject `get_db` into the endpoints. Keep the existing resume validation/provider exception mapping intact, and only persist after `validate_evidence_trace` succeeds. Return 409 for invalid lifecycle mutations, 404 for missing profiles, and 422 for invalid request bodies or empty confirmation candidates.

- [ ] **Step 4: Run focused API tests**

Run: `pytest apps/api/tests/test_profiles.py apps/api/tests/test_resume.py -q`
Expected: PASS for SQLite-backed test fixtures, with PostgreSQL integration still tracked separately.

- [ ] **Step 5: Commit backend profile workflow**

```bash
git add apps/api/app/main.py apps/api/app/profile_service.py apps/api/tests/conftest.py apps/api/tests/test_profiles.py apps/api/tests/test_resume.py
git commit -m "feat: add profile confirmation workflow"
```

### Task 3: Convert the resume page into an editable profile UI

**Files:**
- Modify: `apps/web/app/page.tsx`
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/app/layout.tsx`
- Modify: `apps/web/.eslintrc.json` if lint configuration requires it

**Interfaces:**
- Frontend `Profile` mirrors `ProfileRead` including IDs, status, provenance, optional evidence, and nullable proficiency.
- `upload` consumes `POST /api/v1/resumes` and stores the returned profile ID.
- `saveDraft` sends the complete editable profile to `PUT /api/v1/profiles/{profile_id}`.
- `confirmProfile` calls `POST /api/v1/profiles/{profile_id}/confirm` and displays the returned CONFIRMED state.

- [ ] **Step 1: Add a typed client-side fixture/interaction test if the existing frontend test setup supports it**

If no frontend test runner exists, keep behavior covered through strict TypeScript and build checks and do not add a new test framework to this MVP.

- [ ] **Step 2: Implement editable cards and row operations**

Use controlled inputs for education, skills, experiences, and certifications. Each row has edit fields, an add-row control, and a delete control. Skills expose a `<select>` with only `AWARE`, `BASIC`, `PROJECT_READY`, and `PROFICIENT`, plus an explicit unset option. Evidence is rendered once as secondary text; user-entered rows show “User provided” rather than fabricated evidence.

- [ ] **Step 3: Implement save/confirm actions and status handling**

Disable mutation controls while requests are in flight, surface API errors in the existing alert region, keep `DRAFT` after save, and show a clear `CONFIRMED` badge after successful confirmation. Do not expose or infer role recommendation behavior.

- [ ] **Step 4: Fix presentation issues and verify frontend**

Remove duplicated labels such as `WordWord`, `ExcelExcel`, and `PPTPPT` if present in rendered copy. Keep the existing visual language and make the profile controls usable on narrow screens.

Run:

```bash
npm --prefix apps/web run type-check
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

Expected: all commands pass.

- [ ] **Step 5: Commit frontend workflow**

```bash
git add apps/web/app/page.tsx apps/web/app/globals.css apps/web/app/layout.tsx apps/web/.eslintrc.json
git commit -m "feat: make draft profile editable"
```

### Task 4: PostgreSQL integration verification and release review

**Files:**
- Create: `apps/api/tests/test_postgres_integration.py`
- Create or modify: `docker-compose.yml` only if the repository has an existing local-infra convention and the minimal database service is justified
- Modify: `README.md`
- Create: `docs/review/TASK-002_INTENDED_VS_IMPLEMENTED.md`
- Modify: `docs/product/CHANGELOG.md`
- Modify: `docs/product/DECISIONS.md` only for stable verified decisions

**Interfaces:**
- PostgreSQL integration tests use `TEST_DATABASE_URL` or `DATABASE_URL` and skip with an explicit message when no PostgreSQL is available; they must not silently use SQLite.
- The release review maps each TASK-002 requirement to code and test evidence with `MATCH`, `DRIFT`, or `UNVERIFIED`.

- [ ] **Step 1: Add explicit PostgreSQL integration coverage**

Cover Alembic upgrade, persisted profile creation, GET, PUT, confirm, and DRAFT-to-CONFIRMED readback using PostgreSQL. Assert the database URL scheme is PostgreSQL and fail rather than silently substituting SQLite when the integration command is explicitly requested.

- [ ] **Step 2: Run all verification commands**

```bash
pytest apps/api/tests -q
npm --prefix apps/web run type-check
npm --prefix apps/web run lint
npm --prefix apps/web run build
git diff --check
```

For the database gate, run the PostgreSQL-specific command with `TEST_DATABASE_URL` when available. If unavailable, report implementation/unit results as PASS and PostgreSQL migration/persistence/API verification as UNVERIFIED.

- [ ] **Step 3: Write intended-vs-implemented review**

For each P0 rule, cite the TASK-002 design and frozen product/technical documents, then name the exact implementation file and test. Report only meaningful mismatches and list the PostgreSQL verification gap explicitly if it remains.

- [ ] **Step 4: Update durable project documentation**

Update the README with database setup, Alembic commands, test commands, and the PostgreSQL requirement. Add a concise changelog entry for TASK-002 without describing out-of-scope features as implemented.

- [ ] **Step 5: Request review and commit release artifacts**

Run `git status --short`, inspect the complete diff, request a code review, address all critical/important findings, then commit:

```bash
git add README.md docs/review/TASK-002_INTENDED_VS_IMPLEMENTED.md docs/product/CHANGELOG.md apps/api/tests/test_postgres_integration.py
git commit -m "docs: verify profile confirmation task"
```

## Plan self-review

- Scope coverage: draft creation, four editable sections, provenance, skill self-assessment, confirmation state, PostgreSQL-first persistence, Alembic, API, UI, regression tests, and intended-vs-implemented review are all assigned.
- Placeholder scan: no implementation step depends on an unspecified endpoint, schema, or later task.
- Type consistency: all API operations use `ProfileRead`, `ProfileUpdate`, and UUID profile IDs defined in Task 1; the service signatures are defined in Task 2 and consumed by the endpoints and tests.
- Verification caveat: SQLite-backed tests are not sufficient evidence for the PostgreSQL gate; the final report must preserve `UNVERIFIED` if `TEST_DATABASE_URL` is unavailable.
