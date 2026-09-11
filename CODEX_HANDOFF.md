# AI Career OS — Resume Profile Normalization Codex Handoff

> 新 Codex 对话首先阅读本文件。本文档是当前项目状态的唯一交接入口；不要把旧聊天记录或旧计划中的未完成复选框当作当前任务。

## 1. 项目身份与当前状态

- 项目：AI Career OS — Profile Confirmation & Resume Profile Normalization
- 仓库根目录：`G:\myself\ai-career-OS-resume-profile-normalization`
- 当前日期：2026-09-11（Asia/Shanghai）
- 当前分支：`feature/resume-profile-normalization`
- 远端：`origin/feature/resume-profile-normalization`
- 当前 HEAD：`4d7301e05f9440c79c03a47c7ed385c5353cfd27`
- 当前提交：`fix: tighten DeepSeek section JSON contracts`
- 工作树：干净；本地 HEAD 与远端 HEAD 一致
- 当前范围：TASK-002 及 TASK-002.5 系列可靠性加固已实现；当前最近工作是 TASK-002.5G DeepSeek section JSON contract acceptance fix
- 下一阶段：先完成真实 PostgreSQL / DeepSeek 浏览器 smoke verification，再决定是否继续同一分支上的小范围修复

不要 merge `main`，不要 force-push，不要开始 TASK-003。

## 2. 必要入口文件

开始工作时按以下优先级读取：

1. 本文件 `CODEX_HANDOFF.md`
2. `README.md`
3. `apps/api/app/main.py`
4. `apps/api/app/resume_schemas.py`
5. `apps/api/app/resume_sections.py`
6. `apps/api/app/resume_normalization.py`
7. `apps/api/app/profile_service.py`
8. `apps/api/app/database.py`、`apps/api/app/models.py`、`apps/api/app/profile_schemas.py`
9. `apps/api/alembic/env.py` 与 `apps/api/alembic/versions/`
10. `apps/web/app/page.tsx` 与 `apps/web/app/profile-flow.ts`
11. `apps/api/tests/test_resume.py`、`test_resume_reliability.py`、`test_profiles.py`、`test_postgres_integration.py`
12. 最新计划记录：`docs/superpowers/plans/2026-09-11-deepseek-contract-acceptance.md`

`docs/review/TASK-002*.md` 和更早的 `docs/superpowers/plans/*` 是历史证据，不是新的执行指令；只在需要核对决策来源时读取。

## 3. 当前有效交付物

### Profile Confirmation

- 简历上传后，经过证据 grounding/normalization 的结果直接创建 `status=DRAFT` Profile。
- 支持 `GET /api/v1/profiles/{profile_id}`、`PUT /api/v1/profiles/{profile_id}`、`POST /api/v1/profiles/{profile_id}/confirm`。
- `PUT` 只保持 `DRAFT`；只有显式 confirm 才能转为 `CONFIRMED`。
- 前端通过 URL 中的 `profile_id` 在刷新后 GET 并恢复 Profile，不依赖 React 内存状态。
- Draft 有 dirty state；Confirm 时若有未保存改动，先用合法 Save Draft payload 执行 PUT，成功后才 POST confirm。PUT 失败时不 confirm，并清理 loading 状态。
- `CONFIRMED` Profile 在前端只读，编辑、添加、删除控件保持禁用。

### Resume extraction / normalization

- section-first extraction 先按显式 heading 切分，再对非空、受支持 section 做有界 targeted extraction。
- 保留 source-surface grounding：模型返回的事实必须能在对应 section 中逐项锚定；不支持的事实被丢弃并产生结构化 warning，不凭空补事实。
- 保留确定性恢复：Word / Excel / PowerPoint、显式 credentials、credential score、CAMPUS classification、Education institution recovery。
- `relevant_courses` 对新结果默认是 `[]`；旧 Profile 中缺失或 `null` 时，加载和前端状态都归一化为 `[]`。
- Experience 的 `organization`、`dates`、`description` 继续逐字段 grounding；不支持的可选字段只丢该字段，不丢整个 Experience。
- 每个简历最多五次应用层 extraction/repair 操作；`OPENAI_TIMEOUT_SECONDS` 默认 30 秒，`OPENAI_MAX_RETRIES` 默认 0，均有上限。

