# Section-First Resume Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make targeted, section-first extraction the normal resume pipeline while preserving the grounded `ResumeExtractionResult` and profile persistence contract.

**Architecture:** Keep PDF extraction, deterministic section detection, grounding, normalization, hard-fact recovery, and profile persistence in their existing modules. Add an internal lean targeted-output schema and a small orchestration layer in `app.main` that calls only recognized non-empty sections, converts lean semantic values into source-anchorable public facts, and runs the existing final grounding/normalization path once. Retain the full provider method only for the no-section compatibility fallback and for legacy providers that expose no section method.

**Tech Stack:** FastAPI, Pydantic v2, OpenAI structured outputs, existing resume section/grounding helpers, pytest, SQLAlchemy profile persistence.

## Global Constraints

- Do not merge `main`.
- Do not start TASK-003.
- Do not change schema, models, migrations, API response contracts, frontend, or database data.
- The normal path for a resume with recognized non-empty sections must not call `provider.extract()` with the full resume.
- Keep `MAX_LLM_CALLS_PER_RESUME = 5` and `OPENAI_MAX_RETRIES` default `0`; do not add automatic section retries.
- Preserve evidence grounding, exact source spans, provenance, Office recovery, credential/score recovery, institution recovery, experience classification, and safe provider failure taxonomy.
- Never log resume text, evidence excerpts, provider bodies, secrets, or raw exception messages.

---

### Task 1: Lock lean targeted output and section planning behavior

**Files:**
- Modify: `apps/api/app/resume_schemas.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_resume_reliability.py`

**Interfaces:**
- Produce internal `LeanResumeExtractionResult` and its lean fact types with semantic fields only; no evidence offsets or provenance fields.
- Produce `build_section_extraction_plan(source_text: str, deterministic: ResumeExtractionResult) -> list[ResumeSection]` (or an equivalent private helper) that returns only recognized, non-empty sections requiring targeted semantic extraction, in stable priority/order and capped at `MAX_LLM_CALLS_PER_RESUME`.

- [x] **Step 1: Add a failing test proving the sectioned path can be planned without a full-resume call.**

```python
def test_section_plan_contains_only_non_empty_supported_sections() -> None:
    source = (
        "教育背景\n北京大学\n\n"
        "工作经历\nBackend Engineer\n\n"
        "专业技能\nPython\n\n"
        "证书\nCET-6 300"
    )

    plan = main.build_section_extraction_plan(source, ResumeExtractionResult())

    assert [(section.key, section.heading) for section in plan] == [
        ("EDUCATION", "教育背景"),
        ("EXPERIENCE", "工作经历"),
        ("SKILLS", "专业技能"),
    ]
    assert all(section.text in source for section in plan)
```

- [x] **Step 2: Run the new test and verify it fails because the planner does not exist.**

