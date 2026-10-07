# Resume Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user explicitly requested direct completion without review questions; execute inline in this task.

**Goal:** Deliver a mission-scoped Resume Studio with 18 real Typst templates, shared Agent/web editing, provenance checks, live page preview, and a real downloadable PDF.

**Architecture:** Import one confirmed `TargetResume` plus bound Profile into one revisioned Studio document. All later final-resume edits use that document and one mutation API. FastAPI renders validated document data through original Typst templates; the interview reads its confirmed revision.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, Typst CLI 0.15.1, PyMuPDF, Next.js 15, React 18, TypeScript, Node test runner, pytest.

## Global Constraints

- Work only in `G:\myself\ai-career\.worktrees\resume-studio` until integration; preserve uncommitted files in the main checkout.
- UI follows `docs/superpowers/specs/2026-10-07-ai-career-os-pixel-ui-copy-design.md`.
- 9 Chinese plus 9 English manifest entries are real compilable templates with full preview, not CSS screenshots.
- No upstream template/code copy. All 18 entries are original and third-party assets require license records.
- `TargetResume` and its bullet IDs remain traceable; Studio becomes the final editable version only after explicit import.
- Cross-language gallery browsing never translates or changes content.
- Only included high-risk `NEEDS_CONFIRMATION` and `BLOCKED_MISSING` nodes block PDF; omitted nodes do not.
- All writes require `If-Match` revision; 409 never overwrites an unsaved draft.
- Real PDF bytes must be returned; no browser print dialog.

---

### Task 1: Revisioned document and import

**Files:**
- Create: `apps/api/alembic/versions/014_resume_studio.py`
- Create: `apps/api/app/resume_studio_schemas.py`
- Create: `apps/api/app/resume_studio_service.py`
- Modify: `apps/api/app/models.py`
- Test: `apps/api/tests/test_resume_studio_document.py`

**Interfaces:** `get_or_create_document(db: Session, mission_id: UUID) -> ResumeStudioDocument`, `read_document(row) -> dict`; models `ResumeStudioDocument` with unique `mission_id`, source target ID, revision, language, template, JSON, confirmed revision.

