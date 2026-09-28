# Evidence OS Integration

## Role in the product

Evidence OS is **Career Evidence Intelligence**: grounding, provenance, and zero-fabrication gates.

It is **not** a second user-facing job-hunt workflow.

## User path

Primary UX remains **Job Mission**:

Paste JD -> What Matters -> Experience Selection -> Resume Strategy -> Target Resume -> Red Team -> Recover Evidence / Proof Sprint -> Interview -> Outcome.

`/evidence-os` is retained as an **Advanced / Debug** view for inspectors and engineering dogfood.

## Data relationship

| System | Responsibility |
|--------|----------------|
| Profile / ProofArtifact / ResumeClaim | Product source of truth for mission-scoped claims and artifacts |
| `eos_*` tables (migration `011_evidence_os`) | Optional provenance ledger + confirmation workflow |
| `evidence_adapter.py` | Shared gates callable from Mission/Proof without duplicating claim rows |

## Alembic

- Prior head: `010_v02_integrated_job_mission`
- Evidence OS: `011_evidence_os` (`down_revision = 010_v02_integrated_job_mission`)
- Do not reintroduce a second `010_evidence_os` revision.

## Principles enforced

- ZERO FABRICATION
- CONFIRMED ONLY for final resume bullets
- NO FAKE ATS PASS RATES
- Proof task checkbox is not verified evidence
