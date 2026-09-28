# Career Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build the smallest complete Career Preferences vertical slice: two ranked priorities and weekly preparation hours, persisted only for confirmed profiles and editable through the existing profile page.

**Architecture:** Add a dedicated one-to-one CareerPreference relational record and a strict request/response boundary. A service-layer upsert locks the parent profile, enforces the CONFIRMED state, and leaves profile facts untouched; ProfileRead carries an optional preferences object for rehydration. The existing Next.js profile page consumes pure preference helpers and renders a minimal confirmed-only selection section.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Alembic, PostgreSQL/SQLite test fixtures, Next.js, React, TypeScript, Node test runner, pytest.

## Global Constraints

- Work only in G:\myself\ai-career-OS-career-preferences on feature/career-preferences.
- Do not merge main, push main, or start TASK-004 Role Exploration.
- Do not change Resume extraction, Resume/Profile fact semantics, unrelated database tables, or unrelated frontend features.
- No LLM calls are required; deterministic validation, ordering, state transitions, and persistence remain in code.
- Supported priorities are exactly COMPENSATION, LESS_CODING, FAST_EMPLOYMENT, CURRENT_FIT, and LONG_TERM_GROWTH.
- priority_order contains exactly two different supported values; array order is persisted as priority 1 then priority 2.
- weekly_hours is a strict integer in the inclusive range 1–60.
- Only a CONFIRMED profile may create or update preferences; a DRAFT profile returns HTTP 409 and is never auto-confirmed.
- Existing Profile GET remains backwards-compatible by returning an optional preferences object or null.
- Never set TEST_DATABASE_URL equal to DATABASE_URL; skip PostgreSQL integration tests when no dedicated test URL exists.
- Do not print or log secrets, database internals, or unrelated resume/profile values.
- Commit only TASK-003 changes and push only origin/feature/career-preferences after all verification.

---

### Task 1: Define preference contracts, model, and migration

**Files:**
- Create: apps/api/tests/test_career_preferences.py
- Modify: apps/api/app/profile_schemas.py
- Modify: apps/api/app/models.py
- Create: apps/api/alembic/versions/004_career_preferences.py
- Modify: apps/api/tests/test_alembic_revisions.py

**Interfaces:**
- Produces CareerPreferencePriority, CareerPreferencesInput, and CareerPreferencesRead in app.profile_schemas.
- Produces models.CareerPreference and an optional UserProfile.career_preference relationship.
- Produces Alembic revision 004_career_preferences with down_revision = "003_credential_details".

- [ ] **Step 1: Write failing schema tests**

Add these tests before implementation:

~~~python
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.profile_schemas import (
    CareerPreferencesInput,
    CareerPreferencePriority,
    CareerPreferencesRead,
)


def test_preferences_accept_two_ordered_priorities_and_hours() -> None:
    payload = CareerPreferencesInput(
        priority_order=["FAST_EMPLOYMENT", "CURRENT_FIT"],
        weekly_hours=20,
    )
    assert payload.priority_order == [
        CareerPreferencePriority.FAST_EMPLOYMENT,
        CareerPreferencePriority.CURRENT_FIT,
    ]
    assert payload.weekly_hours == 20


@pytest.mark.parametrize(
    "value",
    [[], ["FAST_EMPLOYMENT"], ["FAST_EMPLOYMENT", "CURRENT_FIT", "COMPENSATION"]],
)
def test_preferences_require_exactly_two_priorities(value: list[str]) -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(priority_order=value, weekly_hours=20)


def test_preferences_reject_duplicate_or_unknown_priority() -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(priority_order=["CURRENT_FIT", "CURRENT_FIT"], weekly_hours=20)
    with pytest.raises(ValidationError):
        CareerPreferencesInput(priority_order=["CURRENT_FIT", "UNKNOWN"], weekly_hours=20)


@pytest.mark.parametrize("hours", [0, 61, 20.0, "20"])
def test_preferences_require_strict_integer_hours_in_range(hours: object) -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(
            priority_order=["CURRENT_FIT", "COMPENSATION"],
            weekly_hours=hours,
        )


