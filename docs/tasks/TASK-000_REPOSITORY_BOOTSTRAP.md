# TASK-000 — Repository Bootstrap

**Assignee:** Codex  
**Goal:** Create a clean, version-controlled project skeleton before any business feature is implemented.

## Context

Product and Technical Specs are frozen. Do not implement Resume/JD/Gap business logic in this task.

## Required work

1. Initialize Git repository if not already initialized.
2. Configure GitHub remote if the Project Owner provides an empty repository URL.
3. Create/organize:

```text
apps/
  web/
  api/
docs/
  product/
  technical/
  tasks/
tests/
```

4. Initialize Next.js + TypeScript + Tailwind under `apps/web`.
5. Initialize FastAPI app under `apps/api`.
6. Add `.gitignore`.
7. Add `.env.example` with variable names only.
8. Add root `README.md`.
9. Add basic lint / type-check / formatting commands.
10. Add minimal backend health test and frontend build/type-check.
11. Preserve all frozen documentation.
12. Create baseline Git commit.

## Forbidden

- No Resume Parser
- No JD Analyzer
- No database business tables
- No RAG implementation
- No Agent framework
- No secrets
- No unapproved framework replacement

## Acceptance Criteria

- `apps/web` starts successfully.
- `apps/api` starts successfully.
- FastAPI exposes a minimal `/health` endpoint.
- backend test passes.
- frontend type-check/build passes.
- `.env` is ignored.
- frozen docs remain present.
- Git working tree is clean after baseline commit.

## Git

Suggested branch:
`chore/repository-bootstrap`

Suggested commit:
`chore: bootstrap project repository`

## Required completion report

```text
Changed Files:
Commands Run:
Tests:
Lint / Type Check:
Git Branch:
Commit:
Known Issues:
Scope Deviations:
```
