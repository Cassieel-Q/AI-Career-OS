# P0 v0.1 Synthesis + Roadmap Acceptance Fix Design

**Date:** 2026-09-19
**Status:** Approved by the user-provided Product Owner correction brief
**Branch:** `feature/p0-completion-sprint`

## Goal

Keep atomic JD and Profile evidence traceable while presenting decision-level capability clusters, generating derived stages on deliberate workflow transitions, and making Roadmap failures diagnosable and recoverable.

## Design

The existing `MarketProfile` and `MarketRequirement` rows remain the atomic evidence layer. A deterministic synthesis function derives transient capability clusters from those rows and their evidence. Clusters own no new facts: each cluster references one or more atomic requirement IDs, computes source JD IDs, prevalence, and evidence from those references, and uses stable grouping keys derived from normalized names/categories. The API returns `capabilities` alongside `requirements`, so existing persisted rows and evidence endpoints remain compatible and no migration is needed.

Gap analysis sends only capability clusters to the provider and persists one gap per cluster while retaining the linked atomic IDs in the response. Priority ranking therefore receives a bounded capability set; user ordering remains persisted against the same gap IDs. Roadmap input contains only target role, weekly hours, confirmed priorities, capability gap summaries, and bounded evidence summaries. The service validates provider output, linkage, four weeks, and workload before persistence.

The browser shell binds the Job Descriptions Next action to Market Profile generation and the Market Profile Next action to Gap generation. Passive reads never call generation endpoints. Roadmap generation uses one guarded attempt per click with explicit retry UI.

## Error handling

Provider adapters classify configuration, timeout, transport, structured-output/schema, and workload/linkage failures. Logs record only safe category, status, model, and payload counts; personal JD/Profile values and secrets are excluded. The API maps categories to stable 5xx/4xx responses. The browser keeps the user on the current step, shows the safe message, and exposes Retry.

## Validation

Add backend tests for deterministic clusters, grounded evidence, compact Gap/Priority/Roadmap inputs, provider error classification, and workload success/failure. Add frontend tests for one-click transitions, synthesized rendering, bounded priorities, retry state, and duplicate-submit guards. Run focused and full suites, type-check, lint, compileall, Alembic head, OpenAPI sanity, diff check, and the authorized G-first/C-fallback production build.
