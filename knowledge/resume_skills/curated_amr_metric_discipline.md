---
id: CURATED_RESUME_AMR_METRIC_DISCIPLINE
kind: resume_skill
name: AMR metric discipline (Ask → Measure/evidence → Record)
version: 1.0.0
provenance: CURATED_RESEARCH
source_refs:
  - aicareer-profiles/07-careeros-boundaries.md (B1/B2)
  - aicareer-profiles/phase3/evals E01–E02
competencies: [grounding, honesty]
---

# AMR — Ask → Measure/evidence → Record

## Intent
AMR is the product shorthand for metric discipline: **Ask** the candidate for the real number or baseline, require **Measure/evidence** (source-backed), then **Record** only confirmed metrics. Never estimate.

## Rules
1. `is_estimate` must stay false; estimates are blocked (`METRIC_ESTIMATE_FORBIDDEN`).
2. Metrics need confirmed source linkage before final bullets.
3. If the user says「你就按大概 30% 写」, refuse and offer qualitative-specific alternatives.
4. ATS / quality scores are heuristic labels only—no fake pass probabilities.

## Failure modes
- Draft contains invented `35%` / `大概20%` → eval gate fail.
- Confirmed-only final render includes pending metric claims → blocked.