def test_preferences_read_exposes_stored_order() -> None:
    result = CareerPreferencesRead(
        id=uuid4(),
        profile_id=uuid4(),
        priority_order=["COMPENSATION", "LESS_CODING"],
        weekly_hours=12,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert result.priority_order[0] is CareerPreferencePriority.COMPENSATION
~~~

Run: ..\.venv\Scripts\python.exe -m pytest tests/test_career_preferences.py -q

Expected: collection fails because the new contracts do not exist. Correct setup errors until the failure is specifically caused by missing TASK-003 contracts.

- [ ] **Step 2: Add strict Pydantic contracts**

In apps/api/app/profile_schemas.py, preserve every existing Profile fact validator and add:

~~~python
from typing import Self
from pydantic import StrictInt


class CareerPreferencePriority(StrEnum):
    COMPENSATION = "COMPENSATION"
    LESS_CODING = "LESS_CODING"
    FAST_EMPLOYMENT = "FAST_EMPLOYMENT"
    CURRENT_FIT = "CURRENT_FIT"
    LONG_TERM_GROWTH = "LONG_TERM_GROWTH"


class CareerPreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority_order: list[CareerPreferencePriority] = Field(min_length=2, max_length=2)
    weekly_hours: StrictInt = Field(ge=1, le=60)

    @model_validator(mode="after")
    def reject_duplicate_priorities(self) -> Self:
        if len(set(self.priority_order)) != 2:
            raise ValueError("priority_order must contain two different priorities")
        return self


class CareerPreferencesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    profile_id: UUID
    priority_order: list[CareerPreferencePriority]
    weekly_hours: int
    created_at: datetime
    updated_at: datetime
~~~

Run the focused tests. Expected: schema tests pass while model and migration assertions remain pending.

- [ ] **Step 3: Add the SQLAlchemy one-to-one model**

Inside UserProfile add:

~~~python
career_preference: Mapped[CareerPreference | None] = relationship(
    "CareerPreference",
    back_populates="profile",
    uselist=False,
    cascade="all, delete-orphan",
)
~~~

Add this model to apps/api/app/models.py:

~~~python
class CareerPreference(Base):
    __tablename__ = "career_preferences"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    priority_1: Mapped[str] = mapped_column(String(32), nullable=False)
    priority_2: Mapped[str] = mapped_column(String(32), nullable=False)
    weekly_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[UserProfile] = relationship(
        "UserProfile", back_populates="career_preference"
    )
~~~

Run the focused tests and verify Base.metadata.create_all creates the new table.

- [ ] **Step 4: Add migration 004 and revision-chain assertions**

Create apps/api/alembic/versions/004_career_preferences.py:

~~~python
"""create career preferences

Revision ID: 004_career_preferences
Revises: 003_credential_details
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "004_career_preferences"
down_revision = "003_credential_details"
branch_labels = None
depends_on = None

PRIORITIES = "'COMPENSATION', 'LESS_CODING', 'FAST_EMPLOYMENT', 'CURRENT_FIT', 'LONG_TERM_GROWTH'"


def upgrade() -> None:
    op.create_table(
        "career_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority_1", sa.String(length=32), nullable=False),
        sa.Column("priority_2", sa.String(length=32), nullable=False),
        sa.Column("weekly_hours", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("profile_id", name="uq_career_preferences_profile_id"),
        sa.CheckConstraint(f"priority_1 IN ({PRIORITIES})", name="ck_career_preferences_priority_1"),
        sa.CheckConstraint(f"priority_2 IN ({PRIORITIES})", name="ck_career_preferences_priority_2"),
        sa.CheckConstraint("priority_1 <> priority_2", name="ck_career_preferences_priorities_distinct"),
        sa.CheckConstraint("weekly_hours BETWEEN 1 AND 60", name="ck_career_preferences_weekly_hours"),
    )


def downgrade() -> None:
    op.drop_table("career_preferences")
~~~

Extend test_alembic_revisions.py to assert that the new revision is <=32 characters and directly follows 003_credential_details. Run:

~~~powershell
..\.venv\Scripts\python.exe -m pytest tests/test_career_preferences.py tests/test_alembic_revisions.py -q
~~~

Expected: all contract, metadata, and revision tests pass.

- [ ] **Step 5: Commit the contract/model/migration slice**

~~~powershell
git add apps/api/app/profile_schemas.py apps/api/app/models.py apps/api/alembic/versions/004_career_preferences.py apps/api/tests/test_career_preferences.py apps/api/tests/test_alembic_revisions.py
git commit -m "feat: add career preference persistence contract"
~~~

Expected: the worktree is clean and the commit contains only TASK-003 files.

### Task 2: Implement confirmed-only upsert and Profile GET rehydration

**Files:**
- Modify: apps/api/app/profile_schemas.py
- Modify: apps/api/app/profile_service.py
- Modify: apps/api/app/main.py
- Modify: apps/api/tests/test_career_preferences.py
- Modify: apps/api/tests/test_postgres_integration.py

**Interfaces:**
- ProfileRead.preferences: CareerPreferencesRead | None is additive and nullable.
- upsert_career_preferences(db: Session, profile_id: UUID, payload: CareerPreferencesInput) -> CareerPreferencesRead owns state checking and persistence.
- PUT /api/v1/profiles/{profile_id}/preferences returns CareerPreferencesRead.

- [ ] **Step 1: Write failing service/API tests**

Add tests for 404, DRAFT conflict, confirmed creation, order preservation, 1/60 boundaries, invalid values, fresh-session GET, no duplicate rows, unchanged Profile facts, and update of the same row. The core assertions are:

~~~python
def test_confirmed_profile_can_create_and_read_preferences(client, persisted_profile) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["FAST_EMPLOYMENT", "CURRENT_FIT"], "weekly_hours": 20},
    )
    assert response.status_code == 200
    assert response.json()["priority_order"] == ["FAST_EMPLOYMENT", "CURRENT_FIT"]
    assert client.get(f"/api/v1/profiles/{persisted_profile.id}").json()["preferences"]["weekly_hours"] == 20


def test_second_put_updates_one_row_and_keeps_profile_facts(
    client, db_session, persisted_profile
) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200
    before = client.get(f"/api/v1/profiles/{persisted_profile.id}").json()
    first = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["COMPENSATION", "LESS_CODING"], "weekly_hours": 12},
    ).json()
    second = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["CURRENT_FIT", "LONG_TERM_GROWTH"], "weekly_hours": 30},
    ).json()
    assert second["id"] == first["id"]
    after = client.get(f"/api/v1/profiles/{persisted_profile.id}").json()
    assert after["education"] == before["education"]
    assert after["skills"] == before["skills"]
    assert db_session.query(models.CareerPreference).filter_by(profile_id=persisted_profile.id).count() == 1
~~~

Run the focused file and verify each failure is caused by the absent route/service.

- [ ] **Step 2: Add the optional ProfileRead field and serializer**

Add preferences: CareerPreferencesRead | None = None to ProfileRead. In profile_service.py, add:

~~~python
def _preferences_read(
    preference: models.CareerPreference | None,
) -> CareerPreferencesRead | None:
    if preference is None:
        return None
    return CareerPreferencesRead(
        id=preference.id,
        profile_id=preference.profile_id,
        priority_order=[preference.priority_1, preference.priority_2],
        weekly_hours=preference.weekly_hours,
        created_at=preference.created_at,
        updated_at=preference.updated_at,
    )
~~~

Pass preferences=_preferences_read(profile.career_preference) in the existing ProfileRead constructor. Run existing Profile tests; legacy profiles must return preferences: null.

- [ ] **Step 3: Implement the transactional upsert**

In profile_service.py, add:

~~~python
def upsert_career_preferences(
    db: Session,
    profile_id: UUID,
    payload: CareerPreferencesInput,
) -> CareerPreferencesRead:
    profile = _get_profile(db, profile_id, for_update=True)
    if profile.status != ProfileStatus.CONFIRMED.value:
        raise HTTPException(
            status_code=409,
            detail="Career preferences require a confirmed profile",
        )
    preference = db.execute(
        select(models.CareerPreference)
        .where(models.CareerPreference.profile_id == profile_id)
        .with_for_update()
    ).scalar_one_or_none()
    values = {
        "priority_1": payload.priority_order[0].value,
        "priority_2": payload.priority_order[1].value,
        "weekly_hours": payload.weekly_hours,
        "updated_at": datetime.now(timezone.utc),
    }
    if preference is None:
        preference = models.CareerPreference(profile_id=profile_id, **values)
        db.add(preference)
    else:
        for field, value in values.items():
            setattr(preference, field, value)
    try:
        db.commit()
        db.refresh(preference)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Career preferences persistence failed",
        ) from error
    return _preferences_read(preference)  # type: ignore[return-value]
~~~

Keep Pydantic validation before this function and never mutate Profile fact collections.

- [ ] **Step 4: Add the FastAPI route**

Import the new schema and service function in main.py, then add:

~~~python
@app.put(
    "/api/v1/profiles/{profile_id}/preferences",
    response_model=CareerPreferencesRead,
)
def save_career_preferences(
    profile_id: UUID,
    payload: CareerPreferencesInput,
    db: Session = Depends(get_db),
) -> CareerPreferencesRead:
    return upsert_career_preferences(db, profile_id, payload)
~~~

FastAPI returns 422 for request validation; the service returns safe 404/409/503 categories without database internals.

- [ ] **Step 5: Add safe PostgreSQL integration coverage**

Extend test_postgres_integration.py with an integration test that creates a minimal profile, confirms it, PUTs preferences, closes the session, and reads the same preference through a fresh session. Reuse _postgres_url() and _assert_test_database_isolation(); no fallback URL and no destructive application-DB cleanup.

Run:

~~~powershell
..\.venv\Scripts\python.exe -m pytest tests/test_career_preferences.py tests/test_profiles.py tests/test_postgres_integration.py -q
~~~

Expected: SQLite/API tests pass; PostgreSQL tests skip only when TEST_DATABASE_URL is absent.

- [ ] **Step 6: Commit backend behavior**

~~~powershell
git add apps/api/app/profile_schemas.py apps/api/app/profile_service.py apps/api/app/main.py apps/api/tests/test_career_preferences.py apps/api/tests/test_postgres_integration.py
git commit -m "feat: enforce confirmed career preferences"
~~~

### Task 3: Add pure frontend preference state and request helpers

**Files:**
- Create: apps/web/app/career-preferences.ts
- Modify: apps/web/app/profile-flow.ts
- Modify: apps/web/tests/profile-flow.test.mts

**Interfaces:**
- Produces CareerPreferencePriority, CareerPreferences, CareerPreferencesDraft, and CAREER_PREFERENCE_OPTIONS.
- Produces toggleCareerPreference, isCareerPreferencesDraftValid, careerPreferencesDraftFromProfile, profileCanEditCareerPreferences, and saveCareerPreferencesRequest.

- [ ] **Step 1: Write failing helper tests**

Add Node tests for labels, ordered selection, two-item cap, removal promotion, validation, DRAFT visibility, rehydration, and request payload:

~~~typescript
test("the five frozen priority options have Chinese labels", () => {
  assert.equal(CAREER_PREFERENCE_OPTIONS.length, 5);
  assert.deepEqual(CAREER_PREFERENCE_OPTIONS.map((option) => option.label), [
    "薪资优先",
    "少写代码",
    "尽快就业",
    "当前匹配度",
    "长期成长",
  ]);
});

test("selection order appends, caps at two, and removes the clicked item", () => {
  const first = toggleCareerPreference([], "FAST_EMPLOYMENT");
  const second = toggleCareerPreference(first, "CURRENT_FIT");
  assert.deepEqual(toggleCareerPreference(second, "COMPENSATION"), second);
  assert.deepEqual(toggleCareerPreference(second, "FAST_EMPLOYMENT"), ["CURRENT_FIT"]);
});

test("draft validity requires two priorities and integer hours from one to sixty", () => {
  assert.equal(isCareerPreferencesDraftValid([], "20"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT"], "20"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT", "CURRENT_FIT"], "0"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT", "CURRENT_FIT"], "20.5"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT", "CURRENT_FIT"], "20"), true);
});
~~~

Run: npm.cmd test. Expected: the new imports fail because the helper module does not yet exist.

- [ ] **Step 2: Implement the pure frontend helper module**

Create apps/web/app/career-preferences.ts with:

~~~typescript
import type { Profile } from "./profile-flow";

export type CareerPreferencePriority =
  | "COMPENSATION"
  | "LESS_CODING"
  | "FAST_EMPLOYMENT"
  | "CURRENT_FIT"
  | "LONG_TERM_GROWTH";

export type CareerPreferences = {
  id: string;
  profile_id: string;
  priority_order: [CareerPreferencePriority, CareerPreferencePriority];
  weekly_hours: number;
  created_at: string;
  updated_at: string;
};

export type CareerPreferencesDraft = {
  priority_order: CareerPreferencePriority[];
  weekly_hours: string;
};

export const CAREER_PREFERENCE_OPTIONS = [
  { value: "COMPENSATION", label: "薪资优先" },
  { value: "LESS_CODING", label: "少写代码" },
  { value: "FAST_EMPLOYMENT", label: "尽快就业" },
  { value: "CURRENT_FIT", label: "当前匹配度" },
  { value: "LONG_TERM_GROWTH", label: "长期成长" },
] as const satisfies ReadonlyArray<{ value: CareerPreferencePriority; label: string }>;

export function toggleCareerPreference(
  selected: CareerPreferencePriority[],
  value: CareerPreferencePriority,
): CareerPreferencePriority[] {
  if (selected.includes(value)) return selected.filter((item) => item !== value);
  return selected.length >= 2 ? selected : [...selected, value];
}

export function isCareerPreferencesDraftValid(
  priorityOrder: CareerPreferencePriority[],
  weeklyHours: string,
): boolean {
  if (priorityOrder.length !== 2 || new Set(priorityOrder).size !== 2) return false;
  if (!/^\\d+$/.test(weeklyHours)) return false;
  const hours = Number(weeklyHours);
  return Number.isInteger(hours) && hours >= 1 && hours <= 60;
}

export function careerPreferencesDraftFromProfile(profile: Profile): CareerPreferencesDraft {
  return {
    priority_order: profile.preferences?.priority_order
      ? [...profile.preferences.priority_order]
      : [],
    weekly_hours: profile.preferences ? String(profile.preferences.weekly_hours) : "",
  };
}

export function profileCanEditCareerPreferences(profile: Profile | null): boolean {
  return profile?.status === "CONFIRMED";
}

export async function saveCareerPreferencesRequest(
  profileId: string,
  draft: CareerPreferencesDraft,
  apiUrl: string,
  request: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> = fetch,
): Promise<CareerPreferences> {
  const response = await request(apiUrl + "/api/v1/profiles/" + profileId + "/preferences", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      priority_order: draft.priority_order,
      weekly_hours: Number(draft.weekly_hours),
    }),
  });
  return await readApiPayloadFromResponse<CareerPreferences>(response);
}

async function readApiPayloadFromResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  const payload = raw ? JSON.parse(raw) : null;
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail?: unknown }).detail
      : null;
    throw new Error(typeof detail === "string" ? detail : "Request failed (HTTP " + response.status + ").");
  }
  return payload as T;
}
~~~

Modify profile-flow.ts to import the type, add preferences?: CareerPreferences | null to Profile, and normalize missing values to null.

- [ ] **Step 3: Verify helper tests**

Add assertions for Profile GET rehydration, persisted draft conversion, DRAFT visibility, valid PUT JSON, and safe API errors. Run npm.cmd test; all existing and new tests must pass.

- [ ] **Step 4: Commit frontend helper behavior**

~~~powershell
git add apps/web/app/career-preferences.ts apps/web/app/profile-flow.ts apps/web/tests/profile-flow.test.mts
git commit -m "feat: add career preference frontend state"
~~~

### Task 4: Render the confirmed-only Career Preferences section

**Files:**
- Modify: apps/web/app/page.tsx
- Modify: apps/web/app/globals.css
- Modify: apps/web/tests/profile-flow.test.mts

- [ ] **Step 1: Add failing visibility and rehydration tests**

Cover profileCanEditCareerPreferences for DRAFT/CONFIRMED and careerPreferencesDraftFromProfile for a stored preference. Run npm.cmd test and verify the tests fail only because the page wiring/helpers are absent.

- [ ] **Step 2: Add local draft state and hydrate it at every profile boundary**

In page.tsx, import the helper module and add:

~~~typescript
const [preferenceDraft, setPreferenceDraft] = useState<CareerPreferencesDraft>({
  priority_order: [],
  weekly_hours: "",
});
const [savingPreferences, setSavingPreferences] = useState(false);
~~~

After GET, upload, and confirm responses, call setPreferenceDraft(careerPreferencesDraftFromProfile(payload)). Clear the draft when a new file is selected. Leave existing fact-editing guards and confirm behavior unchanged.

- [ ] **Step 3: Add selection and save handlers**

~~~typescript
function selectPreference(value: CareerPreferencePriority) {
  if (!profileCanEditCareerPreferences(profile) || savingPreferences) return;
  setPreferenceDraft((current) => ({
    ...current,
    priority_order: toggleCareerPreference(current.priority_order, value),
  }));
}

async function savePreferences() {
  const currentProfile = profile;
  if (!currentProfile || !profileCanEditCareerPreferences(currentProfile)) return;
  if (!isCareerPreferencesDraftValid(preferenceDraft.priority_order, preferenceDraft.weekly_hours)) return;
  setSavingPreferences(true);
  setError("");
  try {
    const saved = await saveCareerPreferencesRequest(currentProfile.profile_id, preferenceDraft, apiUrl);
    setPreferenceDraft(careerPreferencesDraftFromProfile({ ...currentProfile, preferences: saved }));
    setProfile((current) => current ? { ...current, preferences: saved } : current);
  } catch (saveError) {
    setError(saveError instanceof Error ? saveError.message : "Career preferences could not be saved.");
  } finally {
    setSavingPreferences(false);
  }
}
~~~

- [ ] **Step 4: Render the minimal UI only after confirmation**

Render below the existing Profile actions:

~~~tsx
{profileCanEditCareerPreferences(profile) && (
  <section className="career-preferences" aria-label="Career Preferences">
    <h3>Career Preferences</h3>
    <p className="profile-note">Choose the two priorities that matter most for your next career decision.</p>
    <div className="preference-grid">
      {CAREER_PREFERENCE_OPTIONS.map((option) => {
        const order = preferenceDraft.priority_order.indexOf(option.value);
        const selected = order !== -1;
        const full = preferenceDraft.priority_order.length >= 2;
        return (
          <button
            key={option.value}
            type="button"
            className={selected ? "preference-card selected" : "preference-card"}
            aria-pressed={selected}
            disabled={savingPreferences || (full && !selected)}
            onClick={() => selectPreference(option.value)}
          >
            <span>{selected ? "#" + (order + 1) : ""}</span>
            <span>{option.label}</span>
          </button>
        );
      })}
    </div>
    <label className="field-label">
      每周可用于职业准备/学习的时间（小时）
      <input
        type="number"
        min={1}
        max={60}
        step={1}
        value={preferenceDraft.weekly_hours}
        disabled={savingPreferences}
        onChange={(event) => setPreferenceDraft((current) => ({ ...current, weekly_hours: event.target.value }))}
      />
    </label>
    <button
      type="button"
      onClick={savePreferences}
      disabled={savingPreferences || !isCareerPreferencesDraftValid(preferenceDraft.priority_order, preferenceDraft.weekly_hours)}
    >
      {savingPreferences ? "Saving..." : "Save preferences"}
    </button>
    <button type="button" className="button-secondary" disabled>
      下一步：探索适合我的岗位
    </button>
  </section>
)}
~~~

Add only local CSS for the card grid, selected ordinal, and disabled state. DRAFT profiles must not render this section; no Role Exploration request or navigation is allowed.

- [ ] **Step 5: Verify frontend behavior and commit**

Extend Node tests for five options, first/second click order, two-item cap, removal promotion, Save states, rehydration, edit/resave, and DRAFT suppression. Run:

~~~powershell
npm.cmd test
npm.cmd run type-check
npm.cmd run lint
~~~

Expected: all tests pass, TypeScript has no errors, and lint has no errors.

Then commit:

~~~powershell
git add apps/web/app/page.tsx apps/web/app/globals.css apps/web/tests/profile-flow.test.mts
git commit -m "feat: add career preferences UI"
~~~

### Task 5: Cross-layer verification and intended-vs-implemented review

**Files:**
- Modify only tested TASK-003 files when a verification failure identifies a defect.
- Create: docs/review/TASK-003_INTENDED_VS_IMPLEMENTED.md

- [ ] **Step 1: Run focused and full backend checks**

~~~powershell
cd apps/api
..\.venv\Scripts\python.exe -m pytest tests/test_career_preferences.py tests/test_profiles.py tests/test_profile_service.py tests/test_alembic_revisions.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m compileall -q app
~~~

Expected: zero failures; PostgreSQL integration skips only without a dedicated TEST_DATABASE_URL; compileall exits 0.

- [ ] **Step 2: Verify Alembic chain and offline SQL safely**

Use a non-production placeholder URL only for offline rendering:

~~~powershell
$env:DATABASE_URL = "postgresql+psycopg://offline_user:offline_password@localhost:5432/ai_career_os_offline"
..\.venv\Scripts\alembic.exe -c alembic.ini history
..\.venv\Scripts\alembic.exe -c alembic.ini upgrade head --sql | Select-String "career_preferences|004_career_preferences|priority_1|weekly_hours"
Remove-Item Env:DATABASE_URL
~~~

Expected: revision chain ends at 004_career_preferences and offline SQL contains the table and constraints. If a safe, already-configured development database is available and demonstrably separate, run upgrade-head verification there; never create credentials or downgrade/reset the application database.

- [ ] **Step 3: Run frontend checks and conditional production build**

Run npm.cmd test, npm.cmd run type-check, and npm.cmd run lint in apps/web. If the G: drive reproduces the known Next.js filesystem error, use or create C:\temp\ai-career-os-devcheck-task003, sync the branch, run npm.cmd ci, and run npm.cmd run build there. Do not copy secrets or user documents.

- [ ] **Step 4: Perform scope/security review**

~~~powershell
git diff --check
git status --short --branch
git ls-files | Select-String '\.(env|pem|key|pdf)$'
~~~

Confirm no Resume extraction changes, no Role Exploration code, no secrets, and no unrelated tables. Confirm the preference endpoint mutates only the dedicated career_preferences row.

- [ ] **Step 5: Write intended-vs-implemented review**

Create docs/review/TASK-003_INTENDED_VS_IMPLEMENTED.md with a table mapping every frozen requirement to implementation file(s), test(s), and verification status. Include explicit rows for CONFIRMED-only state, two-priority ordering, 1–60 hours, GET rehydration, no duplicate rows, unchanged Profile facts, DRAFT UI suppression, and TASK-004 not started. Include no secrets or personal data.

- [ ] **Step 6: Final commit, push, and clean-state verification**

After every check passes:

~~~powershell
git add apps/api apps/web docs/review/TASK-003_INTENDED_VS_IMPLEMENTED.md
git commit -m "feat: add career preferences"
git push origin feature/career-preferences
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/feature/career-preferences
~~~

Expected: remote branch equals the new commit SHA and the worktree is clean. Do not merge main or start TASK-004.