### DeepSeek adapter

- OpenAI-compatible JSON transport 使用 `response_format={"type":"json_object"}`。
- DeepSeek endpoint 自动加入 `extra_body={"thinking":{"type":"disabled"}}`。
- 处理边界保持：`JSON content -> json.loads -> Pydantic model_validate -> grounding`。
- section prompt 已改为按 `EDUCATION`、`EXPERIENCE`、`CAMPUS`、`SKILLS`、`CREDENTIALS`、`LANGUAGE` 使用独立紧凑 JSON 合同。
- `LeanCertification` 保持 `extra="forbid"`，section 输出只允许 `name`、`issuer`、`date`、`score`；禁止 `status`、`credential_type`、`level`、`type`、`category` 等额外字段。
- Experience/CAMPUS 的可选字段必须逐项从 supplied section 原文复制；不能合并 bullet、改写 organization、规范日期标点、合成日期范围或拼接分散文本；无法逐项原文复制时返回 `null`。
- Pydantic `ValidationError` 的安全诊断只记录 `stage`、`section`、`loc`、`type`、`error_count`，不记录模型 JSON、简历文本、evidence、字段值或 secrets。

## 4. Git 状态与关键提交

当前分支历史中与后续开发最相关的提交：

| Commit | 作用 |
|---|---|
| `5d111f1` | section-first resume extraction |
| `f4a5102` | preserve source-grounded section facts |
| `7d9a02d` | support DeepSeek JSON output |
| `94ba721` | complete DeepSeek JSON output plan |
| `4d7301e` | tighten DeepSeek section JSON contracts（当前 HEAD） |

当前 HEAD 已推送到 `origin/feature/resume-profile-normalization`。任何新修改都应创建新的普通 commit 后正常 push；不要重写远端历史。

## 5. 最新提交修改的文件

当前最新 commit 只修改：

- `apps/api/app/main.py`
  - 增加六类 section-specific JSON prompt contract。
  - 增加白名单化的 Pydantic validation `loc/type/count` 元数据。
  - section provider failure 日志附带安全 section key 与结构化诊断。
  - 未改变 Pydantic schema、grounding、section planner 或公开 API。
- `apps/api/tests/test_resume.py`
  - 精确 credential JSON 通过测试。
  - `status` / `credential_type` 额外字段拒绝测试。
  - 安全 validation diagnostic 测试。
  - 各 section contract 选择测试。
  - Experience optional-field prompt contract 测试。
- `docs/superpowers/plans/2026-09-11-deepseek-contract-acceptance.md`
  - 当前任务的执行计划与完成状态。

本次未修改 frontend、数据库 schema、ORM models、Alembic migration、Profile API contract 或真实数据库。

## 6. 关键技术决策（当前有效）

### 数据库与迁移

- 生产/真实持久化以 PostgreSQL 为准，使用 SQLAlchemy + Alembic。
- `DATABASE_URL` 是应用运行和 Alembic migration 的数据库配置入口。
- `TEST_DATABASE_URL` 只用于 PostgreSQL integration tests，必须指向独立数据库 target。
- SQLite in-memory 只用于快速、纯逻辑或本地 service/API fixture 测试，不能作为 PostgreSQL persistence/migration/API gate 的最终证据。
- integration helper 在 destructive setup 前检查：若 `DATABASE_URL` 与 `TEST_DATABASE_URL` 指向同一 backend/host/port/database，立即失败并报 `TEST_DATABASE_URL must not point to the application database.`。
- 当前代码中的 migration chain 是：

  `001_create_profile_tables` → `002_profile_normalization` → `003_credential_details`

- 所有 revision ID 必须不超过 Alembic `alembic_version.version_num` 的 32 字符限制；`002_profile_normalization` 是已采用的短 ID。
- 禁止用 `alembic stamp` 绕过迁移，禁止 reset/drop 真实数据库，禁止为了测试修改应用数据库。

### Provenance / trust boundary

