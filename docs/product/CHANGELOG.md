# AI Career OS — CHANGELOG

## 2026-09-19 — UIX-001 Workflow Navigation Shell — FROZEN

- Product Owner browser manual acceptance: PASS.
- UIX-001 is complete and frozen; the shared workflow now uses focused, URL-addressable step pages with server-backed guards.
- UIX-001 did not change backend code, API contracts, or database schema.
- The next planned phase is one P0 Completion Sprint covering TASK-007 through TASK-014; it has not started.
- Frontend verification: 56 tests passed; TypeScript and ESLint passed; production build and dynamic-route smoke passed from the authorized temporary C: validation copy after the G: Next filesystem issue.

## 2026-09-04 — TASK-002 Profile Confirmation & Supplement

- Resume parsing creates a persisted `DRAFT` Profile after evidence validation.
- Added editable education, skills, experiences, and certifications with
  `AI_EXTRACTED`, `USER_ENTERED`, and `USER_EDITED` provenance.
- Added user-selected skill proficiency and explicit `DRAFT` → `CONFIRMED`
  transition through the profile API.
- Added PostgreSQL-first SQLAlchemy models and Alembic migration.
- PostgreSQL integration remains a separate release gate and is not replaced by
  SQLite unit fixtures.

## 2026-09-03 — Pre-Codex Baseline v1.0

- 合并所有 PRD Review 与 Final Review 结果。
- 保持 14 个 P0 Capability，不新增产品 P0。
- 技术方向更新为 Next.js Frontend + FastAPI Backend。
- 增加 Structured Data + Evidence RAG 双轨架构。
- 明确 Resume 核心解析不依赖 Embedding。
- 最终项目计划加入 PostgreSQL + pgvector Evidence RAG，但不阻塞 Core Workflow。
- 明确 Workflow First, Agent Later。
- 增加 Git / Repository Bootstrap 作为 Codex 的 TASK-000。

## 2026-09-02 — Product Gate Passed

- 完成 Product Discovery。
- 冻结 14 个 P0 Capability。
- 建立 PRD / Backlog / Decisions / Glossary。

## 2026-09-03 — Technical Gate Passed
- Frozen RAG defaults.
- Frozen Error/Retry policy.
- Frozen Test/Eval strategy.
- Selected Supabase Auth, Vercel frontend, Railway backend.
- TECH_SPEC v1.0 frozen.
- TASK-000 Repository Bootstrap prepared.
