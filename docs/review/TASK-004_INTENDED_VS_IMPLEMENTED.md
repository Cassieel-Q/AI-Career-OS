# TASK-004 intended vs implemented review

Date: 2026-09-13  
Branch: `feature/role-exploration`  
Scope: synthetic backend evaluation and regression coverage for the bounded Role Exploration slice.

## Contract summary

- The catalog is code-owned and versioned as `v1`, with exactly six role codes: `AI_PRODUCT_MANAGER`, `AI_APPLICATION_ENGINEER`, `AI_SOLUTION_CONSULTANT`, `LLM_ALGORITHM_ENGINEER`, `AI_DATA_ANALYST`, and `AI_PRODUCT_OPERATIONS`.
- `POST /api/v1/role-explorations` accepts a confirmed `profile_id` with saved career preferences and upserts one snapshot. `GET /api/v1/profiles/{profile_id}/role-exploration` returns the persisted snapshot and revalidates it against the same catalog version.
- Provider payloads contain only role code, level, bounded reasons/concerns, Profile-child `evidence_refs`, and saved `preference_refs`. The service adds catalog display names and `role_profile_version` before persistence.
- Every result must contain each of the six roles exactly once (at most three `RECOMMENDED`), with references grounded in current Profile child UUIDs and preference values limited to the two saved priorities.
- Context construction copies Profile child values/IDs, ordered preferences, weekly hours, and the immutable catalog into an isolated provider context. It does not mutate Profile or preference rows.
- Explicit Office aliases, technical skills, and credential values that already exist in the confirmed Profile remain available as grounded input. No unsupported credential is synthesized by Role Exploration.
- The frontend boundary is the existing Profile-confirmed/preferences flow plus the role-exploration API contract; this task adds no frontend behavior.

## Synthetic evaluation coverage

`apps/api/tests/test_role_exploration_evaluation.py` runs the same contract against three fictional, structurally varied contexts:

1. Product/operations emphasis with low coding and fast employment priorities.
2. Python/development emphasis with current-fit and less-coding priorities.
3. Algorithm/data emphasis with current-fit and long-term-growth priorities.

Each context uses fixture-only child rows (including Word/Excel/PowerPoint/Python/SQL and an explicit scored CET-4 credential), a fake provider that returns all six role codes in a different order, and assertions for:

- exact six-role uniqueness and catalog-owned names;
- grounded evidence UUIDs and participation of both saved preferences;
- explicit Office/technical-skill and credential preservation in provider input;
- absence of unsupported credential/result fields, probabilities, percentages, and market claims;
- unchanged Profile child rows, status, and saved preferences after generation;
- order/name agnosticism (the test asserts sets, not a preferred provider order).

No personal data, live provider calls, market data, or acceptance-resume values are used.

## Non-goals

This review does not add ranking science, employment probabilities, salary or demand estimates, credential inference, new role codes, free-form role names, profile editing, frontend UI, or production-provider behavior. PostgreSQL execution remains covered by the existing dedicated integration tests and is skipped when no isolated `TEST_DATABASE_URL` is configured.

