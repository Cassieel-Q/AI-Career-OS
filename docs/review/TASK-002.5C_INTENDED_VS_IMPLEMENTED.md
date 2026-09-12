# TASK-002.5C — Intended vs Implemented

## Item-level grounding

The previous 502 path was `_raise_if_unreliable`: it counted quarantined top-level facts and raised `unsupported_item_threshold` when rejected facts exceeded 25%. That made one unsupported item fatal for a small extraction. The implementation now keeps `ValidationWarning(code="UNSUPPORTED_FACT")`, drops the unsupported item, and continues whenever at least one grounded fact remains. A 502 is retained for an extraction with no usable grounded facts; the existing diagnostic detail remains safe and does not expose model output.

The persisted draft is created from the grounded/normalized result only, so rejected skills, certifications, and experiences do not enter the Profile.

## Deterministic explicit recovery

After grounding and normalization, a bounded source-text recovery pass scans recognized `SKILLS`, `CREDENTIALS`, and `LANGUAGE` sections. It recovers only the explicit Office aliases `Word`, `Excel`, `PPT` → `PowerPoint`, `PowerPoint`, and `Microsoft PowerPoint`, plus the supported explicit credential vocabulary. Each recovered item stores the exact matched source substring and absolute `evidence_start`/`evidence_end` offsets. No source token means no recovered fact.

Explicit adjacent scores such as `CET-4 500` and `CET-6 300` are preserved as scores. The recovery pass does not assign pass/fail status. `办公软件` and `办公技能` are removed only when atomic Office tokens are recovered; a source containing only `办公软件` remains generic. Soft-skill labels are not expanded into an ontology.

## Schema and migration

No migration was required. The behavior uses existing Profile child provenance, score, and status fields; no schema, API contract, or TASK-002 confirmation workflow was changed.

## Verification status

- Focused reliability, resume, and normalization tests cover item quarantine, persistence exclusion, Office aliases, umbrella suppression, explicit credentials, scores/status, and source spans.
- Full backend pytest, frontend checks, and `git diff --check` are run before delivery.
- Live five-run model acceptance is environment-dependent and is not claimed unless an explicitly configured model/API smoke environment is available.
