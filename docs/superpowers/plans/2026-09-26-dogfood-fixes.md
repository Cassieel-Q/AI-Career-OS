# AI Career OS dogfood fixes execution plan

> Execute in order. Each task starts with a failing test, then the smallest implementation, then targeted and full verification. Preserve all unrelated dirty files.

## Task 1 — unified interview CTA and session identity

**Files:** `apps/web/app/mission-page.tsx`, `apps/web/app/mission-state.ts`, `apps/web/app/proof-steps.tsx`, `apps/web/app/proof-state.ts`, `apps/api/app/proof_service.py`, related tests.

1. Add red tests for strengthening readiness CTA, `fresh=1` using the returned session, and invalidating prior ACTIVE sessions.
2. Run only those tests and record the failure.
3. Make `renderInterview` and compact hints consume `resolveInterviewTabCta`; make start flow store/use the returned session; invalidate old ACTIVE sessions and choose the newest session deterministically.
4. Run targeted web/API tests, then inspect the diff.

## Task 2 — three-round continuity and recovery validation

**Files:** `apps/api/app/proof_service.py`, `apps/api/app/mission_service.py`, `apps/web/app/proof-shell.tsx`, `apps/web/app/mission-page.tsx`, tests.

1. Add red tests for an early provider completion, Chinese error copy with preserved input, invalid recovery text, and READY status preservation.
2. Implement automatic follow-up generation until three answered rounds, inline interview errors, factual recovery validation, and message rendering.
3. Run targeted tests and API type/import checks.

## Task 3 — resume strategy and target-resume semantics

**Files:** `apps/api/app/mission_provider.py`, `apps/api/app/mission_service.py`, `apps/web/app/mission-page.tsx`, `apps/web/app/export-target-resume.ts`, tests.

1. Add red tests for no English placeholder, strategy dedupe, duplicate bullet removal, existing evidence default acceptance, and pending generated projects.
2. Implement normalization/deduplication and explicit status rules. Keep objective facts untouched; separate campus entries and avoid meta/interview prose in resume bullets.
3. Run target resume/API/web tests.

## Task 4 — interview pack and Chinese mock provider

**Files:** `apps/api/app/mission_provider.py`, `apps/api/app/proof_service.py`, `apps/api/app/interview_provider.py`, schemas/tests.

1. Add red tests with `skill_id`, `source_refs`, and body question-pattern sections, plus a provider prompt assertion.
2. Parse/filter source intel correctly and pass pack context into mock interview turns. Require Simplified Chinese for question, feedback, and references.
3. Run pack/provider/proof tests.

## Task 5 — proof UI, loading, debrief, and action feedback

**Files:** `apps/web/app/proof-shell.tsx`, `apps/web/app/proof-route.tsx`, `apps/web/app/proof-flow.ts`, `apps/web/app/mission-page.tsx`, `apps/web/app/globals.css`, tests.

1. Add red tests for full-width mock layout, bound back link, latest completed debrief selection, pack loading state, and action feedback.
2. Remove the hidden aside grid column, keep the interview route, settle pack/proof loads independently, and expose the latest completed session/debrief.
3. Run web tests and type-check.

## Task 6 — Profile contact facts and extraction/confirmation

**Files:** `apps/api/app/models.py`, schemas/services/routes/prompts, migration, `apps/web/app/mission-profile-confirm.tsx`, tests.

1. Add red API/schema tests for name, phone, email, and city round-trip.
2. Add nullable fields and migration, extract contacts, include them in confirm/read/update payloads, and render editable confirmation fields without auto-confirming them.
3. Run API migrations/tests and web type-check.

## Task 7 — bound-profile export and preflight

**Files:** `apps/web/app/mission-page.tsx`, `apps/web/app/export-target-resume.ts`, `apps/web/app/export-resume-checks.ts`, tests.

1. Add red tests for bound profile selection, section classification, skill normalization, filename, and checklist blocking.
2. Wire the existing helper, preserve education/honors/campus sections, normalize skills, and block print until checklist issues are shown/resolved.
3. Run web tests/type-check and a deterministic export smoke test.

## Task 8 — refresh race and final verification

**Files:** `apps/web/app/mission-page.tsx`, tests/docs.

1. Add a red test proving resume content renders before slow proof/readiness calls settle.
2. Split essential and optional refresh work; disable generation while loading and preserve confirmed edits.
3. Run the full web suite, type-check, targeted API suite, `git diff --check`, and record any pre-existing failures separately.
