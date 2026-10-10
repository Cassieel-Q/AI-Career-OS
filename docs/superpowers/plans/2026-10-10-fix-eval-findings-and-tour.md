# AI Career OS Evaluation Findings Fixes and Project Tour Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the product risks exposed by the 2026-10-09 synthetic/public live evaluation, verify the fixes with regression tests and a fresh browser run, update the Project Tour with evidence from the current product, and publish the verified branch to GitHub.

**Architecture:** Keep the mission workflow and existing provider boundaries. Add deterministic normalization and evidence gates at the API boundary, where model output is already parsed and the final resume/interview context is assembled. Keep Resume Studio as the delivery source of truth; the older mission preview will be explicitly labeled as source-archive guidance. Use repository-relative, redacted screenshots from a fresh local browser run for the Project Tour.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Next.js 15, TypeScript, Python pytest, Playwright/browser automation, Typst PDF rendering, Git/GitHub.

## Global Constraints

- Do not modify production data, real resumes, API keys, or the user's dirty main checkout.
- Work only in the existing linked worktree `G:\myself\ai-career\.worktrees\aioscareer-combine` on `feature/eval-benchmark-v1`.
- Synthetic/public evaluation numbers remain explicitly labeled; do not claim real-user or consented-real quality.
- Product text and reference answers must not invent candidate actions, metrics, employers, or tools.
- Every behavior change gets a failing test before implementation and a fresh targeted/full verification after implementation.
- Project Tour media must be generated from this current branch and contain no private candidate data.
- Push only after tests, browser evidence, diff review, and Git status are verified.

---

### Task 1: Freeze the evidence baseline and add regression tests

**Files:**
- Read: `docs/evaluation/2026-10-09-问题汇总.md`, `docs/evaluation/product-risk-acceptance.md`, `docs/evaluation/findings-and-backlog.md`
- Modify: `apps/api/tests/test_mission_provider.py`, `apps/api/tests/test_interview_provider.py`, `apps/api/tests/test_interview_pack_intel.py`, `apps/web/app/export-resume-checks.test.mts` (or the existing matching web test file)

**Interfaces:**
- Tests target the current public helpers and provider outputs; no test should depend on an external provider.

- [ ] **Step 1: Record each reproducer and expected behavior**

  Add tests for: cashier/barista/courier service work being `OMIT` for a product/technical JD; a high-signal product/project experience not being silently converted from `OMIT` when deterministic evidence is strong; Chinese `本科/本科及以上/硕士` appearing in parsed JD requirements; interview intel integration omitting synthetic/demo records and internal `CURATED` tags; reference answers with unsupported numeric/action claims being gated; and source-archive checks being distinguishable from Studio delivery checks.

- [ ] **Step 2: Run the new tests before implementation**

  From `apps/api`: `python -m pytest tests/test_mission_provider.py tests/test_interview_provider.py tests/test_interview_pack_intel.py -q`.
  From `apps/web`: `npm test -- --test-name-pattern="export|checklist"` or the closest existing focused command.
  Expected: new behavior tests fail for the product gaps, not because of import or fixture errors.

### Task 2: Add deterministic JD education recovery

**Files:**
- Modify: `apps/api/app/mission_schemas.py`, `apps/api/app/mission_provider.py`
- Test: `apps/api/tests/test_mission_provider.py`

**Interfaces:**
- `JobExtractionPayload` gains a backward-compatible `education_requirements: list[str]` field.
- `OpenAIMissionProvider._enrich_job_extraction(raw_text, extraction)` returns education evidence copied from the JD when the provider omitted it.

- [ ] **Step 1: Add a schema field without a migration**

  Add `education_requirements` with a bounded list and include it in the extraction prompt/output normalization. Existing stored JSON remains valid because the field defaults to an empty list.

- [ ] **Step 2: Implement source-text recovery**

  Detect explicit Chinese and English degree phrases (`本科`, `本科及以上`, `学士`, `硕士`, `博士`, `Bachelor`, `Master`, `PhD`) only when present in `raw_text`. Preserve the shortest exact source phrase. If an existing requirement/preferred requirement already contains the degree, do not duplicate it. Add a grounded requirement with `category="education"` and the exact source phrase when needed so the live evaluator and downstream What Matters see the same evidence.

- [ ] **Step 3: Run focused JD tests and the benchmark smoke**

  `python -m pytest tests/test_mission_provider.py tests/test_jd_analysis_provider.py -q` and `python -m evals.benchmark.run --suite jd --mode offline`.

### Task 3: Calibrate experience selection at the provider boundary

**Files:**
- Modify: `apps/api/app/mission_provider.py`
- Test: `apps/api/tests/test_mission_provider.py`

**Interfaces:**
- `_heuristic_experience_decision` remains the deterministic fallback/guardrail and returns the existing `(decision, why, highlights, confidence)` tuple.
- `select_experiences` applies a deterministic floor to model rows after schema normalization and before persistence.

- [ ] **Step 1: Encode negative and positive evidence categories**

  Add service-role markers for cashier, barista, waiter, delivery/courier, retail, restaurant and similar routine service work. For a product/technical target with no product/technical evidence, classify these as `OMIT`. Add product/project markers for creator work, A/B tests, content/product experiments, research, models, data, evaluation and shipped prototypes. Give a high-signal project/research fact a conservative high confidence only when the source text contains those markers.

- [ ] **Step 2: Protect high-signal experiences from an LLM `OMIT`**

  When the deterministic evidence floor is high and the fact is a project/research/product/technical experience, upgrade an LLM `OMIT` to `KEEP_AND_HIGHLIGHT` with an evidence-grounded Chinese reason. Do not upgrade generic work or a service role merely because it has a title.

