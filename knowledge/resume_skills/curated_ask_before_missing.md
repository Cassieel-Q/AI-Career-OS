---
id: CURATED_RESUME_ASK_BEFORE_MISSING
kind: resume_skill
name: Ask before filling missing evidence
version: 1.0.0
provenance: CURATED_RESEARCH
source_refs:
  - aicareer-profiles/07-careeros-boundaries.md (B2)
  - aicareer-profiles/phase3/skills/match-and-gap (excavation mechanism)
competencies: [grounding, honesty]
---

# Ask before missing

## Intent
When a JD requirement has no matching evidence, ask the candidate—never invent coverage.

## Rules
1. Coverage states: `covered` | `weak` | `missing` | `not_applicable` | `needs_excavation`.
2. For `weak` / `needs_excavation`, emit ≤8 high-value excavation questions; allow「不知道」→ qualitative-specific wording.
3. Do not auto-insert metrics, tools, employers, or ownership to close gaps.
4. Ambitious positioning must list `ambitious_evidence_gaps` instead of fabricating support.

## Failure modes
- Model "helps" by guessing a percentage → gate as fabricated metric.
- Gap silently disappears in Target Resume → isolation/eval fail.
