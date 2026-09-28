# AI Career OS dogfood fix design

## Goal

Repair the reported resume optimization, proof, mock interview, profile, and export paths while preserving confirmed user facts and avoiding accidental state regressions.

## Product rules

1. Interview availability is derived from one readiness CTA. A strengthening mission may start only when the same CTA says it is ready.
2. A fresh interview starts the session returned by the start endpoint. Older active sessions are invalidated before creating it.
3. A provider that ends before three answered rounds is continued with a Chinese follow-up. Errors keep the current question and answer box visible.
4. Recovery accepts factual evidence only, reports the server message, and never downgrades a ready mission.
5. Education, certificates, honors, and other objective profile facts are preserved. Existing evidence-backed resume bullets are accepted by default; generated JD projects remain confirmation-gated.
6. Student work is a separate campus section and is included only when relevant to the target role. Export uses the mission-bound profile and performs a visible preflight check.
7. Interview packs use actual source references and parsed question patterns. Mock interview receives the same pack context and asks in Simplified Chinese.

## Acceptance criteria

- No English placeholder strategy cards or duplicate cards/bullets for one experience.
- No stale-session display after `fresh=1`; at most one active session per mission.
- One answered turn cannot reach an unrecoverable debrief error; the question/input remain visible on failures.
- Test/audit garbage cannot become user-confirmed evidence; READY status remains READY.
- Interview pack references and question patterns are non-empty when source intel exists.
- Mock layout uses the full content width, existing pack loads without an empty flash, and the latest completed debrief remains reachable.
- Profile stores name, phone, email, and city; bound-profile export includes them, preserves section classification, normalizes skills, and blocks unsafe export with a checklist.

## Non-goals

- Do not rewrite unrelated mission/JD behavior.
- Do not delete existing audit artifacts or reset the dirty worktree.
- Do not auto-confirm facts in the live browser.
