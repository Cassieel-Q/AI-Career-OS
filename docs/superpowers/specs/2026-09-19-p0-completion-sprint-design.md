# P0 Completion Sprint v0.1 Design

**Date:** 2026-09-19  
**Status:** Approved for implementation from the user-provided P0 sprint instruction  
**Branch:** `feature/p0-completion-sprint`  
**Baseline:** `70a373199f6085a2ebb6ed466e0966b69ab00858`

## Goal

Deliver the first complete, runnable loop after UIX-001: confirmed profile → current target role → at least three real job descriptions → evidence-grounded market profile → gap analysis → deterministic priorities with user override → four-week roadmap → progress/replan → dashboard.

The sprint keeps the frozen UIX-001 shell and does not merge or push `main`.

## Architecture

The FastAPI backend remains the only owner of business truth. New derived records are relational and bound to explicit upstream fingerprints:

```text
TargetRole + JobDescriptions
        ↓ sample_fingerprint
MarketProfile → MarketRequirement → RequirementEvidence
        ↓ market_profile_id + profile_updated_at
GapAnalysis → Gap → PriorityState
        ↓ confirmed priority + weekly_hours
RoadmapRevision → RoadmapWeek → RoadmapTask
        ↓ task status
Progress / Dashboard projection
```

Market Profile, Gap Analysis, and Roadmap records carry `VALID`/`INVALIDATED` state and a source fingerprint. JD mutations invalidate the derived chain server-side. Target-role or preference changes use the existing cascade behavior and therefore remove the old target/JD lineage. Progress updates only change task state.

LLM providers are injectable protocols with strict Pydantic contracts. They receive only the current target role and raw JD/profile evidence, return grounded semantic candidates, and never calculate frequency, status, ranking, or workload. Deterministic code normalizes aliases, aggregates counts, binds source JD evidence, validates gap states, computes priority factors, and rejects an over-budget roadmap. Tests use stub providers; production uses the existing OpenAI-compatible environment variables.

## Persistence model

Migration `008_p0_completion_sprint` adds:

- `market_profiles`: one current record per target role, sample fingerprint, JD count, status, timestamps.
- `market_requirements`: normalized requirement, category, count, frequency ratio, and stable order.
- `market_requirement_evidence`: source JD foreign key, copied evidence text, and optional source URL.
- `gap_analyses`: one analysis per market profile, profile fingerprint, status, timestamps.
- `gaps`: requirement link, `MATCHED`/`PARTIAL`/`MISSING`/`UNCERTAIN` state, severity, proximity, feasibility, rationale, and source evidence summary.
- `gap_priorities`: system rank, user rank, lane (`NOW`/`NEXT`/`NOT_NOW`), explanation, and override timestamp.
- `roadmaps`: revisioned plan bound to a gap analysis and priority fingerprint, weekly hours, status, and superseded revision.
- `roadmap_weeks`: four week objectives, focus gap IDs, and measurable outcomes.
- `roadmap_tasks`: actionable task text, estimated minutes, linked gap, completion criteria, and `TODO`/`IN_PROGRESS`/`DONE`/`SKIPPED` status.

The current row is selected by status and matching fingerprints. Regeneration replaces the current child rows in a transaction; replan creates a new roadmap revision and marks the prior revision superseded so execution history remains visible.

## Provider and deterministic contracts

### JD analysis

`JDAnalysisProvider.analyze(target_role, job_descriptions)` returns one extraction per JD. Every item has `name`, `category`, and `evidence_text` copied from exactly one supplied JD. Categories are `SKILL`, `RESPONSIBILITY`, `EXPERIENCE`, `EDUCATION`, `DOMAIN`, `COLLABORATION`, or `OTHER`.

`normalize_requirement` applies a small explicit alias map for the six frozen AI roles (for example `python programming` and `python development` → `Python`) and conservative whitespace/case normalization. Aggregation counts distinct JD IDs and calculates `count / sample_count` in Python.

### Gap analysis

`GapAnalysisProvider.explain(requirements, confirmed_profile)` may provide a semantic state proposal and rationale. The service validates the state enum, requires a market requirement and confirmed-profile evidence reference, and falls back to `UNCERTAIN` when a safe comparison is not possible. The persisted result never becomes an opaque fit percentage.

### Priority

The score is deterministic and explainable:

```text
priority_score =
  frequency_ratio * 40
  + severity_weight * 25
  + preference_relevance * 15
  + proximity_weight * 10
  + feasibility_weight * 10
```

`severity_weight`, `proximity_weight`, and `feasibility_weight` are fixed lookup values. Ties break by frequency, then requirement name. The service assigns `NOW` to the top three, `NEXT` to the next four, and `NOT_NOW` to the remainder. User ordering is stored separately and wins on reads and roadmap generation.

### Roadmap

The provider proposes actionable weekly tasks. The service validates every task has a linked gap, completion criteria, positive minutes, and a supported status. It rejects a plan whose total minutes exceed `weekly_hours * 60 * 4 * 1.15`; the 15% tolerance accommodates small rounding while preventing a 5-hour week from becoming a 30-hour plan.

## API surface

- `GET/POST /api/v1/target-roles/{target_role_id}/market-profile`
- `GET /api/v1/market-requirements/{requirement_id}/evidence`
- `GET/POST /api/v1/profiles/{profile_id}/gap-analysis`
- `GET/PUT /api/v1/profiles/{profile_id}/priorities`
- `GET/POST /api/v1/profiles/{profile_id}/roadmap`
- `PATCH /api/v1/roadmap-tasks/{task_id}`
- `POST /api/v1/profiles/{profile_id}/roadmap/replan`
- `GET /api/v1/profiles/{profile_id}/dashboard`

All endpoints return safe user-facing errors for not-ready, invalidated, provider, and persistence states. Provider failures map to loading/error/retry UI without exposing secrets or raw upstream exceptions.

## Workflow extension

The existing route sequence becomes:

```text
Profile → Preferences → Role Exploration → Target Role → Job Descriptions
→ Market Profile → Gap Analysis → Priorities → Roadmap → Progress → Dashboard
```

Each stage remains a focused URL route inside `WorkflowShell`. Deep-link guards derive from the server snapshot and redirect to the latest valid step. Refresh and browser history re-read server state. Dashboard only aggregates persisted records and does not create a second source of truth.

## Verification

- Backend focused tests after TASK-007–011: extraction grounding, normalization, counts, evidence, invalidation, gap states, deterministic priority, and override persistence.
- Backend focused tests after TASK-012–013: workload limit, task status, progress, replan revision and preservation.
- Frontend tests for request helpers, workflow guards, route navigation, loading/error/retry, and dashboard composition.
- Final gates: full pytest, frontend test/type-check/lint, Next production build, `compileall`, `git diff --check`, Alembic single head, and OpenAPI route sanity.

## Explicit non-goals

No scraping, RAG, salary prediction, autonomous agents, multi-target planning, universal occupation ontology, authentication redesign, or changes to frozen UIX-001 behavior beyond adding valid downstream steps.
