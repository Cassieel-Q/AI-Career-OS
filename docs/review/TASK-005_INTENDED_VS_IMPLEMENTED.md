# TASK-005 intended vs implemented review

Date: 2026-09-14  
Branch: `feature/target-role-selection`  
Scope: one active, user-selected Target Role bound to the current Role Exploration snapshot.

## Approved contract

- A confirmed Profile with saved preferences and a current Role Exploration
  may select any of the six supported role codes, including `LOW_PRIORITY`.
- The selection is user-owned and does not invoke an LLM or change the
  Role Exploration recommendation.
- A Profile has one active Target Role; selecting another role replaces it.
- No selection history, multi-target mode, clear endpoint, role comparison, or
  downstream JD/planning UI is included.
- Preference invalidation deletes the Role Exploration snapshot; the Target
  Role is bound to that snapshot and is deleted by the database foreign-key
  cascade.

## Implemented backend

- Added strict `TargetRoleInput` and `TargetRoleRead` contracts.
- Added `TargetRole` ORM model and Alembic migration `006_target_roles`.
- Added unique Profile and exploration bindings with `ON DELETE CASCADE`.
- Added:
  - `GET /api/v1/profiles/{profile_id}/target-role`
  - `PUT /api/v1/profiles/{profile_id}/target-role`
- The service locks the current Profile/exploration during selection, validates
  the requested role against the current six-role result, derives the catalog
  display name/version, and atomically inserts or replaces the one-to-one row.
- Stored role names are never accepted from the client and are re-derived from
  the code-owned catalog.

## Implemented frontend

- Added typed GET/PUT helpers in `apps/web/app/target-role.ts`.
- Added an explicit “选择为目标岗位” action to each exploration card.
- All six cards are selectable; the current target is visibly marked.
- The selection rehydrates after refresh and clears when the preference draft
  changes or the exploration becomes invalid.
- Existing stale-request guards prevent old exploration/selection responses
  from overwriting newer local state.

## Verification evidence

- Backend full suite: `353 passed, 2 skipped`.
- Frontend Node suite: `31 passed`.
- Backend `compileall`: passed.
- TypeScript `tsc --noEmit` using the complete TASK-004 dependency environment
  and a temporary path mapping: passed.
- ESLint CLI using the TASK-004 dependency environment and the target config:
  passed.
- Alembic heads/history: one head, `006_target_roles`, with the chain preserved
  through `005_role_explorations`.
- `git diff --check`: passed.

## Non-goals preserved

- No new role codes or free-form role names.
- No AI reranking, market claims, salary, probability, or demand data.
- No JD ingestion, Market Profile, Gap Analysis, Career Plan, roadmap, or
  dashboard changes.
- No real resumes or personal data in tests, logs, commits, or documentation.
