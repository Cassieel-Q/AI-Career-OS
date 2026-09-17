# Multi-JD Input Implementation Plan

> **For agentic workers:** Use executing-plans task-by-task with test-driven-development. User authorized inline implementation; stop for review after verification.

**Goal:** Persist up to ten raw JD samples under the current Target Role.
**Architecture:** Add strict schemas, one dependent ORM table, a focused service and API router; integrate a separately keyed frontend section and typed request helpers.
**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL, Next.js/React, Node test runner.

## Global Constraints

- Follow the frozen TASK-006 spec and explicit PATCH omission/null semantics.
- No LLM, parsing, requirement normalization/aggregation, Market Profile or Gap.
- Synthetic fixtures only; never migrate or destructively test the app DB.
- Work in feature/multi-jd-input; no merge, push main or TASK-007.

## 1. Persistence, contracts and current-state service

- [ ] Add API regression tests in apps/api/tests/test_job_descriptions.py: missing current target, CRUD, omitted/null/blank fields, count, duplicate edits, order, stale parent, same-role reselection and replacement cascading.
- [ ] Run the tests before implementation. POST must fail with missing route.
- [ ] Add apps/api/app/job_description_schemas.py (create/patch/read contracts), job_description_service.py (CRUD, hash and locked current-parent validation), job_description_routes.py (four routes).
- [ ] Extend models.py with JobDescription and TargetRole dependent relationship; add 007_job_descriptions.py after 006_target_roles, with unique parent/hash and cascading FK.
- [ ] When role or exploration changes, delete/flush the old TargetRole before inserting its replacement. Keep the ID for the same role/snapshot. Update the existing ID-reuse test to assert the stronger evidence boundary.
- [ ] Wire the router into main.py. Run focused API/service/contracts/migration tests until green, then commit this logical unit when Git approval is available.

Core behavior under test:

```python
first = client.post(collection_url, json={"raw_text": "Build AI apps"})
assert first.status_code == 201
assert client.post(collection_url, json={"raw_text": " Build  AI apps\n"}).status_code == 409
assert client.patch(item_url, json={"source_url": None}).json()["raw_text"] == "Build AI apps"
```

## 2. Frontend collection flow

- [ ] Add Node tests in apps/web/tests/job-descriptions.test.mts and include all .test.mts files in the test command.
- [ ] First run observes missing helpers; implement apps/web/app/job-descriptions.ts with typed CRUD, safe errors, readiness and immutable collection transitions.
- [ ] Create apps/web/app/job-descriptions-section.tsx: fetch on mount, per-card editing, single unsaved add card, saves/deletes, errors and count guidance.
- [ ] Mount keyed by TargetRole ID inside page.tsx only for a current exploration/target. Cancel/ignore pending results after unmount; block JD operations during target selection. State from previous target cannot return.
- [ ] Add minimal styles in globals.css. At three saved records show readiness, with no navigation to an unimplemented route. Count excludes drafts.
- [ ] Run Node tests, type-check and lint; commit frontend unit when Git approval is available.

## 3. Invariants, verification and review

- [ ] Verify SHA-256 normalization preserves actual raw evidence, blank links become null, no URL fetching, no model calls.
- [ ] Verify Profile-first write locks serialize additions and target/preference mutations; classify uniqueness separately from general persistence errors.
- [ ] Run focused tests, full pytest, compileall, Alembic heads/graph tests and PostgreSQL offline SQL.
- [ ] Run frontend tests, type-check, lint and NTFS production build if feasible; use identical source, no commits from temporary clone.
- [ ] Create docs/review/TASK-006_INTENDED_VS_IMPLEMENTED.md with scope, evidence, review findings and limitations.
- [ ] Run git diff --check and final status; preserve small logical commits and stop ready for review.
