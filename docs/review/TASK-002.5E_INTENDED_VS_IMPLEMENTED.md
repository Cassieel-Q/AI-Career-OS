# TASK-002.5E Intended vs Implemented

## Scope

This change hardens recall for explicit, non-empty Education sections only. It does not change the database schema, migrations, Profile API contract, frontend, TASK-003 scope, or the existing Office/credential recovery rules.

## Evidence-based root cause

The pre-change `process_resume_extraction` path had four concrete gaps:

1. `completeness_warnings` detected a missing Education section, but the generic repair loop allowed only one `extract_section` call per missing section. An empty or ungrounded first Education repair therefore ended with the section still missing.
2. `ground_resume_extraction` grounded an Education item through its institution anchor, but did not validate `degree`, `field_of_study`, or `dates` independently. An unsupported optional field could survive, while a later repair could not safely fill a missing optional field.
3. `_dedupe_education` merged only `relevant_courses`. When two grounded records for the same institution contributed different optional fields, the first record won and the later degree/major/date facts were lost.
4. The pipeline emitted only generic section diagnostics, so it did not identify whether Education was empty after the first pass, empty/ungrounded after repair, or unresolved after the bounded repair budget.

The API serialization path was separately exercised with a repaired Education item. The item reached the `POST /api/v1/resumes` response with supported fields intact, so the observed recall loss was in extraction/grounding/merge rather than ORM-to-`ProfileRead` serialization.

## Implemented flow

1. Existing heading detection and completeness checks remain the source of truth for whether an explicit non-empty Education section exists.
2. The first extraction is grounded against the full resume text and normalized as before.
3. If Education remains empty, the pipeline emits a redacted first-pass diagnostic and calls the provider with the Education section only.
4. Education receives at most two section-only repair calls after the first pass. Other sections retain the existing one-repair limit. No full-resume rerun is introduced.
5. Each repair result is grounded against the isolated Education section before merge, then its evidence span is rebased to absolute offsets in the original resume. The Education-specific provider prompt requests only school/institution, degree, major/field-of-study, explicit date text, and relevant courses; it prohibits inference and unrelated sections.
6. Same-institution Education records are deduplicated while retaining the first non-null value for each optional field and the union of grounded courses.
7. If both Education repairs are exhausted, the profile retains other grounded facts and reports `EDUCATION_EXTRACTION_INCOMPLETE` rather than silently treating the explicit section as absent.

## Partial-field and provenance behavior

- Institution remains the primary required Education anchor.
- `degree`, `field_of_study`, and `dates` are retained independently only when each value is explicitly present in the item's grounded evidence anchor. This prevents a matching value in another resume section from being borrowed.
- Unsupported optional values are set to `None` and reported as ordinary `UNSUPPORTED_FACT` warnings; supported Education fields are not discarded.
- `relevant_courses` continues to use the existing evidence-bound grounding rule.
- When merge/dedup fills missing optional fields or courses, the evidence metadata is updated too; when absolute spans are available, the final evidence is the contiguous source span covering the merged facts.
- If a repair evidence anchor cannot be mapped back to the original resume, its offsets are cleared rather than preserving potentially section-relative positions.
- No unsupported fact is synthesized, and no Education diagnostic includes resume excerpts or raw evidence. Stage diagnostics use the constant marker `EDUCATION` and an empty evidence field.

## Structured diagnostics

The Education stage uses redacted `ValidationWarning` records for:

- `EDUCATION_SECTION_NOT_DETECTED`
- `EDUCATION_FIRST_PASS_EMPTY`
- `EDUCATION_REPAIR_EMPTY`
- `EDUCATION_REPAIR_UNGROUNDED`
- `EDUCATION_DROPPED_DURING_NORMALIZATION`
- `EDUCATION_DROPPED_DURING_MERGE`
- `EDUCATION_EXTRACTION_INCOMPLETE`

`EDUCATION_REPAIR_FAILED` is also emitted for a provider exception, with only the exception type as the reason.

## Verification

- Focused backend suites: `85 passed, 6 warnings`.
- Full backend suite: `111 passed, 1 skipped, 6 warnings`.
- Frontend tests: `13 passed`.
- Frontend type-check: passed.
- Frontend lint: passed with no warnings or errors.
- `npm run build`: not completed in this Windows workspace. Next.js first reported `EISDIR` while reading `node_modules/next/dist/pages/_app.js`; after that path was confirmed to be a file, repeated builds stalled without compiler output and were stopped. No application source or tracked generated file was changed by the attempts.
- Live five-run model smoke: not rerun in this coding pass; acceptance of the external model remains a separate smoke-test item.

## Migration and scope

No migration is required. The existing Education schema (`institution`, `degree`, `field_of_study`, `dates`, `relevant_courses`) is unchanged. No main merge and no TASK-003 work are included.