- [ ] **Step 3: Preserve decision/why consistency**

  Run `_align_experience_why` after every guardrail change. The final payload must never contain `OMIT` with “建议保留/重点展示” language.

- [ ] **Step 4: Run match regressions**

  `python -m pytest tests/test_mission_provider.py tests/test_experience_omit_why.py -q` and `python -m evals.benchmark.run --suite match --mode offline`.

### Task 4: Wire honest interview intel and fact-safe reference answers

**Files:**
- Modify: `apps/api/app/mission_provider.py`, `apps/api/app/interview_provider.py`
- Test: `apps/api/tests/test_interview_pack_intel.py`, `apps/api/tests/test_interview_provider.py`, add an integration test beside the existing interview pack tests if needed

**Interfaces:**
- `interview_pack_intel.annotate_topics(topics, interview_intel, company=...)` becomes the final enrichment pass for mission interview topics.
- Add a pure helper in `interview_provider.py` that receives a reference answer plus `target_job`, `claim`, and `evidence`, returning either the grounded answer or an explicit evidence-insufficient message.

- [ ] **Step 1: Wire `annotate_topics` after topic enrichment**

  Pass the current company and the bounded intel records. Ensure `skill_id` and `source_refs` are honored, synthetic/demo rows are excluded, cross-company rows are labeled as role-family references, and importer headers/internal `CURATED` markers are absent from topic text and evidence bullets.

- [ ] **Step 2: Add the reference-answer evidence gate**

  Build a grounding blob only from confirmed final-resume text, supplied evidence values, and the claim. If the answer contains a numeric token or a high-risk action phrase absent from that blob (for example “采访/访谈创作者” when the fact only says “分析 50 篇内容”), replace the answer with an explicit evidence-insufficient notice and append a weak-point/recommended-action note. If no grounding context is supplied in a standalone provider unit test, preserve current behavior so the unit remains a transport test rather than a product claim.

- [ ] **Step 3: Run interview regressions**

  `python -m pytest tests/test_interview_pack_intel.py tests/test_interview_provider.py tests/test_interview_sessions.py -q`.

### Task 5: Make Studio the delivery source of truth in the mission UI

**Files:**
- Modify: `apps/web/app/export-resume-checks.ts`, `apps/web/app/mission-page.tsx`
- Test: existing web export/checklist tests; add a focused test if no coverage exists

**Interfaces:**
- `buildPreExportChecklist` accepts an explicit option such as `includeContactWarnings?: boolean` with the current default preserved for legacy callers.
- The mission page’s “来源档案检查” passes `includeContactWarnings: false` and clearly states that Studio’s current confirmed revision controls the deliverable PDF.

- [ ] **Step 1: Write the failing web test**

  Assert that source-archive contact gaps are not presented as a delivery blocker on the mission page when Studio owns the final document; direct checklist callers can still request contact warnings.

- [ ] **Step 2: Implement the source-vs-delivery boundary**

  Keep archive checks for traceability, but remove their ability to imply the Studio PDF is missing a contact field. Use copy that names the source archive and directs the user to `/missions/{missionId}/resume/studio` for final contact/事实核对.

- [ ] **Step 3: Run web verification**

  `npm test`, `npm run type-check`, and `npm run build` from `apps/web`.

### Task 6: Fresh browser evidence and Project Tour update

**Files:**
- Modify: `README.md`
- Create/update: `docs/screenshots/project-tour-2026-10-10/`, `docs/evaluation/e2e-2026-10-10/README.md`, `docs/evaluation/e2e-2026-10-10/` redacted report/evidence

**Interfaces:**
- Use the real local app at `http://localhost:3001` or the current worktree service URL, not static mock HTML.

- [ ] **Step 1: Start the API/Web services for this worktree**

  Use an isolated SQLite runtime DB and configured local provider/Typst path. Record exact ports, commit, and sample class. Never include `.env`, raw resume text, or API responses with personal data.

- [ ] **Step 2: Capture one complete current-path run**

  Test `/missions` → JD → role correction → resume source → selection → target resume → Studio → fact confirm → PDF download → interview preview/answer/review → `/interview-records`. Capture screenshots for each stable stage, including compact skills, multi-point project rendering, fact gate and PDF result. If browser recording is available, save a short real run video; otherwise use the fresh screenshot set and state that no video was captured.

- [ ] **Step 3: Replace stale tour references**

  Update README tour copy and image paths to the fresh set. Distinguish current `/missions` routes from legacy `/workflow`/`/proof` compatibility routes. Add an evidence note linking the run report and commit.

### Task 7: Full verification, commit, and GitHub publication

**Files:**
- Modify: `docs/evaluation/product-risk-acceptance.md`, `docs/evaluation/findings-and-backlog.md`, `00-当前状态.md` only with verified results

- [ ] **Step 1: Run the full gates**

  API: focused tests, then `python -m pytest tests -q` and `python -m compileall -q app`.
  Web: `npm test`, `npm run type-check`, `npm run build`.
  Eval: `python -m evals.benchmark.validate`, offline suites, and a live smoke only if the configured provider is available. Keep pre-existing failures named and separate.

- [ ] **Step 2: Inspect evidence and Git diff**

  Run `git diff --check`, inspect changed files, confirm no runtime/private files are tracked, review screenshot dimensions/legibility, and compare the report against the actual run output.

- [ ] **Step 3: Update risk status honestly**

  Mark each RISK-ACC item `Fixed`, `Partial`, or `Open` only from fresh evidence. Do not mark reference-answer safety or real-user usability fixed from unit tests alone.

- [ ] **Step 4: Commit and push**

  Commit with a descriptive message, push `feature/eval-benchmark-v1` (or the exact current branch) to `origin`, verify the remote commit with `git ls-remote`, and return the GitHub branch/commit URL. Do not force-push or overwrite `main`.
