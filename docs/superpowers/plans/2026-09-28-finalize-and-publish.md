# AI Career OS Finalize and Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the tested AI Career OS version, document it with safe screenshots, organize the final project under `G:\myself\ai-career`, and publish it to the requested GitHub repository.

**Architecture:** Keep the current v0.2 full-intelligence worktree as the source of truth. Build a clean publication copy that excludes runtime caches, audit dumps, logs, personal data, and credentials while preserving the application, tests, curated interview skills, resume skills, product/technical docs, and selected screenshots. Add the hydration warning guard and verify the clean copy before pushing `main`.

**Tech Stack:** Next.js 15 / TypeScript, FastAPI / SQLAlchemy, SQLite test fixtures, curated Markdown interview packs, GitHub.

## Global Constraints

- Do not upload API keys, environment files, runtime logs, database files, personal resumes, or audit fixtures containing personal evidence.
- Keep `knowledge/interview_skills/` and `knowledge/resume_skills/` in the final repository.
- Preserve the current tested v0.2 full-intelligence behavior and the final deletion/interview-intelligence commits.
- Remove only clearly disposable historical working copies after a manifest is written; preserve source/reference repos that contain unique interview or product knowledge.
- Verify hydration, web type-check/tests, API targeted tests, and GitHub remote state before claiming completion.

---

### Task 1: Freeze the hydration fix

**Files:**
- Modify: `apps/web/app/layout.tsx`
- Test: `apps/web/tests/layout.test.mts`

- [x] Write and run the failing test for the extension-attribute mismatch.
- [x] Add `suppressHydrationWarning` to the root `<html>` element.
- [x] Run the regression test and TypeScript check.

### Task 2: Build the publication manifest

**Files:**
- Create: `docs/release/final-project-manifest.md`
- Create: `docs/release/screenshots/`

- [ ] Record source commit, dirty-file handling, retained knowledge sources, excluded paths, and historical directory decisions.
- [ ] Copy only representative UI screenshots without personal identifiers or raw resume text.

### Task 3: Write the public README

**Files:**
- Modify: `README.md`

- [ ] Describe the user flow from JD and resume through AI ranking, rewrite approval, PDF export, mock interview, evidence coaching, and Interview Memory.
- [ ] Document local setup, environment variables, migrations, test commands, curated interview pack provenance, deletion semantics, and known limitations.
- [ ] Embed the selected screenshots with relative repository paths.

### Task 4: Create and verify the clean final repository

- [ ] Copy the current source snapshot to `G:\myself\ai-career` while excluding `.git`, caches, logs, `_audit`, temporary scripts, runtime databases, and private fixtures.
- [ ] Add a focused `.gitignore` and final manifest.
- [ ] Run secret/path scans and verify that interview/resume knowledge packs exist.
- [ ] Run web and API verification from the clean copy.

### Task 5: Publish and archive historical copies

- [ ] Initialize or update the final repository remote `https://github.com/Cassieel-Q/AI-Career-OS.git`.
- [ ] Commit the final snapshot and push `main` using a safe remote check.
- [ ] Move clearly superseded Git worktrees under `G:\myself\ai-career\archive` only after the final copy and remote are verified.
- [ ] Keep `aicareeri-interview`, the PM reference material, and curated knowledge in the final/references area.

### Task 6: Final verification

- [ ] Confirm GitHub `main` points to the final commit.
- [ ] Confirm no secrets or personal files are tracked.
- [ ] Report exact URLs, tests, retained directories, archived directories, and any unverified limits.
