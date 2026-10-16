# AI Career OS · 项目长期记忆

## 环境与运行

- 技术栈固定：Next.js 15（App Router，`typedRoutes: true`）+ FastAPI + SQLAlchemy 2 / Alembic + SQLite/PostgreSQL。
- **本机 8000 端口被无关服务（CityQuest API）占用**，本地调试请用 8100 等其它端口。
- 沙箱设置了 `http_proxy`；本地回环请求必须 `no_proxy=127.0.0.1,localhost`（httpx / curl / playwright）。
  **httpx 必须用 `httpx.Client(trust_env=False)`**：只设 `no_proxy` 不可靠，代理会把本机请求
  转发并写成绝对形式的路径，后端返回 404（表现为「第一次成功、之后全 404」，极易误判为应用缺陷）。
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
- **后端必须带 `AI_CAREER_DATA_DIR=%LOCALAPPDATA%\AICareerOS` 启动**，否则回退 `DATABASE_URL`
  （未装 psycopg2）→ 所有写接口 500。

## 测试隔离（踩过真事故，务必遵守）

- **任何触碰数据集的测试必须隔离 `AI_CAREER_DATA_DIR`**（monkeypatch 到 tmp_path）。
  曾因 `restore_as_new_dataset` 未隔离，把用户真实 `active_dataset` 指针切到一个 17 字节假库，
  导致服务全部 503。`tests/test_security_boundaries.py` 里有 autouse fixture 可作模板。
- 备份恢复只能生成**新**数据集，绝不覆盖当前库；E2E 结束后必须切回原数据集。
- 不要同时跑 pytest 全量和打真实服务的 E2E（会争抢 SQLite 导致 503）。
- `next build` 若需隔离验证：把源码 **真复制**（不要 junction，readlink 会 EISDIR）到非 G 盘 NTFS 目录。

## 岗位采集（job_ingest）要点

- 适配器在 `normalize_job` **之后**改写 `company` 时，必须调用 `retag_company()` 重算
  `dedupe_key`。否则库里存的是旧 key，`find_duplicates` 永远查不到 → 去重形同失效
  （Greenhouse 曾因此每次重复采集都「新增 30 条」）。
- `save_collected` 里来源结构化字段优先于启发式切分结果（启发式会把 JD 首行当公司/岗位名）。
- 支持的公开来源：RemoteOK、Remotive、Greenhouse（需 board token）、Lever（需企业标识）。
  三者都**不支持服务端城市/实习过滤**，只能本地过滤（`filter_mode=local`）。
- **中文招聘网站（BOSS 直聘 / 实习僧）未做真实验证**，标记 `CHINESE_JOB_SITES_UNVERIFIED`，
  不得写成「已支持」。需登录平台的唯一合规入口是「粘贴完整 JD」。
- 评测口径：采集时间 ≠ 发布时间；接口成功 ≠ 岗位仍在招；无人工标签时相关性记 `UNREVIEWED`。
