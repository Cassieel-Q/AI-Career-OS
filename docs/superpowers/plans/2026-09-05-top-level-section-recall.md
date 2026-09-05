# Top-Level Resume Section Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every recognized non-empty top-level Education, Experience, and Skills section is either recovered with grounded facts or reported with a structured partial-result warning.

**Architecture:** Keep the existing source-grounding and bounded hard-fact recovery pipeline. Expand only the explicit heading alias table, then process the initial missing-section list with at most one section-only repair per missing section. Recompute completeness after each repair and convert any unresolved section omission into a structured warning without inventing facts.

**Tech Stack:** FastAPI, Pydantic, pytest, existing structured-output resume provider, SQLAlchemy persistence.

## Global Constraints

- Do not merge `main`.
- Do not start TASK-003.
- Do not change the database schema or add a migration.
- Do not broaden into a soft-skill ontology or a full second-pass reviewer.
- Preserve Office/credential deterministic recovery, credential scores, and CAMPUS classification.
- Keep unsupported facts quarantined and evidence-grounded.

---

### Task 1: Reproduce and trace the section omission paths

**Files:**
- Test: `apps/api/tests/test_resume_reliability.py`
- Inspect: `apps/api/app/resume_sections.py`
- Inspect: `apps/api/app/main.py`

- [ ] **Step 1: Add a failing multi-section repair regression.**

Add a provider whose `extract_section` returns grounded Education, Skills, and Experience facts for the requested section. Call `process_resume_extraction` with a source containing all three recognized sections and an initial result containing only a credential. Assert all three repaired collections are present. The current global `missing[0]` implementation must leave at least one collection empty.

- [ ] **Step 2: Add alias detection regressions.**

Assert `detect_sections` recognizes `学历信息`, `实习/工作经历`, `工作/实习经历`, `项目经历`, `技能特长`, `个人技能`, `职业技能`, `技能证书`, and `核心课程` as their intended section keys. Run the focused tests and record whether the failures come from alias matching or repair sequencing.

- [ ] **Step 3: Add a failed-repair diagnostic regression.**

Use a provider that returns `ResumeExtractionResult()` for a missing Education section while the initial result contains a grounded Skill. Assert processing returns the Skill, keeps Education empty, and includes a structured warning with a section-missing/repair-failed code. This proves unresolved partial extraction is not silently treated as complete.

### Task 2: Expand only the explicit section aliases

**Files:**
- Modify: `apps/api/app/resume_sections.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [ ] **Step 1: Add the requested aliases to `_SECTION_ALIASES`.**

Keep `CAMPUS` separate so `校园经历` continues to classify campus facts. Add `学历信息` to `EDUCATION`; add `实习/工作经历`, `工作/实习经历`, and `项目经历` to `EXPERIENCE`; add `技能特长`, `个人技能`, and `职业技能` to `SKILLS`; add `技能证书` to `CREDENTIALS`; and add `核心课程` to `COURSES`.

- [ ] **Step 2: Run alias tests and the existing section tests.**

Run `..\\.venv\\Scripts\\python.exe -m pytest tests/test_resume_reliability.py -q` from `apps/api`. Confirm aliases pass without changing the section content boundary or the existing CAMPUS behavior.

### Task 3: Repair each missing section once and surface unresolved omissions

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

- [ ] **Step 1: Iterate over the initial missing-section warnings.**

Replace the single `missing[0]` repair with a bounded loop over the initial warnings. Before each call, skip warnings already resolved by a prior repair. Track attempted section keys so one section cannot be requested twice. Pass only that section's `ResumeSection.text` and key to `provider.extract_section`, ground against that section text, merge only the allowed collection, normalize, run existing deterministic recovery, and recompute completeness.

- [ ] **Step 2: Add structured warnings for unresolved sections.**

Keep `SECTION_REPAIR_FAILED` for provider/repair exceptions. After the bounded repair pass, for every remaining completeness warning append a `ValidationWarning` such as `SECTION_CONTENT_MISSING` with the section key, heading/source excerpt, reason `targeted_repair_incomplete`, and source `completeness`. Do not raise solely because a partial result still lacks one section; retain the existing no-grounded-facts 502 for an entirely unusable extraction.

- [ ] **Step 3: Run the repair regressions and existing grounding tests.**

Confirm Education, Skills, and Experience are restored when the section provider returns grounded facts; unsupported repair facts remain quarantined; and an empty/failed repair returns a partial result with a structured warning.

### Task 4: Final verification and delivery

**Files:**
- Update: `docs/review/TASK-002.5D_INTENDED_VS_IMPLEMENTED.md`

- [ ] **Step 1: Run focused backend tests.**

Run `..\\.venv\\Scripts\\python.exe -m pytest tests/test_resume_reliability.py tests/test_resume.py tests/test_resume_normalization.py -q` from `apps/api`.

- [ ] **Step 2: Run the full backend and frontend checks.**

Run backend `..\\.venv\\Scripts\\python.exe -m pytest -q`; frontend `npm test`, `npm run type-check`, and `npm run lint` from `apps/web`. No frontend source change is expected, but the existing regression suite must remain green.

- [ ] **Step 3: Run repository checks and inspect scope.**

Run `git diff --check`, inspect `git status --short --branch`, verify no migration/schema/frontend workflow files changed, and document the exact two root causes plus the unresolved-warning behavior.

- [ ] **Step 4: Commit and push.**

Commit with `fix: stabilize top-level resume section recall` and push only `feature/resume-profile-normalization` without force push or merging `main`.