- [ ] Write a failing API/service test with a confirmed TargetResume fixture and a bound Profile. Assert first load imports only accepted/edited bullets, preserves their UUIDs and evidence refs, and second load returns the same document/revision.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/test_resume_studio_document.py -q`; confirm failure is missing Studio behavior.
- [ ] Add the model, Alembic migration, typed document schema, and import service. Use `source_experience_id` to group bullets under entries; preserve source order. Newly generated IDs are UUIDs.
- [ ] Run the focused test, migration upgrade/downgrade in a separate SQLite fixture, and full API suite; commit `feat: add resume studio document`.

### Task 2: Single mutation API, facts, and concurrency

**Files:**
- Modify: `apps/api/app/resume_studio_schemas.py`, `apps/api/app/resume_studio_service.py`
- Create: `apps/api/app/resume_studio_routes.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_studio_mutations.py`

**Interfaces:** `apply_operation(db, mission_id, expected_revision, operation) -> dict`, operations `set_text`, `add_entry`, `add_bullet`, `omit`, `restore`, `move`, `set_template`, `confirm_fact`, `set_language`; `export_checks(document) -> list[dict]`.

- [ ] Write failing tests for text edit, add/delete/restore, same-section ordering, stable IDs, fact filtering, high-risk export blocks, omitted non-blocking, and two clients submitting the same revision (second gets 409 and first survives).
- [ ] Run the focused pytest file and confirm the expected assertions fail.
- [ ] Implement strict Pydantic operation discriminators, server-side node lookup/validation, risk classification, source validation, revision compare-and-swap, and route registration. Never accept client-submitted `risk_level`.
- [ ] Re-run focused and full API tests; commit `feat: add revisioned studio edits`.

### Task 3: Original template catalog and Typst renderer

**Files:**
- Create: `apps/api/app/resume_studio_templates.py`
- Create: `apps/api/app/resume_studio_render.py`
- Create: `apps/api/app/resume_studio_typst/base.typ`
- Create: `apps/api/app/resume_studio_typst/templates.json`
- Create: `docs/licenses/resume-studio-NOTICES.md`
- Test: `apps/api/tests/test_resume_studio_render.py`

**Interfaces:** `list_templates() -> list[dict]`, `render_document(document, template_id) -> RenderResult(pdf: bytes, pages: list[str], layout_map: list[dict], page_count: int)`.

- [ ] Write failing tests asserting exactly 9 `zh` and 9 `en` unique IDs, static valid manifest metadata, and real PDF + all-page SVG output for two different sample documents in each language.
- [ ] Run the focused tests and confirm template/renderer behavior is absent.
- [ ] Implement 9 clearly different original layout configurations with localized Chinese/English manifest entries, escaped Typst generation, source text anchors, CLI timeout and temporary roots, SVG page counting, PDF text extraction, cache keyed by content/template/runtime/fonts, and per-key coalescing. Resolve Typst binary from `TYPST_BIN` or PATH; fail with installation guidance.
- [ ] Pin Typst 0.15.1 in setup docs, record original template copyright and runtime/font licenses in NOTICES. Render all 18 templates using the same full fictitious sample; inspect complete pages and text extraction; commit `feat: render eighteen original typst templates`.

### Task 4: Preview, confirmation, and PDF routes

**Files:**
- Modify: `apps/api/app/resume_studio_routes.py`, `apps/api/app/resume_studio_service.py`
- Test: `apps/api/tests/test_resume_studio_routes.py`

**Interfaces:** `GET /api/v1/job-missions/{id}/resume-studio`, `PATCH` same path, `GET /api/v1/resume-studio/templates`, `POST /api/v1/job-missions/{id}/resume-studio/preview`, `POST .../confirm`, `GET .../pdf`.

- [ ] Write failing route tests for preview metadata/page count, 409 stale revision, confirmed PDF bytes and safe filename, blocked facts, and edit invalidating a prior confirmation.
- [ ] Run focused tests and confirm new route expectations fail.
- [ ] Implement static manifest endpoint, render result serialization, latest revision check, one-to-two-page gate, text-selectability check, `Content-Disposition` download, and recoverable Typst errors.
- [ ] Run focused and full API suites; commit `feat: expose resume studio preview and pdf`.

### Task 5: Web data client and edit history

**Files:**
- Create: `apps/web/app/resume-studio/types.ts`, `apps/web/app/resume-studio/api.ts`, `apps/web/app/resume-studio/history.ts`
- Test: `apps/web/tests/resume-studio.test.mts`

**Interfaces:** `readStudio`, `applyStudioOperation`, `renderStudio`, `confirmStudio`, `downloadStudioPdf`; `StudioHistory` tracks reversible operations without reusing revisions.

- [ ] Write failing Node tests for API URL/body/If-Match, stale 409 payload, history undo/redo, and stable same-document content hash across template changes.
- [ ] Run `node --experimental-strip-types --test tests/resume-studio.test.mts` and confirm failure reflects missing behavior.
- [ ] Implement typed fetch client and pure history logic. Each undo/redo issues an inverse operation against the latest server revision; network errors preserve the local draft.
- [ ] Run the focused test and Web type check; commit `feat: add studio web client`.

### Task 6: Gallery and visual editor

**Files:**
- Create: `apps/web/app/resume-studio/studio-page.tsx`, `apps/web/app/resume-studio/studio.css`
- Create: `apps/web/app/missions/[missionId]/resume/studio/page.tsx`
- Modify: `apps/web/app/mission-page.tsx` (one entry link only)
- Test: `apps/web/tests/resume-studio-ui.test.mts`

**Interfaces:** route receives `missionId`; page state is server document + revision; SVG pages and `layout_map` drive preview click-to-edit; template cards show full sample pages.

- [ ] Write failing UI contract tests for route presence, gallery count, preview click mapping, fact filters, move controls, refresh recovery, and PDF download link.
- [ ] Run focused tests and confirm expected missing UI behavior.
- [ ] Implement gallery, page preview, hotspot overlay, right editor, source drawer, four-state fact filter, add/omit/restore/move, drag and drop with native pointer events, keyboard move, undo/redo, debounce and latest-response guard. Keep CSS scoped to Studio and use approved design tokens.
- [ ] Run focused tests, Web type check, existing suite, desktop/mobile browser exercise; commit `feat: add resume studio workbench`.

### Task 7: Final-resume interview bridge and UI integration

**Files:**
- Modify: `apps/api/app/proof_service.py`
- Modify: `apps/web/app/mission-page.tsx` only if required after UI branch integration
- Test: `apps/api/tests/test_resume_studio_interview.py`

**Interfaces:** `_final_resume_context(mission)` returns confirmed Studio content when `confirmed_revision == revision`, otherwise preserves legacy TargetResume behavior.

- [ ] Write a failing interview test: after Studio confirmation, interview context contains edited Studio bullet and revision; after an unconfirmed edit, it does not treat the edit as confirmed; historic missions retain legacy behavior.
- [ ] Run focused test to verify red, implement the context preference and safe fallback, rerun full API suite.
- [ ] When `aioscaree-UI` commits, merge/rebase its work into this branch, resolve only real overlapping `mission-page.tsx`/CSS changes, run Web and API checks, and commit integration.

### Task 8: End-to-end and release QA

**Files:**
- Create: `docs/superpowers/qa/2026-10-08-resume-studio-qa.md`
- Modify: `README.md`, `docs/licenses/resume-studio-NOTICES.md`
- Test: browser E2E and `apps/api/tests/test_resume_studio_render.py`

- [ ] Exercise two distinct fictitious resumes, Chinese and English, all 18 full-page previews, edit/add/reorder/template swap, four fact filters, 409 conflict, refresh, confirm and download; save desktop/mobile screenshots under `docs/screenshots/resume-studio/`.
- [ ] Extract downloaded PDF text and verify page count and safe filename. Confirm two different documents yield different content and template change preserves node text/IDs.
- [ ] Run `npm test`, `npm run type-check`, `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m compileall -q app`, and `git diff --check`. Record exact counts, remaining limits and asset licenses in QA note.
- [ ] Commit QA/docs/screenshots and leave branch with a clean status; show the user the resulting route, screenshots, commands and any unsupported environment condition.
