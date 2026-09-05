# TASK-002.5D — Intended vs Implemented

## Exact recall root causes

The omission was not caused by Profile serialization or the repair merge dropping valid grounded items. The trace and regression tests identify three application-level causes:

1. `process_resume_extraction` previously selected only `missing[0]`, so a resume with multiple non-empty recognized sections missing from the first-pass result received one targeted repair and silently retained the other section omissions. This matches the smoke pattern where Education plus Skills or Experience were missing together.
2. The section alias table did not recognize several explicit headings, including `学历信息`, `实习/工作经历`, `工作/实习经历`, `项目经历`, `技能特长`, `个人技能`, `职业技能`, `技能证书`, and `核心课程`. For those headings, completeness validation never fired because segmentation produced no section.
3. An empty targeted-repair response left the completeness warning only in the internal list; it did not create a structured extraction diagnostic, so a usable partial Profile could appear to have no missing-section problem.

## Section detection and repair behavior

The alias table now recognizes the requested Education, Experience/Campus/Project, Skills, Credentials, and Courses variants. Existing source segmentation and absolute source spans are preserved. `校园经历` remains the `CAMPUS` subtype while `项目经历` is handled by the general `EXPERIENCE` repair path.

The initial completeness list is processed in a bounded loop. Each missing section can trigger at most one section-only provider call. The provider receives only that section's text; its result is grounded against that same text, merged only into the allowed collection, normalized, and passed through the existing deterministic Office/credential recovery. Completeness is recomputed after each repair, so multiple missing top-level sections can all be recovered without introducing a full second-pass reviewer.

If a repair raises, the existing structured `SECTION_REPAIR_FAILED` warning is retained. If a section remains missing after the bounded repair pass, the processor adds `SECTION_CONTENT_MISSING` with reason `targeted_repair_incomplete`. The partial grounded result is retained; an unresolved section alone does not cause a 502. The existing no-grounded-facts failure remains for an entirely unusable extraction.

Unsupported repair facts are still rejected by section-local grounding and therefore cannot be persisted. Existing Office/credential recovery, credential scores, and CAMPUS classification remain unchanged.

## Schema and migration

No migration was required. This change only adjusts in-memory section detection, bounded repair orchestration, and structured diagnostics; no database schema or Profile persistence contract changed.

## Verification status

Focused section-recall regressions cover multi-section repair, all requested heading aliases, empty repair diagnostics, section-local grounding, unsupported-fact exclusion, and existing hard-fact recovery. Full backend and frontend checks are run before delivery. Live model smoke results are not claimed unless separately executed in the configured model environment.
