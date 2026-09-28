# UIX-001 Workflow Navigation Shell Design

**Date:** 2026-09-18
**Status:** FROZEN — Product Owner manual acceptance PASS (2026-09-19)
**Branch:** `feature/workflow-navigation-shell`
**Source:** Product Owner handoff pasted on 2026-09-18; existing API and UI inspected from `ab9c54b`

## Goal

Reorganize the existing Profile → Career Preferences → Role Exploration → Target Role → Job Descriptions capability into a URL-addressable, server-state-driven wizard without changing frozen business rules or backend contracts.

## Constraints

- Work only in the G: drive worktree `G:\myself\ai-career-OS-workflow-navigation-shell`.
- Do not start TASK-007 or add Market Profile, JD parsing, Gap, Roadmap, Dashboard, scoring, or schema changes.
- Keep the existing API paths, database rules, CORS behavior, and domain helpers.
- Profile identity lives in dynamic workflow URLs.
- The server remains the source of truth; URL selects presentation only.
- Previous only navigates. Next requires the current server state.
- Browser refresh and native history must rehydrate from the URL and API.
- The existing JD add/edit/delete/duplicate/readiness behavior remains intact.

## Chosen architecture

Use Next App Router route segments:

- `/workflow/start`
- `/workflow/[profileId]/profile`
- `/workflow/[profileId]/preferences`
- `/workflow/[profileId]/role-exploration`
- `/workflow/[profileId]/target-role`
- `/workflow/[profileId]/job-descriptions`

`/` becomes a canonical redirect to `/workflow/start`. Each dynamic route renders a focused client step inside a shared shell. Pages do not share a large in-memory wizard store.

### Shared shell

A `WorkflowShell` component renders:

- desktop vertical step indicator;
- compact top indicator on narrow screens;
- centered content panel;
- one shared bottom navigation row;
- accessible current-step semantics and visible focus states.

The shell receives the profile id, current step, server-derived workflow snapshot, and step content. Navigation helpers build dynamic URLs and use Next router navigation so browser Back/Forward remains native.

### Server-state helper and guards

A small workflow-state module reads the existing API contracts:

1. Profile (including optional saved preferences);
2. current Role Exploration;
3. current Target Role;
4. current Target Role JD collection when needed.

Pure guard functions map those facts to:

- completed step status;
- the latest valid route;
- whether a deep link is allowed;
- whether a Next action is allowed.

Each route performs a fresh read on mount. If a prerequisite is missing or stale, it replaces the URL with the latest valid step. Missing Target Role/JD responses are treated as expected empty states; user-facing errors use safe messages.

Preferences save success clears downstream client state and navigates to Role Exploration, which will re-read the server and show the empty-generation state. This respects backend cascade invalidation.

### Step components

- **Start:** uploads a PDF through the existing endpoint, then replaces the URL with the new profile route.
- **Profile:** reuses current editable sections and evidence display; Confirm is the only transition to Preferences.
- **Preferences:** reuses the five frozen options and 1–60 weekly-hours validation; save-and-continue persists before navigation.
- **Role Exploration:** reads or generates the current snapshot; generation has visible loading, disabled repeat clicks, recoverable error, and Retry.
- **Target Role:** shows all six exploration results and allows one explicit user selection; no automatic AI choice.
- **Job Descriptions:** reuses TASK-006 request helpers and CRUD UI; no TASK-007 navigation.

The large legacy stacked `page.tsx` implementation is split into focused step components, with domain helpers retained.

### Failure and stale-state behavior

- Draft or missing Profile: return to `/workflow/start`.
- Unconfirmed Profile: deep links beyond Profile return to Profile.
- Missing saved Preferences: return to Preferences.
- Missing Role Exploration: Target Role and later deep links return to Role Exploration.
- Missing current Target Role: Job Descriptions returns to Target Role.
- A preference change causes the backend to delete downstream derived state; a subsequent route read cannot resurrect the old snapshot or JDs.
- A stale browser history entry is guarded on arrival and replaced with the latest valid route.

## Testing design

Add focused frontend unit tests for workflow state/guard mapping, route construction, and navigation readiness. Retain existing domain helper tests. Add component-level coverage for:

- start upload redirect;
- Profile confirmation gating;
- preference save before navigation;
- Role Exploration loading, duplicate-click prevention, retry error;
- Target Role and JD deep-link guards;
- invalidation-aware route selection.

Run the required frontend tests, TypeScript type-check, ESLint, production build, and `git diff --check`. No backend changes are expected, so backend remains untouched and its existing regression evidence is reported separately.
