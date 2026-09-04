# TASK-002.5 — Intended vs Implemented

## Intended behavior

- Extract explicit resume facts with section-aware structure.
- Normalize only deterministic patterns, while preserving evidence provenance.
- Persist the normalized Draft Profile using the PostgreSQL-first schema.
- Regression-test repeated extraction patterns with at least three fictional Golden Resumes.

## Implemented behavior

- `Education.relevant_courses` and `Experience.experience_type` are present in extraction, API read/write schemas, SQLAlchemy models, and Alembic revision `002_add_profile_normalization_fields`.
- The extraction prompt maps resume sections to the normalized taxonomy and keeps language ability separate from explicit credentials.
- Office aliases are deterministically canonicalized to `Word`, `Excel`, and `PowerPoint`; known bundles are split only when every segment is a supported Office alias.
- Language credentials are canonicalized and kept in certifications; generic language ability is kept in skills. Canonical items retain the original evidence excerpt and are validated against source text, including supported aliases.
- Three Golden Resume fixtures cover Office bundles, education/courses, campus/internship sections, language ability, and explicit credentials. Metrics tracked are extraction recall, classification consistency, normalization consistency, and hallucinated fact count.

## AI reviewer decision

The narrow AI reviewer is not justified by the current Golden Set: all three fixtures normalize with `1.0` recall/classification/normalization consistency and `0` hallucinated facts. No second LLM pass was added.

## Remaining verification

- SQLite-backed unit and API tests pass for fast feedback.
- PostgreSQL migration SQL was generated and inspected. A live PostgreSQL integration run remains environment-dependent and should be executed against the configured test database before production rollout.
