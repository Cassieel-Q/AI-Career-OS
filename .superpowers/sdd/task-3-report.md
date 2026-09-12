# Task 3 report: frontend career-preference helpers

## Changed files

- `apps/web/app/career-preferences.ts` — added the frozen five-option priority model, ordered two-item toggle, strict weekly-hours validation, confirmed-only edit gate, profile draft rehydration, and PUT request helper.
- `apps/web/app/profile-flow.ts` — added optional nullable `Profile.preferences` typing and normalized missing/null preferences to `null` at profile boundaries.
- `apps/web/tests/profile-flow.test.mts` — added coverage for labels, selection ordering/cap/removal, validation, DRAFT visibility, missing/null compatibility, persisted draft rehydration, request payload, and safe API errors.

## Verification

- `npm.cmd test` (from `apps/web`) — **21 passed, 0 failed**.
- `git diff --check` — passed.
- `npm.cmd run type-check` / `npm.cmd run lint` — not runnable in this checkout because the local Next.js/TypeScript binaries were unavailable; an attempted dependency install was interrupted by the environment.

## Commit

Implementation commit: `acd40dc4cec32fc6732d0263e36fcdd038ccc197` (`feat: add career preference frontend state`)
