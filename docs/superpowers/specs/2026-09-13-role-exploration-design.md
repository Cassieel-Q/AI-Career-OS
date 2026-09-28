# TASK-004 Basic Role Exploration Design

**Status:** Approved for implementation

## Goal

Provide a bounded exploratory comparison of the user's confirmed Profile and
saved Career Preferences against six versioned built-in AI role profiles. The
feature is exploratory guidance, not a claim about live hiring markets and not
the Target Role Selection flow.

## Scope and invariants

- Only the six frozen role codes are valid: `AI_PRODUCT_MANAGER`,
  `AI_APPLICATION_ENGINEER`, `AI_SOLUTION_CONSULTANT`,
  `LLM_ALGORITHM_ENGINEER`, `AI_DATA_ANALYST`, and `AI_PRODUCT_OPERATIONS`.
- Every generated result contains all six roles exactly once. There are no
  percentage, salary, hiring-probability, company-count, or demand-count
  fields.
- `RECOMMENDED`, `POSSIBLE`, and `LOW_PRIORITY` are the only exploration
  levels; at most three roles may be `RECOMMENDED`.
- Evidence references are Profile child-row UUIDs and preference references are
  values from the Profile's two saved, ordered preferences. The application
  rejects references that are missing or belong to another Profile.
- A result is generated only for a `CONFIRMED` Profile with an existing
  Career Preferences row. Neither input is mutated by exploration.
- The UI and API state clearly that the result uses the confirmed Profile,
  saved preferences, and built-in role knowledge; no real JD has been used.

## Approaches considered

1. **Fixed catalog + LLM explanation/ranking + deterministic validation
   (selected).** Code owns the six-role catalog, names, version, completeness,
   reference checks, and safety limits. The OpenAI-compatible provider compares
   supplied facts/preferences to the catalog and returns only strict role
   codes, levels, reasons, concerns, and references.
2. Deterministic scoring with LLM-written explanations. This is predictable but
   hard-codes user matching logic and risks presenting the catalog as a fact
   source, so it is deferred.
3. One-shot unconstrained LLM result with schema-only checks. This is smaller
   but permits role drift and weak evidence traceability, so it is rejected.

## Backend architecture

### Built-in role profiles

`apps/api/app/role_profiles.py` owns immutable, versioned `RoleProfile` values.
Each contains `role_code`, `display_name`, `summary`,
`core_responsibilities`, `key_capabilities`, `coding_intensity`,
`entry_barrier`, `typical_evidence`, and `career_characteristics`. The catalog
has a single `ROLE_PROFILE_VERSION` (initially `v1`) and no market statistics.

### Strict schemas and provider

`apps/api/app/role_exploration_schemas.py` defines strict (`extra="forbid"`)
models for role codes, levels, provider-only output, validated role results,
the request body, and the persisted/read snapshot. Provider output contains no
`role_name`; the application derives that field from the catalog. Reasons and
concerns are bounded string arrays, evidence refs are UUIDs, and preference
refs are the existing `CareerPreferencePriority` enum.

`apps/api/app/role_exploration_provider.py` defines a provider protocol and an
OpenAI-compatible implementation. It reads backend environment variables,
keeps keys server-side, uses the existing JSON-object/deepseek compatibility
pattern, and never changes Resume provider behavior. Its prompt supplies the
confirmed facts by ID, the two saved preferences in order, and the six role
profiles; it forbids new roles, invented facts, percentages, probabilities,
market claims, profile mutations, and raw evidence text in the output.

### Validation and service

`apps/api/app/role_exploration_service.py` loads the Profile and preferences,
builds a copied provider context, calls the provider, then validates the
provider result before any write:

1. exact six-role set and no duplicates;
2. allowed exploration levels and no more than three recommendations;
3. every evidence UUID belongs to one of the current Profile's education,
   skill, experience, or certification rows;
4. every preference ref is one of the current saved priority values;
5. no percentage/probability or unsupported market-claim text;
6. role names/version are filled from the code-owned catalog.

Only the validated JSON representation is persisted. Provider failures, schema
failures, invalid references, and persistence failures map to stable safe HTTP
errors without logging model JSON, profile values, evidence, or secrets.

## Persistence and API

`RoleExploration` is a one-to-one child of `UserProfile` with UUID `id`, unique
`profile_id` foreign key (`ON DELETE CASCADE`), `role_profile_version`, JSON
`result`, `created_at`, and `updated_at`. Migration
`005_role_explorations` follows `004_career_preferences`. A second POST updates
the same row and keeps the latest snapshot; no history table or child tables
are introduced.

- `POST /api/v1/role-explorations` accepts only `{ "profile_id": "<uuid>" }`
  and returns the validated latest snapshot after confirmed-state and
  preference checks.
- `GET /api/v1/profiles/{profile_id}/role-exploration` returns the latest
  snapshot or a clear not-generated response. Stored JSON is validated again on
  read so corruption cannot become a valid business result.

Stable business errors distinguish profile not found (404), unconfirmed
profile or missing preferences (409), provider not configured/persistence
failure (503), provider timeout (504), and invalid provider JSON/schema,
references, or role set (502). No API key or raw upstream response is exposed.

## Frontend architecture

`apps/web/app/role-exploration.ts` owns the read/create request helpers, result
types, Chinese exploration-level labels, readiness checks, and safe API error
handling. `page.tsx` enables the existing next-step button only for a confirmed
Profile with persisted preferences, requests the snapshot, and rehydrates the
latest result after page load. The page renders six simple cards with role
name, exploration level, reasons, concerns, evidence-reference labels, and
preference-reference labels, plus the fixed disclaimer that no real JD has
been used. There is no target-role selection control, JD ingestion, market
profile, or gap-analysis behavior.

## Testing and evaluation

- Backend unit/API tests cover all state gates, strict schemas, six-role
  completeness, duplicate/unknown roles, recommendation limit, invalid levels,
  cross-Profile evidence rejection, invalid preference refs, provider and
  persistence failures, latest-snapshot reads, and unchanged Profile/
  Preferences.
- Migration tests verify `005_role_explorations` and the one-to-one constraint.
- Three fictional evaluation contexts cover product/operations + low-coding/
  fast-employment, Python/development + current-fit, and algorithm/data +
  long-term-growth. They assert structural grounding, fixed roles, valid refs,
  preference participation, and absence of probability precision; they do not
  assert a single “correct” career answer.
- Frontend tests cover readiness gates, request payload/error behavior,
  six-role rendering data, level/reasons/concerns/evidence/disclaimer
  visibility, and rehydration. No real resumes or personal data are used.

## Non-goals

No changes to Resume extraction, Profile confirmation, Career Preferences,
Target Role Selection, JD ingestion, Market Profile, Gap Analysis, historical
exploration versions, pgvector, or frontend API keys.
