# AI Career OS — DECISIONS

## Product Decisions

- **DEC-001**：MVP 聚焦 AI / 大模型职业，而不是所有职业。
- **DEC-002**：Primary Outcome 是“接下来具体做什么”。
- **DEC-003**：JD 是岗位显性要求的主要 Source of Truth，社区经验做补充。
- **DEC-004**：Resume-first + 强制用户确认。
- **DEC-005**：用户控制权高于 AI 默认排序，使用 Soft Guardrail。
- **DEC-006**：长期路线粗略，最近 4 周详细。
- **DEC-007**：日微调、周重规划、用户主动触发优先。
- **DEC-008**：Dashboard-first，不做 Chatbot-first。
- **DEC-009**：MVP 手动提供 3–10 个 JD，不做招聘网站抓取。
- **DEC-010**：32 个 P0 子需求压缩为 14 个 Capability。
- **DEC-011**：首次 Role Exploration 使用 Built-in Role Profiles；真实 JD 导入后以后者为主。
- **DEC-012**：Resume Parser 不直接判断技能熟练度。
- **DEC-013**：Gap 补齐成本只用 LOW / MEDIUM / HIGH。
- **DEC-014**：MVP Roadmap 不负责完整学习资源推荐。
- **DEC-015**：Task Completion 不等于 Skill Mastery。
- **DEC-016**：LLM 用于语言理解、结构化抽取、有证据推理和规划；确定性规则优先用代码。

## Technical Decisions

### DEC-017 — Next.js Web + FastAPI Backend
**Decision:** Next.js + TypeScript 负责 Web UI；FastAPI + Python 负责业务、AI、RAG 和数据库。  
**Why:** 清晰体现 Web → API → AI/DB 的真实工程链路，也方便 Python AI/Eval/PDF 生态。  
**Trade-off:** 需要维护两个应用和清晰 API Contract。

### DEC-018 — Core Workflow 不依赖 RAG，但最终项目加入 Evidence RAG
**Decision:** Resume → Profile → JD → Gap → Plan 先走 Structured Pipeline；最终展示版增加真正用于非结构化 Evidence Retrieval 的 RAG。  
**Why:** 避免为了 RAG 而 RAG，同时覆盖 AI 岗位面试需要理解的技术点。

### DEC-019 — Structured Data 与 Vector Retrieval 双轨
**Decision:** 精确事实、频率、状态、关系走 PostgreSQL；社区资料、长文本和语义证据检索走 Embedding / Vector Retrieval。  
**Why:** 向量检索不适合精确统计，结构化查询也不适合大规模语义匹配。

### DEC-020 — PostgreSQL + pgvector
**Decision:** 不额外维护独立 Vector DB。  
**Why:** 当前数据规模下 pgvector 足够，基础设施更简单。

### DEC-021 — Resume 核心解析不是 Embedding
**Decision:** PDF → Text Extraction → LLM Structured Output → Confirmed Profile。  
**Why:** Embedding 解决语义相似度，不负责可靠抽取学历、技能、经历等事实。

### DEC-022 — Workflow First, Agent Later
**Decision:** MVP 使用 Deterministic Workflow，不引入自主 Agent。  
**Revisit When:** Ask Career Coach 需要根据自然语言动态选择工具时。

### DEC-023 — Codex 从 Git / Repository Bootstrap 开始
**Decision:** 正式业务编码前先执行 TASK-000：Git、仓库结构、`.gitignore`、`.env.example`、README、基础 lint/test、提交规范。  
**Why:** 项目从第一天就可追踪、可回滚、可 Review。

## DEC-024 — RAG 使用可评估的基线参数
**Decision:** 首版 chunk 约 400–700 tokens、overlap 约 80、top_k=5；这些是 Eval 起点，不宣称为最优值。  
**Status:** ACCEPTED

## DEC-025 — AI 输出必须先 Validation 再持久化
**Decision:** Structured Output 未通过 Pydantic Validation 时不得进入正式业务状态。  
**Status:** ACCEPTED

## DEC-026 — Test 与 Eval 分开
**Decision:** Test 验证软件行为，Eval 验证 AI 输出与检索质量。  
**Status:** ACCEPTED

## DEC-027 — Supabase Auth + Vercel/Railway
**Decision:** MVP 使用托管认证与部署，避免把精力花在非核心基础设施。  
**Status:** ACCEPTED
