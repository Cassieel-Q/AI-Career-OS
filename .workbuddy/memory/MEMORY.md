# AI Career OS · 项目长期记忆

## 环境与运行

- 技术栈固定：Next.js 15（App Router，`typedRoutes: true`）+ FastAPI + SQLAlchemy 2 / Alembic + SQLite/PostgreSQL。
- **本机 8000 端口被无关服务（CityQuest API）占用**，本地调试请用 8100 等其它端口。
- 沙箱设置了 `http_proxy`；本地回环请求必须 `no_proxy=127.0.0.1,localhost`（httpx / curl / playwright）。
- `apps/web` 的 `next dev` / `next build` 在 G: 盘必须带 `node --require ./scripts/next-g-drive-fs-compat.cjs`，
  否则报 `EISDIR`/`EPERM`（G: 盘 readlink 行为异常）。
- `next build` 偶发 `.next/trace` EPERM（文件锁），属环境问题；`next dev` + `tsc --noEmit` 可正常验证。
- 路由类型（`.next/types/routes.d.ts`）在 `next dev`/`build` 时生成；新增页面后需先跑一次
  `next dev` 或 `build`，`npm run type-check` 才能识别新路由。

## 已知既有失败（不要误判为本次引入）

- 后端 7 项：`test_claim_provider`、`test_gap_analysis`、`test_market_profile`、`test_priorities`、
  `test_resume_reliability`、`test_roadmap`、`test_target_jobs`（各 1 项）。
- 前端 2 项：`workflow-navigation`（中文/英文标签断言）、`workflow-state`（首页重定向断言）。
- 判断方法：`git stash push -u` 后在基线重跑对比，再 `git stash pop`。

## 关键设计约定

- **事实边界**：简历生成只读 ResumeProfile；网申填表可读 ResumeProfile + ApplicationProfile；
  助手默认不读 ApplicationProfile 敏感字段。`resume_visible_facts` 是简历侧唯一入口。
- **投递状态机**：`JobApplication.status`（PENDING/APPLIED/SCREENING/ASSESSMENT/INTERVIEW/OFFER/CLOSED），
  必须支持推进与退回。
- **Pydantic 枚举**：`ExperienceInput.experience_type` 只接受 WORK/INTERNSHIP/CAMPUS/PROJECT/OTHER；
  `ProfileSkillInput.proficiency` 只接受 AWARE/BASIC/PROJECT_READY/PROFICIENT。
- **岗位路由前缀**：mission 相关路由挂在 `/api/v1` 下（`/api/v1/job-missions/{id}/...`）。
- **Studio 文档**需要先有 `TargetResume.status == "CONFIRMED"` 才能创建；确认与预览都用 `If-Match: <revision>`。
- 本地优先模式由 `AI_CAREER_DATA_DIR` 启用；启用后数据库由 `active_dataset` 指针决定，
  未启用时完全回退 `DATABASE_URL`。

## 本地数据与脚本

- 本地数据目录：`%LOCALAPPDATA%\AICareerOS`（`career.db` + `datasets/` + `active_dataset`）。
- 一键：`start-all.cmd`；只起本地模式：`start-local.cmd`；浏览器桥：`start-browser-bridge.cmd`。
- 新增迁移后要同步更新 `apps/api/tests/test_alembic_revisions.py` 的链定义与 head 断言。
