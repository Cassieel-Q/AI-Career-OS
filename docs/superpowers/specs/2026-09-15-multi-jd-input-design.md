# TASK-006 Multi-JD Input Design

**Date:** 2026-09-15
**Status:** Frozen for implementation
**Branch:** `feature/multi-jd-input`

## Goal

Collect a bounded set of manually pasted real Job Description samples for the
user's current Target Role. TASK-006 stores raw market evidence only; later
tasks will interpret it.

## Scope and invariants

- A current active Target Role is required before JD input is available.
- One JD is one persisted record with required `raw_text` and optional
  `source_url`.
- An empty collection is allowed before input and after deleting all records.
  A user may save 1–10 active JDs; the third JD reaches the minimum
  needed for future market analysis, while 5–10 is the recommended range.
- The server owns the Target Role relationship. Clients cannot provide or
  override role names, role versions, or exploration snapshot IDs.
- There is one active JD collection, with no history, reassignment, or multiple
  career plans.
- Deleting or replacing the parent Target Role must not leave JDs active for a
  different role. Database cascade handles upstream Target Role invalidation;
  replacement deletes the old parent and its dependent records before the new
  selection can receive JDs.
- Reselecting the same role in the same exploration retains the Target Role ID
  and its samples. Changing role code or snapshot creates a new Target Role ID
  in the same transaction. This prevents requests from old pages writing into
  a newly selected role. The TASK-005 one-active-selection behavior is retained.

## Data model

Add `job_descriptions` through migration `007_job_descriptions`, with
`down_revision = "006_target_roles"`:

- `id` UUID primary key
- `target_role_id` UUID, required foreign key to `target_roles`,
  `ON DELETE CASCADE`
- `raw_text` TEXT, required
- `source_url` TEXT, nullable
- `content_hash` required deterministic SHA-256 digest
- `created_at` and `updated_at` timezone-aware timestamps
- `UNIQUE(target_role_id, content_hash)`

No parsed title, company, skills, location, salary, or normalized requirement
fields are introduced.

## Deterministic duplicate policy

Before hashing, normalize only conservatively:

1. strip leading and trailing whitespace;
2. normalize line endings to LF;
3. collapse whitespace runs to a single ASCII space for hashing only.

Persist and return `raw_text` exactly as supplied. Preserve case, punctuation,
word order and Unicode characters in the hash input; do not apply case folding
or Unicode compatibility normalization. Source URLs do not affect duplication.

Hash the normalized text with SHA-256. Synonyms, fuzzy matching, semantic
similarity, and LLM comparison are explicitly excluded. A duplicate within the
same Target Role returns a deterministic conflict; different normalized text
remains a separate JD.

## API

```text
GET    /api/v1/target-roles/{target_role_id}/job-descriptions
POST   /api/v1/target-roles/{target_role_id}/job-descriptions
PATCH  /api/v1/job-descriptions/{jd_id}
DELETE /api/v1/job-descriptions/{jd_id}
```

- GET returns an array in stable `(created_at, id)` ascending order; an empty
  current collection is `[]`. POST returns 201, PATCH 200, DELETE 204.
- POST requires non-blank `raw_text`, normalizes blank `source_url` to null,
  verifies the Target Role is current, enforces the 10-record maximum, and
  rejects exact duplicates.
- PATCH uses partial-update semantics. An omitted field is unchanged;
  `source_url: null` clears the value; a non-blank string replaces it; an
  empty or whitespace-only `source_url` is defensively normalized to null.
  `raw_text: null`, empty, or whitespace-only values are rejected. A changed
  raw text recomputes `content_hash` and must pass duplicate validation.
- Empty PATCH is a no-op. Non-blank URLs must be HTTP(S) URLs with a host;
  save their trimmed input without fetching them. Read responses include IDs,
  raw text, source URL and timestamps; content hashes remain server-owned.
- DELETE verifies that the JD still belongs to the current active Target Role.
- All mutations verify current ownership from persisted state and never trust
  hidden client state.

Expected error classes follow existing conventions: `404` for missing Target
Role/JD, `409` for stale or non-current state and duplicate/count conflicts,
and `422` for malformed or blank input. The count limit uses `409` because it
depends on persisted collection state. Persistence failures use safe `503`
messages. Serialize writes using the existing Profile-first lock order and
re-read current state after acquiring locks; database uniqueness is the final
duplicate guard. GET also validates the current parent relationship.

## Frontend behavior

After Target Role selection, show the current role and an editable JD section
with count, guidance, add/save/update/delete controls, and a minimum-ready
indicator. No Target Role means no active JD workflow. Refresh loads the saved
collection; target invalidation clears it; a newly selected Target Role starts
empty. The future “分析市场要求” control is visually enabled at 3 or more
JDs but has no TASK-007 navigation or implementation.

## Testing and boundaries

Use synthetic fixtures only. Backend tests cover current-role gates, CRUD,
ordering, hash/duplicate behavior, the 10-record limit, PATCH semantics,
ownership, replacement, and cascade invalidation. Frontend tests cover empty
and populated states, CRUD actions, refresh loading, counts, minimum readiness,
maximum handling, duplicate errors, and Target Role invalidation.

TASK-006 must not call any model provider or implement JD parsing,
normalization/aggregation, Market Profile, Gap Analysis, prioritization,
scraping, semantic deduplication, or TASK-007 behavior.
