# Task 4 report: confirmed-only Career Preferences UI

## Changed files

- `apps/web/app/page.tsx` — added confirmed-profile-only preference draft state, profile-boundary rehydration, ordered selection/removal, weekly-hours editing and validation, PUT save handling, safe errors, and the disabled Role Exploration placeholder.
- `apps/web/app/globals.css` — added scoped preference card grid, selected ordinal, disabled state, and responsive layout styles.
- `apps/web/tests/profile-flow.test.mts` — added save-eligibility and removal-promotion coverage for the preference interaction contract.

## Verification

- `npm.cmd test` (from `apps/web`) — **21 passed, 0 failed**.
- `npm.cmd run type-check` — not runnable in this checkout (`tsc` unavailable).
- `npm.cmd run lint` — not runnable in this checkout (`next` unavailable).
- `git diff --check` — passed.

## Commit

Implementation commit: `4261ed5e9aa85e16d731a2e0d4727d1d50ebf4db` (`feat: add career preferences UI`)
