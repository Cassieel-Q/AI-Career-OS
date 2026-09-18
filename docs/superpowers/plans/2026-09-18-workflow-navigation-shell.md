# UIX-001 Workflow Navigation Shell Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Replace the stacked homepage workflow with URL-addressable Profile -> Preferences -> Role Exploration -> Target Role -> Job Descriptions steps backed by existing server state.

Architecture: Next App Router route folders render focused client step components inside a shared WorkflowShell. A typed workflow-state.ts service reads existing APIs and pure guard helpers derive valid routes and completion from persisted state. Existing domain helpers and backend contracts remain unchanged.

Tech Stack: Next.js 15 App Router, React 18, TypeScript 5.7, Tailwind CSS 3, Node built-in test runner, existing FastAPI API.

## Global Constraints

- Use only G:\myself\ai-career-OS-workflow-navigation-shell on branch feature/workflow-navigation-shell.
- Keep ab9c54b business contracts, API paths, CORS rules, and database schema unchanged.
- Do not start TASK-007 or add JD parsing, Market Profile, Gap, Roadmap, Dashboard, scoring, or authentication changes.
- Profile identity must be present in dynamic workflow URLs.
- Previous navigates only; Next checks server-backed state before routing.
- Browser refresh and deep links re-read the API; stale history cannot resurrect invalid downstream state.
- Preserve TASK-006 JD add/edit/delete/exact-duplicate/3-of-10/10-of-10 behavior.
- Preserve semantic controls, labels, focus, aria-current, disabled loading actions, and readable errors.
- Every production behavior change gets a failing test before implementation.

---

### Task 1: Server-state workflow model and guard rules

Files:
- Create apps/web/app/workflow-state.ts
- Create apps/web/tests/workflow-state.test.mts

Interfaces:
- WorkflowStep = "profile" | "preferences" | "role-exploration" | "target-role" | "job-descriptions"
- WorkflowSnapshot = { profile: Profile | null; roleExploration: RoleExplorationRead | null; targetRole: TargetRoleRead | null; jobDescriptions: JobDescriptionRead[] }
- workflowHref(profileId: string, step: WorkflowStep): string
- workflowCompletion(snapshot: WorkflowSnapshot): Record<WorkflowStep, boolean>
- latestValidStep(snapshot: WorkflowSnapshot): WorkflowStep | "start"
- canEnterStep(snapshot: WorkflowSnapshot, step: WorkflowStep): boolean
- readWorkflowSnapshot(profileId: string, apiUrl: string, request?: ProfileRequester): Promise<WorkflowSnapshot>

- [ ] Write failing tests for a draft profile stopping at Profile, preference invalidation producing no downstream completion, and dynamic route construction.
- [ ] Run node --experimental-strip-types --test tests/workflow-state.test.mts and confirm failure because the module is absent.
- [ ] Implement the typed reader using readApiPayload, getRoleExplorationRequest, getTargetRoleRequest, and getJobDescriptionsRequest. Treat expected missing exploration/target/JD collection responses as null or empty; preserve other errors for page-level error state.
- [ ] Re-run the focused test until it passes.
- [ ] Commit with git commit -m "feat: add server-backed workflow state guards".

---

### Task 2: Shared shell, step indicator, and navigation contracts

Files:
- Create apps/web/app/workflow-shell.tsx
- Create apps/web/app/workflow-navigation.ts
- Create apps/web/tests/workflow-navigation.test.mts

Interfaces:
- WorkflowShell({ profileId, currentStep, snapshot, children, loading?, error?, onRetry? })
- stepNavigation(profileId, step): { previous: string | null; next: string | null; nextLabel: string | null }
- stepLabel(step): string
- stepIndicatorState(snapshot, currentStep): Array<{ step; label; complete; current }>

- [ ] Write failing tests for Profile -> Preferences, Preferences -> Role Exploration, Role Exploration -> Target Role, Target Role -> JD, JD terminal behavior, Previous-only routes, and completion/current semantics.
- [ ] Run node --experimental-strip-types --test tests/workflow-navigation.test.mts and confirm failure.
- [ ] Implement pure navigation helpers and the shell. Use Next useRouter only for URL transitions. Render desktop vertical progress, compact mobile Step N of 5, a centered content panel, and one bottom navigation row. Use aria-current="step" on the current indicator. Do not provide a TASK-007 route.
- [ ] Re-run tests and npm.cmd run type-check.
- [ ] Commit with git commit -m "feat: add workflow shell navigation".

---

### Task 3: Start entry and Profile Confirmation step

Files:
- Create apps/web/app/workflow/start/page.tsx
- Create apps/web/app/workflow/[profileId]/profile/page.tsx
- Create apps/web/app/profile-step.tsx
- Modify apps/web/app/page.tsx
- Modify apps/web/app/layout.tsx
- Extend apps/web/tests/profile-flow.test.mts

- [ ] Add failing tests that assert upload redirects to the profile URL after POST, Profile confirmation is required before Preferences, and the root route is only the canonical entry.
- [ ] Run npm.cmd test -- --test-name-pattern "workflow|profile confirmation|upload" and confirm failure.
- [ ] Extract the current profile editing sections, evidence rendering, draft save, and confirm behavior into profile-step.tsx. Keep the existing payload, validation, and evidence helpers unchanged. The Profile route loads /api/v1/profiles/{profileId} on mount; missing profile returns to Start; DRAFT cannot be treated as complete.
- [ ] Implement Start upload with the existing POST /api/v1/resumes endpoint, then router.replace(workflowHref(profile_id, "profile")). The root page redirects to /workflow/start.
- [ ] Re-run matching tests and npm.cmd run type-check.
- [ ] Commit with git commit -m "feat: move upload and profile into workflow routes".

