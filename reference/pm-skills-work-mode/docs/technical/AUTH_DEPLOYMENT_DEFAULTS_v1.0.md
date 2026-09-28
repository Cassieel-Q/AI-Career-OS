# AI Career OS — AUTH_DEPLOYMENT_DEFAULTS v1.0

**Status:** FROZEN

## Auth

MVP 默认采用 Supabase Auth。

原因：
- 与 PostgreSQL 生态衔接方便
- 减少自建密码系统风险
- 足够支持个人项目与 Demo

业务表只保存内部 `user_id` / auth reference，不把认证逻辑散落在 AI 服务里。

## Deployment

### Frontend
Vercel

### Backend
Railway（若实际部署受限，可替换 Render/Fly.io，不改变架构）

### Database
Supabase PostgreSQL + pgvector

## Secrets

- OpenAI API Key 只在 FastAPI 服务端环境变量
- `.env` 不提交 Git
- `.env.example` 只保留变量名

## Interview note

部署选择是工程成本与复杂度 Trade-off，不是产品核心差异化，因此不做自建 Kubernetes / 微服务。
