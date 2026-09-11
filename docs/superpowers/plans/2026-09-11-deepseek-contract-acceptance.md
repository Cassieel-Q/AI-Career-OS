# DeepSeek Section JSON Contract Acceptance Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DeepSeek section extraction conform to the strict lean Pydantic shapes and expose safe validation diagnostics without changing resume business logic.

**Architecture:** Keep JSON Object transport and the existing `json.loads → model_validate → grounding` boundary. Replace the single ambiguous section prompt suffix with compact contracts selected by section key, and carry only sanitized Pydantic error metadata through `ResumeExtractionFailure` into existing provider logs.

**Tech Stack:** Python, OpenAI-compatible SDK, DeepSeek JSON Output, Pydantic v2, pytest.

## Global Constraints

- Do not change the database, schema, migrations, API, frontend, section planner, extraction architecture, or grounding behavior.
- Keep `extra="forbid"`; never discard unknown model fields before validation.
- Keep source values verbatim and drop only optional fields that fail existing grounding.
- Never log model JSON/content, resume text, evidence text, API keys, or field values.
- Do not merge `main`, start TASK-003, reset data, or force-push.

### Task 1: Add acceptance regressions

**Files:**
- Modify: `apps/api/tests/test_resume.py`
- Existing grounding regressions: `apps/api/tests/test_resume_reliability.py`

- [x] Add tests for exact credential JSON, rejected `status`/`credential_type`, safe validation diagnostics, and the explicit experience optional-field prompt contract.
- [x] Retain tests proving exact optional experience fields pass grounding while paraphrased fields are dropped.
- [x] Run the focused tests and confirm the new cases fail for the ambiguous contract/diagnostic behavior.

### Task 2: Implement section contracts and safe diagnostics

**Files:**
- Modify: `apps/api/app/main.py`

- [x] Replace the generic section contract with per-section JSON examples for education, experience, campus, skills, credentials, and language.
- [x] Add explicit no-extra-key instructions, including no `status` or `credential_type` on `LeanCertification`.
- [x] Require every experience optional field to be independently copied verbatim or returned as `null`.
- [x] Sanitize Pydantic validation loc/type/count metadata and include it with stage and section key in safe diagnostics.
- [x] Run the focused tests and the existing reliability tests until green.

### Task 3: Verify and deliver

**Files:**
- Modify: `docs/superpowers/plans/2026-09-11-deepseek-contract-acceptance.md`

- [x] Run full backend pytest, frontend tests, frontend type-check, frontend lint, and `git diff --check`.
- [x] Inspect the final diff for scope violations and commit with `fix: tighten DeepSeek section JSON contracts`; push the feature branch without force.
- [x] Verify local and remote HEAD match and the worktree is clean.
