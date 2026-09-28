# AI Career OS — Product & Tech Glossary

| Term | 中文 | 本项目含义 |
|---|---|---|
| PRD | 产品需求文档 | 定义用户、问题、P0、边界、验收 |
| Critical Path | 关键路径 | 用户获得核心价值的最短路径 |
| Scope Freeze | 范围冻结 | 新需求默认不进入 MVP |
| Backlog | 需求池 | 有价值但当前不做 |
| Evidence | 证据 | 支撑 Gap / Recommendation 的真实来源 |
| Source of Truth | 主要事实来源 | 冲突时某类问题优先相信哪个数据源 |
| Grounding | 依据约束 | 先拿证据，再让 LLM 推理 |
| Structured Output | 结构化输出 | 让 LLM 按固定 Schema 返回 |
| Gap | 差距 | User Profile 与 Target Market Profile 的差异 |
| User Override | 用户覆盖 | 用户可以改变 AI 默认建议 |
| State | 状态 | 当前目标、Gap、任务、进度等事实 |
| Replanning | 重规划 | 根据 State 调整后续计划 |
| Frontend | 前端 | Next.js Web UI |
| Backend | 后端 | FastAPI 业务、AI、RAG、数据库服务 |
| API | 接口 | Next.js 与 FastAPI 的契约 |
| Modular Monolith | 模块化单体 | 一个后端服务内部按职责拆模块 |
| Embedding | 向量表示 | 把文本变成用于语义相似度的数字向量 |
| Vector Search | 向量检索 | 按语义相似度找相关文本 |
| pgvector | PostgreSQL 向量扩展 | 在 PostgreSQL 中保存/检索向量 |
| RAG | 检索增强生成 | Retrieve Evidence 后再让 LLM 基于证据生成 |
| Chunk | 文本分块 | 长文档切成可检索的小段 |
| Metadata | 元数据 | chunk 的来源、文档 ID、JD ID、类型等 |
| Top-K | 前 K 条结果 | 向量检索返回最相关的 K 条 |
| Structured Pipeline | 结构化链路 | Resume/JD → Schema → DB → Rules |
| Retrieval Pipeline | 检索链路 | Document → Chunk → Embedding → Search |
| Deterministic Workflow | 确定性工作流 | 下一步由程序规则决定 |
| Agent | 智能体 | 根据目标和状态自主选择工具/步骤的 LLM 系统 |
| Hybrid System | 混合系统 | 规则计算 + LLM 推理 |
| Secret Management | 密钥管理 | API Key 只放后端环境变量 |
| ORM | 对象关系映射 | 用 Python 对象操作数据库 |
| Migration | 数据库迁移 | 记录数据库 Schema 版本变化 |
| Eval | AI 评估 | 测抽取、检索、Gap、Roadmap 质量 |
| Conventional Commits | 提交规范 | feat/fix/test/docs/refactor 等 |
| Definition of Done | 完成定义 | 代码、测试、文档、Git 等都满足才算完成 |
| TASK-000 | 仓库启动任务 | Codex 的第一个任务：Git + Repo Bootstrap |