- AI evidence、provenance、evidence offsets 属于服务端控制的可信边界。
- 前端只提交后端允许编辑的用户字段，不得修改 AI evidence 或伪造 provenance。
- Pydantic validation 不得为了让 provider 请求通过而放宽；unknown model fields 必须失败并进入安全 taxonomy。
- 不允许用非原文摘要、跨 section 拼接或推断事实填补简历内容。

### 产品范围

当前 TASK-002 范围不包含：

- pgvector、RAG、Role Recommendation、JD、Gap Analysis
- 复杂 audit/versioning
- authentication/user profile listing
- TASK-003 内容

## 7. 验证状态

最近一次代码验证结果：

| Gate | Command / 状态 |
|---|---|
| Backend focused | `cd apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_resume.py tests/test_resume_reliability.py -q` → `172 passed` |
| Backend full | `cd apps/api; .\.venv\Scripts\python.exe -m pytest -q` → `211 passed, 1 skipped` |
| Frontend tests | `cd apps/web; npm test` → `13 passed` |
| Frontend type-check | `npm run type-check` → passed；自动生成的 `next-env.d.ts` 已恢复为基线 |
| Frontend lint | `npm run lint` → passed；只有现有 `next lint` deprecation notice |
| Git whitespace | `git diff --check` → passed |
| Remote consistency | local HEAD = remote HEAD = `4d7301e`；工作树 clean |

`1 skipped` 是没有配置独立 `TEST_DATABASE_URL` 时的 PostgreSQL integration skip，不代表 PostgreSQL persistence gate 已通过。

## 8. 数据库状态

### 已知的代码状态

- PostgreSQL 连接代码位于 `apps/api/app/database.py`；没有 `DATABASE_URL` 时 API persistence 返回配置错误。
- Alembic 从 `apps/api/alembic/env.py` 读取 `DATABASE_URL`。
- `apps/api/tests/test_postgres_integration.py` 覆盖 migration upgrade、Profile round-trip、GET、PUT、confirm、DRAFT → CONFIRMED readback，并拒绝 SQLite。
- `apps/api/requirements.txt` 已声明 PostgreSQL runtime drivers，包括 `psycopg[binary]` 与 `psycopg2-binary`。

### 真实数据库状态

当前仓库和最近提交没有可作为 live database proof 的 revision 输出。应将真实 PostgreSQL 当前 revision 视为 **待验证**，不要因为 migration 文件存在或 SQLite tests 全绿就假设真实数据库已到 head。当前 handoff 也不声称已经修改真实数据库。

下一次执行真实 DB 验证时必须：

1. 只输出 `DATABASE_URL_PRESENT=True/False`，不要打印完整 URL、password 或 token。
2. 先对目标 PostgreSQL 执行只读 `SELECT 1`；失败时先诊断 DNS/TCP/SSL/认证/URL parsing，不改 migration 绕过认证。
3. 检查 `python -m alembic current`、`heads`、`history`。
4. 只有安全连接和 revision chain 确认后，才执行 `python -m alembic upgrade head`。
5. 不使用 `stamp`，不 reset/drop，不删除已有 Profile 数据。
6. integration test 使用独立 `TEST_DATABASE_URL`；缺少时保持 skip，并在报告中标为 `UNVERIFIED`。

## 9. 当前阻塞项与风险

1. **PostgreSQL live gate 未由当前仓库状态证明。** 需要独立测试数据库或明确授权的 Supabase 开发数据库，先做安全连接和迁移检查。
2. **TASK-002.5G 的真实 DeepSeek/browser smoke 尚未在当前 commit 后重新执行。** 需要确认 CREDENTIALS 不再因额外字段触发 `ValidationError`，Experience/CAMPUS 可选字段 warning 是否按预期下降，且无数据幻觉。
3. **旧文档存在历史状态冲突。** `docs/review/TASK-002*.md` 和旧 readiness/plan 文件保留了当时的计数与未完成项；以本文件、当前代码、当前测试输出和最新 commit 为准。
4. 当前没有代码级阻塞；本地自动化测试和工作树均正常。

## 10. 下一步任务

按以下顺序继续，不要直接开始 TASK-003：

