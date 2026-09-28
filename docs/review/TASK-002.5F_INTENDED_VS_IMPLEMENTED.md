# TASK-002.5F Intended vs Implemented

## Scope

This change stays on `feature/resume-profile-normalization`. It does not change
the schema, ORM models, Alembic migrations, API response contracts, frontend,
profile persistence semantics, or TASK-003 scope.

## Exact institution failure root cause

The Education primary fact is `Education.institution`, and the grounding path
uses that primary value together with the model's `evidence_text` to build the
source anchor. If the model omits the Education item, rewrites the institution,
or returns evidence that does not contain the institution, the primary anchor
cannot be built and the complete Education item is rejected. Optional degree,
major, date, and course values therefore become unusable even when some of
them are present in the source.

Section detection was not the limiting path for the observed failures: the
existing detector already recognizes the Education aliases and bounds the
section before grounding. The missing behavior was a section-local deterministic
fallback after grounding/normalization and before the Education repair call.

The strict extraction contract still requires `Education.institution`. An
Education object whose institution property is absent is rejected by Pydantic
before application-level recovery; that validation is intentionally preserved.
The recovery path handles the observed equivalent failure modes—an omitted
Education item or an item whose institution/evidence cannot be grounded—without
manufacturing a placeholder field or weakening the contract.

The latency trace also found that the installed OpenAI SDK's defaults were a
600-second read/write timeout with two automatic retries. That permits a
single provider operation to occupy several minutes before the application can
surface a failure. The previous repair loop also had no per-resume global call
budget.

## Implemented behavior

- A non-empty, recognized Education section is scanned only within its exact
  source bounds.
- Chinese candidates must end in `大学`, `学院`, `职业技术学院`, `学校`, or
  `研究院`; English candidates must contain a non-bare `University`, `College`,
  `Institute`, or `School` form.
- Context markers such as `毕业于` and `graduated from` are removed only from
  the candidate boundary; the returned institution remains the exact source
  substring with absolute source offsets.
- Exactly one distinct candidate is recovered. Multiple candidates produce
  `INSTITUTION_RECOVERY_AMBIGUOUS` and no deterministic choice is made.
- A recovered institution is merged with optional Education fields only when
  each value and its verbatim evidence can independently be anchored inside
  the Education section. Unsupported values remain absent.
- Deterministic recovery runs before Education-only repair, so an explicit
  school token does not consume another LLM call. The existing Education repair
  allowance remains at two attempts for unresolved cases.
- Institution diagnostics are redacted markers: `INSTITUTION_NOT_EXTRACTED`,
  `INSTITUTION_NOT_GROUNDED`, `INSTITUTION_RECOVERED`, and
  `INSTITUTION_RECOVERY_AMBIGUOUS`.

## Latency and call budget

- `OPENAI_TIMEOUT_SECONDS` defaults to `30` seconds and is bounded to
  `(0, 120]`.
- `OPENAI_MAX_RETRIES` defaults to `0` and is bounded to `0..2`.
- The application-level extraction budget is five logical LLM operations per
  resume: one initial full extraction plus at most four section repairs.
  Repairs remain ordered from Education to Campus/Experience and then other
  missing sections; unresolved sections emit a redacted budget warning when
  the cap is reached. `OPENAI_MAX_RETRIES` applies only to the bounded provider
  transport retry policy and does not create additional section-repair
  scheduling; with the default `0`, the five-operation budget is also five
  provider requests. An explicit retry override remains bounded to at most
  three attempts for an individual provider operation.
- Upload timing logs contain only numeric timings, field names, and the LLM
  call count: `pdf_extract_ms`, `initial_llm_ms`,
  `education_repair_1_ms`, `education_repair_2_ms`,
  `other_section_repair_ms`, `grounding_normalization_ms`, `db_persist_ms`,
  `total_resume_ms`, and `total_llm_calls`.
- Warning logging no longer serializes raw values or evidence excerpts.

## Verification record

- Focused backend tests: 106 passed.
- Full backend pytest: 139 passed, 1 skipped.
- Frontend source was not touched; type-check and lint passed as repository gates.
- `git diff --check` passed; the only Git output was the existing Windows
  LF/CRLF normalization warning.
- No migration was required.
- Live provider/browser smoke was not rerun in this change; PostgreSQL data was
  not modified.
