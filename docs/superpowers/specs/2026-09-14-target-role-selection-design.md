# TASK-005 Target Role Selection Design

**Date:** 2026-09-14  
**Status:** Approved by Product Owner  
**Scope:** One active, user-selected target role for the current MVP

## Goal

Turn the current Role Exploration snapshot into one explicit user-owned Target
Role that anchors the later JD, Market Profile, and Gap Analysis workflow.

## Product decisions

- A user may select any of the six supported roles, including `LOW_PRIORITY`.
- Selection requires a confirmed Profile, saved Career Preferences, and a
  current persisted Role Exploration snapshot.
- The selected role is a user decision, not an AI recommendation or reranking.
- A Profile has exactly one active Target Role.
- Selecting another role replaces the current Target Role.
- Selection history, multiple targets, and a separate clear action are out of
  scope; reselecting is the MVP replacement mechanism.
- A Target Role is bound to the current Role Exploration snapshot. When
  preference changes invalidate and delete that snapshot, the bound Target
  Role is deleted as well and must be selected again after regeneration.

## User flow

```text
Confirmed Profile + saved preferences
  -> current six-role exploration
  -> click “选择为目标岗位” on any card
  -> Target Role saved immediately
  -> selected card shows current-target state
  -> later selection replaces it
```

The action is explicit through a dedicated button; clicking an ordinary card
does not save anything. The frontend rehydrates the saved selection on refresh.
No JD or downstream planning controls are added in this task.

## Data model

Add a one-to-one `target_roles` table:

| Field | Rule |
|---|---|
| `id` | UUID primary key |
| `profile_id` | UUID, required, unique, FK to `user_profiles`, cascade on profile deletion |
| `role_code` | Required canonical `RoleCode` value |
| `role_profile_version` | Required catalog version copied from the current exploration |
| `role_exploration_id` | Required unique FK to the bound exploration snapshot, cascade on exploration deletion |
| `selected_at` | Required timezone-aware timestamp |
| `updated_at` | Required timezone-aware timestamp |

The role display name remains code-owned and is derived from
`ROLE_PROFILE_BY_CODE`. No free-form role name, recommendation level, salary,
probability, or market data is stored. The entity itself represents a user
selection, so no redundant `selection_source` field is needed.

## API contract

```text
GET /api/v1/profiles/{profile_id}/target-role
PUT /api/v1/profiles/{profile_id}/target-role
```

Request:

```json
{"role_code": "AI_APPLICATION_ENGINEER"}
```

Read response:

```json
{
  "id": "<uuid>",
  "profile_id": "<uuid>",
  "role_code": "AI_APPLICATION_ENGINEER",
  "role_name": "AI Application Engineer",
  "role_profile_version": "v1",
  "role_exploration_id": "<uuid>",
  "selected_at": "<timestamp>",
  "updated_at": "<timestamp>"
}
```

`PUT` is idempotent for the same role and replaces a different current role.
The server loads the current exploration under a lock, validates that the
requested code is one of the six roles in the current snapshot, and copies the
catalog version and snapshot ID. Client-provided role names, versions, or
exploration IDs are rejected as unknown request fields.

Expected errors:

- `404`: Profile does not exist, or no Target Role has been selected on GET.
- `409`: Profile is not confirmed, no saved preferences exist, or no current
  Role Exploration exists.
- `422`: malformed request or unsupported role code.
- `503`: persistence failure.

## Invalidation and consistency

- Profile facts remain unchanged by selection.
- Career Preferences remain unchanged by selection.
- Role Exploration remains unchanged by selection.
- Existing preference invalidation deletes Role Exploration; the foreign-key
  cascade deletes its Target Role.
- A stale request cannot bind to an old snapshot because the service locks and
  validates the current exploration before writing.
- The unique `profile_id` constraint guarantees one active Target Role.

## Frontend boundary

Add typed request/read helpers and a small page integration:

- Load Target Role only when the current Profile has an effective Role
  Exploration.
- Treat a missing Target Role as an expected empty state.
- Clear in-memory Target Role when preferences are edited or saved.
- Allow one-click explicit selection from any of the six rendered cards.
- Preserve safe API error handling and stale-request protection.
- Show the selected role state without adding downstream workflow controls.

## Testing and acceptance

Backend tests cover strict schemas, migration order/constraints, confirmed and
current-exploration gates, all six role codes, `LOW_PRIORITY` selection,
replacement, one-to-one persistence, snapshot binding, stale/missing cases,
unknown request keys, safe errors, and unchanged source domains.

Frontend tests cover exact GET/PUT contracts, empty-state handling, safe errors,
role selection view data, selected-state mapping, and preference-change reset.

The feature is complete only when focused and full regression tests pass,
compile/type checks pass, the migration graph has one latest head, and the
worktree contains only intended TASK-005 changes.

## Non-goals

- Multiple active Target Roles or Career Plans
- Target Role history
- Role comparison
- AI reranking or a new provider call
- JD ingestion, Market Profile, Gap Analysis, Roadmap, or Dashboard changes
- New role codes or free-form role definitions