Run from `apps/api`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume_reliability.py -k "section_plan_contains_only_non_empty_supported_sections" -q
```

Expected: collection/runtime failure identifying the missing planner.

- [x] **Step 3: Add lean Pydantic output types and the deterministic section planner.**

The lean types contain only semantic fields:

```python
class LeanEducation(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    dates: str | None = None
    relevant_courses: list[str] = Field(default_factory=list)

class LeanSkill(BaseModel):
    name: str

class LeanExperience(BaseModel):
    title: str
    organization: str | None = None
    dates: str | None = None
    description: str | None = None
    experience_type: ExperienceType | None = None

class LeanCertification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None
    score: str | None = None

class LeanResumeExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    education: list[LeanEducation] = Field(default_factory=list)
    skills: list[LeanSkill] = Field(default_factory=list)
    experiences: list[LeanExperience] = Field(default_factory=list)
    certifications: list[LeanCertification] = Field(default_factory=list)
```

The planner starts from `detect_sections(source_text)`, excludes empty
sections, lets deterministic Office/credential recovery cover hard-fact-only
sections, keeps Education/Experience/Campus semantic sections, and preserves
source order while enforcing the five-call cap. It must not append an old
completeness-driven repair plan.

- [x] **Step 4: Run the planner test and the schema tests.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume_reliability.py -k "section_plan_contains_only_non_empty_supported_sections" -q
.\.venv\Scripts\python.exe -m pytest tests\test_resume.py -k "schema or prompt" -q
```

Expected: the planner regression and existing schema/prompt tests pass.

### Task 2: Implement section-local lean conversion and provider calls

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_resume.py`
- Modify: `apps/api/tests/test_resume_reliability.py`

**Interfaces:**
- Produce `_lean_result_to_section_result(lean, section) -> ResumeExtractionResult`, which assigns section-local candidate evidence for grounding, exact `source_section` provenance, and heading-compatible experience metadata.
- Update `OpenAIResumeProvider.extract_section()` to parse `LeanResumeExtractionResult`, while preserving `extract()` as the full-result compatibility method.

- [x] **Step 1: Add failing tests for lean output conversion and full-call avoidance.**

```python
def test_sectioned_resume_does_not_call_full_provider_extract() -> None:
    class SectionOnlyProvider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            raise AssertionError("full resume extraction must not run")

        def extract_section(self, section_text: str, section_label: str) -> object:
            assert section_label == "EDUCATION"
            assert section_text == "教育背景\n北京大学"
            return main.LeanResumeExtractionResult(
                education=[main.LeanEducation(institution="北京大学")]
            )

    processed = main.extract_section_first_resume(
        SectionOnlyProvider(),
        "教育背景\n北京大学",
    )

    assert [item.institution for item in processed.result.education] == ["北京大学"]
    assert processed.total_llm_calls == 1
```

```python
def test_lean_section_values_get_exact_source_backed_spans() -> None:
    source = "教育背景\n北京大学 本科\n\n专业技能\nPython"
    section = main.detect_sections(source)[0]
    result = main._lean_result_to_section_result(
        main.LeanResumeExtractionResult(
            education=[main.LeanEducation(institution="北京大学", degree="本科")]
        ),
        section,
    )

    education = result.education[0]
    assert source[education.evidence_start:education.evidence_end] == education.evidence_text
    assert "Python" not in education.evidence_text
```

- [x] **Step 2: Run the new tests and verify they fail for the current provider/pipeline.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume.py tests\test_resume_reliability.py -k "sectioned_resume_does_not_call_full or lean_section_values" -q
```

Expected: missing helper failures or the current upload path invokes full extraction.

- [x] **Step 3: Implement lean-to-public conversion and section provider parsing.**

Build each public fact with `evidence_text` equal to the supplied section text
as a candidate only; the existing grounding pass must replace it with the
exact source anchor and discard fields that cannot be anchored. Set
`source_section` to the exact detected heading. Set CAMPUS experiences to
`ExperienceType.CAMPUS`; for other experience headings let the existing
heading-based normalization select WORK, INTERNSHIP, or PROJECT and reject
incompatible model values rather than inventing a type.

Change the section OpenAI call to:

```python
response = self.client.beta.chat.completions.parse(
    model=self.model,
    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": section_text}],
    response_format=LeanResumeExtractionResult,
)
parsed = response.choices[0].message.parsed
if parsed is None:
    raise ValueError("OpenAI returned no structured section result")
return LeanResumeExtractionResult.model_validate(parsed)
```

The prompt must say that the model returns semantic values only, does not
provide offsets/canonical aliases/provenance, and must not use text outside
the supplied section. Preserve the existing experience-type and exact-heading
requirements.

- [x] **Step 4: Run conversion, provider prompt, and grounding regressions.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume.py tests\test_resume_reliability.py -k "sectioned_resume or lean_section_values or prompt or grounding" -q
```

Expected: new conversion tests, prompt tests, and existing grounding tests pass.

### Task 3: Integrate the section-first orchestrator, failure isolation, and timing

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_resume.py`
- Modify: `apps/api/tests/test_resume_reliability.py`

**Interfaces:**
- Produce `extract_section_first_resume(provider, source_text, timing_ms=None) -> ProcessedResumeResult`.
- Section failures append a redacted `ValidationWarning` with `code="SECTION_PROVIDER_FAILURE"`, the section category, and one of the existing failure types as `reason`; they do not trigger repair calls.

- [x] **Step 1: Add failing tests for isolated failures, call budget, and timing.**

```python
def test_section_provider_failure_isolated_from_successful_sections() -> None:
    class Provider:
        def extract(self, evidence_text: str) -> object:
            raise AssertionError("sectioned resume must not call full extract")

        def extract_section(self, section_text: str, section_label: str) -> object:
            if section_label == "EDUCATION":
                raise TimeoutError("secret provider body")
            if section_label == "SKILLS":
                return main.LeanResumeExtractionResult(skills=[main.LeanSkill(name="Python")])
            return main.LeanResumeExtractionResult()

    processed = main.extract_section_first_resume(
        Provider(),
        "教育背景\n北京大学\n\n专业技能\nPython",
    )

    assert processed.result.skills[0].name == "Python"
    assert any(
        warning.code == "SECTION_PROVIDER_FAILURE"
        and warning.reason == "timeout"
        for warning in processed.warnings
    )
    assert processed.total_llm_calls == 2

def test_section_first_total_calls_are_bounded() -> None:
    class Provider:
        def extract(self, evidence_text: str) -> object:
            raise AssertionError("full resume call is forbidden")

        def extract_section(self, section_text: str, section_label: str) -> object:
            return main.LeanResumeExtractionResult()

    source = "\n\n".join(
        [
            "教育背景\n北京大学",
            "工作经历\nEngineer",
            "校园经历\nStudent Union",
            "专业技能\nPython",
            "语言能力\nEnglish",
            "证书\nAWS",
        ]
    )
    processed = main.extract_section_first_resume(Provider(), source)

    assert processed.total_llm_calls <= main.MAX_LLM_CALLS_PER_RESUME
```

- [x] **Step 2: Run these tests and verify they fail before orchestration exists.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume_reliability.py -k "section_provider_failure_isolated or section_first_total_calls" -q
```

Expected: missing orchestrator failures.

- [x] **Step 3: Implement the bounded section-first orchestrator.**

The orchestrator must:

1. Detect sections once and obtain an empty deterministic result with
   `recover_explicit_facts(ResumeExtractionResult(), source_text)`.
2. Call each planned section once through `extract_section` when available;
   for legacy providers without that method, call `extract(section.text)` with
   section text only, never the full resume.
3. Convert `LeanResumeExtractionResult` or legacy
   `ResumeExtractionResult` through the section-local adapter.
4. Merge only the collection allowed by the section key.
5. Catch each provider/structured-output failure, construct safe metadata, log
   it with `_log_provider_failure`, append the redacted section warning, and
   continue. Do not call the failed section again.
6. Run `process_resume_extraction(merged, source_text, allow_repair=False,
   initial_llm_calls=call_count, timing_ms=timing_ms)` once at the end so the
   existing grounding, normalization, recovery, completeness diagnostics, and
   no-grounded-facts behavior remain authoritative.

For a source with no recognized non-empty section, call the compatibility
`provider.extract(source_text)` once, process it with `allow_repair=False`, and
retain the `initial_llm_ms` timing field. This is the only full-resume call.

- [x] **Step 4: Replace the upload endpoint's mandatory full call with the orchestrator.**

After `text = extract_pdf_text(data)`, retain provider construction and safe
configuration errors, then call:

```python
processed = extract_section_first_resume(provider, text, timing_ms=timing_ms)
```

Remove the unconditional `provider.extract(text)` block from the normal
upload path. Keep the existing safe outer `ResumeExtractionFailure` handling
and profile persistence unchanged.

- [x] **Step 5: Add section-oriented timing fields without leaking content.**

Add `education_llm_ms`, `experience_llm_ms`, `campus_llm_ms`, and
`other_llm_ms` to `_TIMING_FIELDS` and `_log_resume_timing`. Accumulate elapsed
milliseconds by section category; keep old repair fields at zero for the new
path and preserve `initial_llm_ms` for the no-section fallback. Log only
numeric timings and `total_llm_calls`.

- [x] **Step 6: Run the focused section-first suite.**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_resume.py tests\test_resume_reliability.py -k "section or provider or extraction or timing or office or credential or institution" -q
```

Expected: all section-first, failure taxonomy, grounding, hard-fact, and institution tests pass.

### Task 4: Preserve existing contracts and complete verification

**Files:**
- Modify: `apps/api/tests/test_resume.py`
- Modify: `apps/api/tests/test_resume_reliability.py`
- Modify: `apps/api/tests/conftest.py` only if a fixture needs the new section provider method
- Inspect: `apps/api/app/profile_service.py`, `apps/api/app/profile_schemas.py`, `apps/api/app/models.py`

- [x] **Step 1: Update only test doubles whose source is now intentionally sectioned.**

Keep unheaded source tests on the explicit no-section compatibility fallback.
For sectioned tests, add `extract_section` responses and assert the received
text equals the expected section text. Do not weaken any evidence or Pydantic
assertions.

- [x] **Step 2: Run the complete backend and frontend gates.**

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest -q
cd ..\web
npm test -- --runInBand
npm run type-check
npm run lint
npm run build
cd ..\..
git diff --check
git status --short --branch
```

Expected: backend tests pass with the existing integration skip behavior,
frontend tests/type-check/lint/build pass, diff check is clean, and no schema,
migration, frontend, or database files are changed.

- [x] **Step 3: Run a final scope audit.**

```powershell
git diff --name-only 570403d..HEAD
git diff --stat 570403d..HEAD
rg -n "provider\.extract\(text\)|extract\(source_text\)" apps/api/app/main.py
```

Confirm the only source-text full call is the explicit no-section fallback,
the normal sectioned path uses `extract_section`, and no public profile/API or
database contract changed.

- [x] **Step 4: Commit and push without merging main.**

```powershell
git add apps/api/app/main.py apps/api/app/resume_schemas.py apps/api/tests/test_resume.py apps/api/tests/test_resume_reliability.py docs/superpowers/plans/2026-09-06-section-first-resume-extraction.md
git commit -m "refactor: use section-first resume extraction"
git push origin feature/resume-profile-normalization
```

Record the new commit SHA and push result. Do not force-push or merge `main`.
