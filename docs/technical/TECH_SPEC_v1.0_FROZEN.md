# AI Career OS — TECH_SPEC v1.0 FROZEN

**Status:** FINAL / TECH GATE PASSED  
**Freeze Date:** 2026-09-03

## 1. Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js + TypeScript |
| UI | Tailwind CSS |
| Backend | FastAPI + Python |
| Validation | Pydantic |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migration | Alembic |
| LLM | OpenAI API |
| LLM contract | Structured Outputs |
| PDF | PyMuPDF |
| Vector retrieval | pgvector |
| Auth | Supabase Auth |
| Local infra | Docker Compose |
| Frontend deploy | Vercel |
| Backend deploy | Railway |
| Testing | pytest + limited E2E |
| Agent framework | None for MVP |

## 2. Architecture

```text
Browser
  ↓
Next.js
  ↓ HTTP/JSON API Contract
FastAPI
  ├─ Business Rules
  ├─ OpenAI Structured Output
  ├─ PostgreSQL
  └─ Evidence RAG (pgvector)
```

Architecture style: **Modular Monolith**

## 3. AI Boundary

LLM:
- resume semantic extraction
- JD semantic extraction
- gap reasoning
- explanation
- roadmap/task generation
- replan
- grounded evidence answer

Deterministic code:
- validation
- frequency counting
- state transitions
- priority scoring
- persistence
- permissions
- task status
- sample-size logic

## 4. Structured vs Retrieval

### Structured path
Resume/JD → extraction schema → validation → relational data

### Retrieval path
Unstructured evidence → chunk → embedding → pgvector → top-k evidence

RAG does not replace relational queries.

## 5. Core data model

Core domains:
- User/Profile/Skill
- CareerPlan/RoleProfile
- JobDescription/MarketProfile
- Gap/Evidence
- Roadmap/Task/Progress
- Document/DocumentChunk

Key rules:
- Profile ≠ CareerPlan
- raw JD preserved
- MarketProfile versioned/snapshotted
- system_priority ≠ user_priority
- Task complete ≠ Skill mastered

## 6. API Contract

Base prefix: `/api/v1`

Core flow:
- resume upload
- profile confirm
- preferences
- role exploration
- career plan
- JD import
- market profile
- gap analysis
- priority override
- roadmap
- task update
- replan
- dashboard

Frontend never depends on LLM free-form output.

## 7. Structured Output Schemas

Required schemas:
- ResumeExtractionResult
- JDExtractionResult
- GapAnalysisResult
- RoadmapGenerationResult
- ReplanResult

All LLM outputs must pass Pydantic Validation before persistence.

## 8. Priority Scoring

Ranking uses:
- role importance
- gap severity
- deadline urgency
- effort level

Rules rank; LLM explains.

Structural constraints are handled separately and do not become ordinary learning tasks.

## 9. RAG defaults

- semantic/natural-section chunks
- ~400–700 tokens
- ~80 token overlap
- top_k = 5 baseline
- metadata filtering
- pgvector
- no reranker/hybrid retrieval in v1

Parameters are tuned through Eval, not treated as universal truths.

## 10. Error / Retry

- input error → 4xx, no LLM call
- schema failure → retry once
- provider transient failure → retry up to twice
- invalid state transition → 409
- no invalid AI result written as valid state

## 11. Test & Eval

Software:
- unit
- integration
- one core E2E happy path

AI:
- extraction accuracy
- normalization consistency
- evidence support
- gap relevance
- roadmap feasibility
- RAG retrieval / groundedness

Maintain a small Golden Set for regression.

## 12. Security

- OpenAI key backend-only
- `.env` ignored
- auth via Supabase Auth
- validate file type/size
- no secrets in frontend or Git

## 13. Development rule

No business coding before `TASK-000 — Repository Bootstrap`.

Codex must not:
- expand scope
- replace workflow with autonomous agents
- change API/data contracts without approval
- add infrastructure without justification

## 14. TECH GATE

**TECH GATE PASSED**

Next:

> TASK-000 → Git/GitHub + Repository Bootstrap → first Vertical Slice
