# AI Career OS — TECH_SPEC v0.1

**Status**：DRAFT / NOT FROZEN

## 1. System Architecture

```text
Browser
   ↓
Next.js + TypeScript
   ↓ HTTP/JSON
FastAPI + Python
   ├── PostgreSQL
   │     └── pgvector（Evidence RAG 阶段）
   ├── PDF Text Extraction
   ├── OpenAI API
   ├── Structured Pipeline
   ├── Retrieval Pipeline
   └── Business Rules / Planning
```

## 2. Architecture Style

**Modular Monolith**：一个 FastAPI 后端，内部按职责拆 `resume / profiles / roles / jobs / evidence / gaps / roadmaps / tasks / progress / rag / llm` 等模块，不做微服务。

## 3. Tech Stack v0.1

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
| LLM Output | Structured Outputs / JSON Schema |
| PDF | PyMuPDF |
| Vector Search | pgvector |
| Testing | pytest |
| Local Infra | Docker Compose |
| Version Control | Git + GitHub |
| Agent Framework | None in MVP |

## 4. AI Boundary

### LLM
- Resume semantic extraction
- JD semantic extraction
- Gap reasoning
- Recommendation explanation
- Roadmap / Daily Task generation
- Manual Replanning
- RAG Grounded Answer

### Code / Rules
- PDF text extraction
- Schema Validation
- JD frequency
- State / relationships
- Sample Count
- Priority 的确定性部分
- User Override
- 权限、安全、Git

原则：可确定计算的逻辑优先代码，LLM 用于语言理解和有依据推理。

## 5. Structured Pipeline

### Resume

```text
PDF → PyMuPDF → Text → LLM Structured Extraction → Pydantic → Draft Profile → User Confirm → Confirmed Profile
```

Embedding 不用于生成 User Profile。

### JD

```text
Raw JD → LLM Structured Extraction → Skill Normalization → Python Aggregation → Market Profile
```

精确频率由代码计算。

## 6. Evidence RAG

RAG 属于最终项目，但不阻塞最早 Critical Path。

适合进入 RAG：Community Notes、面经、长 JD 原文片段、后续学习笔记等非结构化资料。

不依赖 RAG：User ID、Target Role、Task State、Gap Priority、JD 技能出现频率、Confirmed Profile 明确字段。

### Ingestion

```text
Document → Clean → Chunk → Metadata → Embedding → PostgreSQL + pgvector
```

### Retrieval

```text
Question / Evidence Query → Query Embedding → Vector Search → Metadata Filter → Top-K → LLM Grounded Answer
```

RAG 的目标是 Evidence Retrieval，不是做一个泛化聊天知识库。

## 7. PDF Policy

MVP 只支持可提取文字的 PDF；扫描图片 PDF 暂不 OCR。解析失败必须返回明确错误。

## 8. Secret Management

```text
Browser → Next.js → FastAPI → OpenAI
```

`OPENAI_API_KEY` 只允许存在 FastAPI 环境变量；不得进入前端 bundle、Git 或源码硬编码。

需要 `.env` / `.env.example` / `.gitignore`。

## 9. Preliminary Repository Structure

```text
AI-Career-OS/
├── apps/
│   ├── web/
│   └── api/
├── docs/
│   ├── product/
│   └── technical/
├── tests/
├── .env.example
├── .gitignore
└── README.md
```

FastAPI 候选：

```text
apps/api/app/
├── main.py
├── api/
├── schemas/
├── models/
├── services/
├── prompts/
├── db/
└── core/
```

## 10. Git Strategy

个人项目使用 `main + feature/<name>`。

Conventional Commits：`feat:` / `fix:` / `test:` / `docs:` / `refactor:`。

正式业务开发前执行：`TASK-000 — Repository Bootstrap`。

## 11. Codex Definition of Done

每个 Task 必须报告：Changed Files、Tests、Lint/Type Check、Git Branch、Commit、Known Issues、Scope Deviations。

## 12. P0 Completion Sprint v0.1 Implementation Addendum

The implementation branch `feature/p0-completion-sprint` now contains the first complete v0.1 workflow after UIX-001:

```text
Confirmed Profile
  → selected Target Role
  → at least three real Job Descriptions
  → evidence-grounded Market Profile
  → Gap Analysis (MATCHED / PARTIAL / MISSING / UNCERTAIN)
  → deterministic Priorities + user override
  → validated four-week Roadmap
  → Progress / manual Replan
  → Dashboard
```

The derived state is persisted in migration `008_p0_completion_sprint`. Market requirements, evidence rows, gap analyses, priorities, roadmap revisions, weeks, and tasks are relational records with explicit status and fingerprint links. Job Description, preference, target-role, and confirmed-profile changes invalidate downstream derived state. Task progress does not rewrite market evidence.

The API surface added in this sprint is:

- `GET/POST /api/v1/target-roles/{target_role_id}/market-profile`
- `GET /api/v1/market-requirements/{requirement_id}/evidence`
- `GET/POST /api/v1/profiles/{profile_id}/gap-analysis`
- `GET/PUT /api/v1/profiles/{profile_id}/priorities`
- `GET/POST /api/v1/profiles/{profile_id}/roadmap`
- `PATCH /api/v1/roadmap-tasks/{task_id}`
- `POST /api/v1/profiles/{profile_id}/roadmap/replan`
- `GET /api/v1/profiles/{profile_id}/dashboard`

Strict provider schemas are injectable and fail safely when the provider is unavailable. Code owns source binding, evidence substring checks, normalization aliases, frequency aggregation, gap states, factor-based ranking, user-order persistence, roadmap workload validation, invalidation, and progress state transitions. Product Owner browser acceptance and an independent PostgreSQL integration run remain release gates for this sprint branch; this addendum does not freeze the broader v0.1 technical specification.

## 13. Next Technical Work

必须继续设计并冻结：

1. Data Model
2. API Contract
3. Resume / JD / Gap / Roadmap Structured Output Schemas
4. Priority Scoring Contract
5. RAG Chunk / Metadata / Retrieval Contract
6. Error Handling
7. Auth strategy
8. Test Strategy
9. Deployment strategy

完成后：`TECH_SPEC v1.0 FROZEN → TASK-000 → Codex`。
