# TASK-002.5B — Intended vs Implemented

## Reliability contract

- Raw extracted values, canonical aliases, and the anchored source span are retained on extraction facts.
- Grounding runs before normalization. Canonical values such as `PPT` → `PowerPoint` are accepted only when the raw value or a deterministic alias is present in the source evidence.
- Unsupported items are quarantined with structured warnings. The current conservative threshold rejects an extraction when every top-level fact is unsupported or when more than 25% of top-level facts are rejected; one unsupported item among four valid items is retained as a warning.
- The persisted Profile is created only from grounded facts, so quarantined facts cannot enter the database.

## Section completeness and repair

Recognized non-empty sections include education, campus experience, work/internship experience, skills, courses, credentials, and language ability. A missing normalized section produces `MISSING_SECTION_CONTENT:<SECTION>`.

At most one targeted repair is attempted. It receives only the missing section text, is grounded against that section, and can merge only the category allowed for that section. It cannot rewrite the full extraction or import facts from another section.

## Deterministic normalization

- Explicit `Word`, `Excel`, and `PPT` evidence becomes three atomic skills; generic `办公软件` remains generic.
- Language ability such as `英语读写能力` and `普通话沟通良好` remains a skill.
- Explicit credentials remain certifications. Scores are preserved when explicit, while pass/fail status is never inferred. `CET-6 300` therefore stores name `CET-6`, score `300`, and no inferred status.

## Verification status

- Reliability and persistence regression tests cover grounding, quarantine, section repair, Office atomicity, language/credential separation, and score/status round trips.
- Five equivalent deterministic raw-output variants produce one normalized semantic signature. This is a local repeatability regression, not a live five-run LLM smoke test.
- A live model repeatability evaluation remains environment-dependent and was not invoked without an explicitly configured model/API test environment.
- PostgreSQL migration/integration verification remains a separate environment gate; SQLite is used only for fast local unit/API tests.
