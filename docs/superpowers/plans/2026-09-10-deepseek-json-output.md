# DeepSeek JSON Output Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace unsupported Pydantic structured-output calls with DeepSeek-compatible JSON Object responses while preserving the existing resume schemas, grounding, normalization, persistence, and failure taxonomy.

**Architecture:** Keep `OpenAIResumeProvider` as the environment-configured OpenAI-compatible adapter. Both full-resume and section extraction calls will use `client.chat.completions.create(response_format={"type": "json_object"})`; a small private response helper will parse JSON and validate the caller's Pydantic model before the existing extraction pipeline receives it. DeepSeek endpoints receive the provider-specific disabled-thinking request option, while other compatible endpoints keep the standard request shape.

**Tech Stack:** Python, OpenAI-compatible SDK, DeepSeek JSON Output, Pydantic v2, pytest.

## Global Constraints

- Do not modify the public resume schema, database schema, migrations, API contract, frontend, or Education/Experience/Grounding logic.
- Keep `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` environment variable names.
- Validate every model response through `json.loads` followed by the appropriate Pydantic model.
- Map invalid JSON and schema-invalid JSON to `structured_output_validation` without logging model output or resume text.
- Add no database migration and do not use the real application database for tests.
- Do not merge `main`, start TASK-003, force-push, or weaken validation.

### Task 1: Add failing provider adapter regressions

**Files:**
- Modify: `apps/api/tests/test_resume.py`

**Interfaces:**
- The fake OpenAI client exposes `chat.completions.create` and returns `choices[0].message.content` as a JSON string.
- `OpenAIResumeProvider.extract()` returns `ResumeExtractionResult` and `extract_section()` returns `LeanResumeExtractionResult` after validation.

- [x] **Step 1: Write the failing tests**

Add fake JSON Object responses and assertions for full and section extraction, invalid JSON, schema-invalid JSON, DeepSeek request options, and unchanged timeout/connection classification. Update prompt tests to capture `chat.completions.create`.

- [x] **Step 2: Run the focused tests and verify the expected failure**

Run from `apps/api`:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_resume.py -q
```

Expected: the new adapter tests fail because the provider currently calls `beta.chat.completions.parse` and expects `.parsed` instead of JSON content.

### Task 2: Implement the minimal DeepSeek JSON adapter

**Files:**
- Modify: `apps/api/app/main.py`

**Interfaces:**
- Add a private JSON response helper that accepts a response and a Pydantic model type and returns the validated model.
- Add a private request helper that calls `client.chat.completions.create` with JSON Object response format and provider-specific DeepSeek options.

- [x] **Step 1: Implement JSON response parsing and validation**

Read `response.choices[0].message.content`, reject missing/non-string content, call `json.loads`, and call `model_validate`. Do not log content or source text.

- [x] **Step 2: Replace both provider parse calls**

Use the JSON request helper for `extract()` and `extract_section()`. Keep the existing prompts and append concise JSON-only/top-level-array contracts. Add `extra_body={"thinking": {"type": "disabled"}}` only when `OPENAI_BASE_URL` resolves to a DeepSeek host.

- [x] **Step 3: Run the focused tests and verify the green result**

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_resume.py tests/test_resume_reliability.py -q
```

Expected: all provider and existing resume reliability tests pass, including structured-output failure handling.

### Task 3: Complete verification and delivery

**Files:**
- Modify: `docs/superpowers/plans/2026-09-10-deepseek-json-output.md`

- [x] **Step 1: Run backend and repository checks**

```powershell
..\\.venv\\Scripts\\python.exe -m pytest -q
npm --prefix apps/web test
npm --prefix apps/web run type-check
npm --prefix apps/web run lint
git diff --check
```

Expected: backend and frontend tests/checks pass; if the known Windows/Next dependency-tree build issue recurs, report it as unverified rather than claiming build success.

- [x] **Step 2: Review the diff and commit**

```powershell
git diff -- apps/api/app/main.py apps/api/tests/test_resume.py docs/superpowers/plans/2026-09-10-deepseek-json-output.md
git status --short
git add apps/api/app/main.py apps/api/tests/test_resume.py docs/superpowers/plans/2026-09-10-deepseek-json-output.md
git commit -m "fix: support DeepSeek JSON output"
```

- [x] **Step 3: Push and verify the remote branch**

```powershell
git push origin feature/resume-profile-normalization
git status --short --branch
git rev-parse HEAD
git rev-parse origin/feature/resume-profile-normalization
```

Expected: push succeeds, local and remote commits match, and the worktree is clean.