### A. Real PostgreSQL verification

- 检查当前 Codex 进程是否继承 `DATABASE_URL`，只输出 presence flag。
- 对 PostgreSQL 执行 `SELECT 1`。
- 运行 Alembic current/heads/history，确认 chain 与代码一致。
- 运行真实 `upgrade head`，随后检查 schema 与 migration 预期一致且无 destructive 意外。
- 若使用 integration tests，先确认 `TEST_DATABASE_URL` 与应用数据库 target 不同。

### B. DeepSeek acceptance smoke

- 使用真实 DeepSeek API 和一份包含 Education、Experience/Campus、Skills、Credentials、Language 的 PDF 做小规模 smoke。
- 记录请求成功/失败、section warning taxonomy、总耗时和调用次数；不要记录模型 JSON、简历原文或 secrets。
- 检查：
  - credential response 只使用 `name/issuer/date/score`；
  - `status`、`credential_type` 等 extra field 进入 structured validation，而不是被静默丢弃；
  - Experience optional fields 只有原文可复制时才保留；
  - Office/credential score/CAMPUS 等确定性恢复不回归；
  - Profile 仍创建为 DRAFT，前端刷新与 confirm 流程保持正常。
- 若发现新问题，只在当前 TASK-002 范围内追加最小修复和回归测试，然后创建新 commit 并 push。

### C. 交付前复核

- Backend focused/full pytest。
- Frontend test/type-check/lint；如用户明确要求再运行 build。
- `git diff --check`、`git status --short --branch`、local/remote HEAD 对齐。
- 报告 PostgreSQL live gate 和 real provider smoke 是 `PASS` 还是 `UNVERIFIED`，不要用 SQLite 结果替代。

## 11. 不得破坏的约束

- 不 merge `main`，不 force-push。
- 不开始 TASK-003。
- 不 reset、drop、stamp 或手工改写真实数据库。
- 不将 SQLite 当作 PostgreSQL integration 的最终证明。
- 不修改 schema、ORM semantics、migration chain、Profile API contract 或前端 workflow 来绕过 provider 问题。
- 不放宽 `extra="forbid"`，不静默丢弃未知模型字段。
- 不允许客户端修改 server-controlled AI evidence/provenance。
- 不削弱 proficiency enum、DRAFT → CONFIRMED 状态机、PostgreSQL locking 或 test database isolation。
- 不记录 API key、password、完整数据库 URL、模型 JSON、简历原文、evidence text 或字段值。
- 不凭空编造 Education、Experience、Skills、Credentials、Courses 或 proficiency。
- 只在有真实 schema 变化时添加 migration；revision ID 必须 ≤32 字符。

## 12. 发送给新 Codex 的启动提示

可将下面内容直接作为新对话第一条消息：

```text
请先阅读项目根目录的 CODEX_HANDOFF.md，并以其中的当前状态为准。

项目：G:\myself\ai-career-OS-resume-profile-normalization
当前分支：feature/resume-profile-normalization
当前 HEAD：4d7301e（已 push，工作树应保持 clean）

TASK-002 及 TASK-002.5 系列实现已完成。不要 merge main，不要 force-push，不要开始 TASK-003。
下一步按交接文档顺序完成：
1. 安全验证 PostgreSQL DATABASE_URL：只输出 presence，不打印 secrets；先 SELECT 1，再检查 Alembic current/heads/history，确认后才 upgrade head。
2. 使用独立 TEST_DATABASE_URL 运行 PostgreSQL integration；同应用数据库必须 fail-fast，SQLite 不能替代最终验证。
3. 对最新 DeepSeek JSON contract fix 做真实 provider/browser smoke；保留严格 Pydantic extra=forbid、source-grounded trust boundary 和现有 API/frontend/database contract。
4. 若发现问题，只做当前 TASK-002 范围内的最小修复，补测试、提交新 commit 并 push。

直接执行，不要重复询问已经在交接文档中明确的设计；遇到真实数据库认证失败先诊断，不猜密码、不改 migration 绕过问题。完成后报告测试、真实 PostgreSQL gate、DeepSeek smoke、commit、push 和 git status。
```