---

### Task 4: Career Preferences step and invalidation-aware continuation

Files:
- Create apps/web/app/workflow/[profileId]/preferences/page.tsx
- Create apps/web/app/preferences-step.tsx
- Extend apps/web/tests/profile-flow.test.mts or create apps/web/tests/preferences-step.test.mts

- [ ] Write failing tests for exactly two priorities, weekly hours 1-60, save-before-navigation ordering, and missing/unfinished preference redirects.
- [ ] Run npm.cmd test -- --test-name-pattern "preferences|save-and-continue" and confirm failure.
- [ ] Implement the focused Preferences step using CAREER_PREFERENCE_OPTIONS, toggleCareerPreference, isCareerPreferencesDraftValid, and saveCareerPreferencesRequest. Route only after a successful save; errors stay on the page with role=alert. Clear local downstream values when a draft input changes.
- [ ] Re-run matching tests and npm.cmd run type-check.
- [ ] Commit with git commit -m "feat: add preferences workflow step".

---

### Task 5: Role Exploration loading/error and Target Role step

Files:
- Create apps/web/app/workflow/[profileId]/role-exploration/page.tsx
- Create apps/web/app/role-exploration-step.tsx
- Create apps/web/app/workflow/[profileId]/target-role/page.tsx
- Create apps/web/app/target-role-step.tsx
- Extend apps/web/tests/profile-flow.test.mts

- [ ] Write failing tests for one request under duplicate clicks, visible loading, recoverable generation error with Retry, and Target Role deep-link guards.
- [ ] Run npm.cmd test -- --test-name-pattern "exploration|target role|retry" and confirm failure.
- [ ] Implement Role Exploration using existing read/create helpers and six-role evidence view helpers. The button is disabled while creating, shows a loading label, and on failure shows “岗位探索暂时生成失败，请重试。” or the safe API message plus Retry. Next is enabled only after a persisted snapshot exists.
- [ ] Implement Target Role loading and explicit selection using existing helpers. A target must belong to the current exploration before Next is enabled; no automatic AI choice is added.
- [ ] Re-run matching tests and npm.cmd run type-check.
- [ ] Commit with git commit -m "feat: add exploration and target role steps".

---

### Task 6: Job Descriptions step and terminal workflow behavior

Files:
- Create apps/web/app/workflow/[profileId]/job-descriptions/page.tsx
- Modify apps/web/app/job-descriptions-section.tsx
- Extend apps/web/tests/job-descriptions.test.mts

- [ ] Write failing tests for target-role requirement, missing-target redirect, zero-record empty state, 3/10 readiness, 10/10 add limit, and absence of TASK-007/Market Profile navigation.
- [ ] Run npm.cmd test -- --test-name-pattern "job description|terminal|TASK-007" and confirm failure.
- [ ] Move the existing JD section into the focused route. Keep exact request helpers, conservative URL normalization, exact duplicate handling, CRUD persistence, readiness, and target-role binding. Use compact previews by default where practical while keeping editing focused and accessible. The shell has no future-step route.
- [ ] Re-run matching tests and npm.cmd run type-check.
- [ ] Commit with git commit -m "feat: add terminal job descriptions workflow step".

---

### Task 7: Responsive shell styling and accessibility pass

Files:
- Modify apps/web/app/globals.css
- Modify apps/web/app/workflow-shell.tsx
- Modify apps/web/app/layout.tsx
- Extend apps/web/tests/workflow-navigation.test.mts

- [ ] Add failing pure state/class tests for aria-current, non-color completion markers, mobile Step N of 5, and disabled loading controls.
- [ ] Run npm.cmd test -- --test-name-pattern "aria|mobile|loading navigation" and confirm failure.
- [ ] Implement restrained layout using existing neutral background, green accent, input/button tokens, shell max-width around 1200px, and content max-width around 800-1000px. Desktop uses a vertical stepper; narrow screens use a compact top indicator and full-width content. Add visible focus-visible styles.
- [ ] Run npm.cmd test, npm.cmd run type-check, and npm.cmd run lint.
- [ ] Commit with git commit -m "style: polish responsive workflow shell".

---

### Task 8: Full regression and delivery evidence

- [ ] Run from apps/web: npm.cmd test; npm.cmd run type-check; npm.cmd run lint; npm.cmd run build.
- [ ] Run from the worktree root: git diff --name-only ab9c54b..HEAD; git diff --check; rg -n "TASK-007|Market Profile|Gap Analysis|salary analysis|fit score" apps/web/app.
- [ ] Inspect Get-ChildItem apps/web/app/workflow -Recurse -File; git status --short --branch; git log -1 --oneline.
- [ ] Report branch, HEAD, worktree path, changed files, route structure, component and guard strategy, refresh/history/invalidation behavior, Role Exploration loading/error, tests, type-check, lint, build, diff check, and known non-blocking debt. State UIX-001 READY FOR PRODUCT OWNER MANUAL ACCEPTANCE. Do not merge, push main, or start TASK-007.
