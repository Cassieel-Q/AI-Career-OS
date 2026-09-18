# TASK-006 intended vs implemented review

Date: 2026-09-18  
Branch: `feature/multi-jd-input`  
Scope: collect and edit raw Job Description samples for the one active Target Role.

## Approved contract

- A current Target Role may hold zero through ten raw JD samples.
- The product recommends five to ten samples; three saved samples are the
  minimum for future market analysis readiness.
- Samples are manually entered only. TASK-006 does not call an LLM, parse,
  normalize, aggregate, scrape, or make market claims.
- Exact duplicates are rejected per Target Role using a deterministic SHA-256
  content hash. Hash normalization trims and collapses whitespace while the
  original `raw_text` is preserved exactly.
- `source_url` is optional. Blank or whitespace-only values become `null`;
  HTTP(S) URLs with a host are accepted without fetching the URL.
- PATCH semantics are explicit: omitted fields are preserved, `source_url:
  null` clears the URL, and a supplied `raw_text` must be non-blank and
  recomputes `content_hash`.
- The active Target Role owns the collection. Re-selecting the same role in the
  same exploration snapshot preserves its Target Role ID and samples; changing
  role or snapshot creates a new Target Role ID so old samples cascade away.
- There is no JD history, multiple active target roles, scraping, or downstream
  market-analysis route in this task.

## Implemented backend

- Added `JobDescription` persistence and migration `007_job_descriptions`,
  including the Target Role foreign key with `ON DELETE CASCADE`, indexed
  collection lookup, timestamps, and the per-target-role unique content hash.
- Added strict create, patch, and read schemas with defensive raw-text and
  source-URL validation.
- Added:
  - `GET /api/v1/target-roles/{target_role_id}/job-descriptions`
  - `POST /api/v1/target-roles/{target_role_id}/job-descriptions`
  - `PATCH /api/v1/job-descriptions/{jd_id}`
  - `DELETE /api/v1/job-descriptions/{jd_id}`
- Collection mutations lock the Profile boundary, reread the current
  Target Role and Role Exploration binding, enforce the ten-item cap, perform
  an early duplicate check, and retain the database unique constraint as the
  final duplicate guard.
- Existing Target Role selection now preserves the row only for the same role
  and exploration snapshot; a changed selection atomically replaces the row,
  preventing stale pages from writing to an old JD collection.

## Implemented frontend

- Added typed collection helpers with exact CRUD contracts and PATCH omission
  preservation.
- Added a Target Role-scoped JD section with saved editable cards, add/cancel,
  update, delete, count, ten-item cap, and safe error states.
- Blank source URLs are normalized to `null` before create/update requests.
- The UI shows the three-sample readiness state and a non-navigating next-step
  placeholder; it does not introduce a future analysis route.
- The section is keyed to the active Target Role ID, so a replaced Target Role
  starts with a clean collection and late responses from the old role are
  ignored.

## Verification evidence

- Backend full suite with provider credentials removed from the test process:
  `386 passed, 2 skipped`.
- Frontend Node suite: `38 passed`.
- TypeScript `tsc --noEmit`: passed in the clean NTFS verification clone.
- ESLint: passed with no warnings or errors.
- Next.js production build: passed in the clean NTFS verification clone.
- Backend `compileall`: passed.
- Alembic reports one head: `007_job_descriptions`.
- Offline Alembic SQL generation includes the `job_descriptions` table and
  unique `(target_role_id, content_hash)` constraint.
- OpenAPI route inspection confirms all TASK-006 CRUD operations and the
  existing Target Role and Role Exploration operations.
- `git diff --check`: passed before the implementation commits.

## Non-goals preserved

- No LLM calls, JD parsing, normalization/aggregation, Market Profile, Gap
  Analysis, prioritization, scraping, semantic deduplication, salary/demand
  analysis, or TASK-007 work.
- No multiple active target roles, JD history, automatic applications, or
  downstream analysis acceptance is included.
- No production/shared database migration was run during TASK-006 validation.
