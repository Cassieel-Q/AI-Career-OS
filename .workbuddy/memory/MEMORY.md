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
  **2026-10-18 已随 `12d6669` 修正为当前实现（中文标签 + 首页渲染 ModelOnboarding），Web 全量 243 passed / 0 failed。**
- 判断方法：`git stash push -u` 后在基线重跑对比，再 `git stash pop`。

## 关键设计约定

- **事实边界**：简历生成只读 ResumeProfile；网申填表可读 ResumeProfile + ApplicationProfile；
  助手默认不读 ApplicationProfile 敏感字段。`resume_visible_facts` 是简历侧唯一入口。
- **投递状态机**：`JobApplication.status`（PENDING/APPLIED/SCREENING/ASSESSMENT/INTERVIEW/OFFER/CLOSED），
  必须支持推进与退回。
- **Pydantic 枚举**：`ExperienceInput.experience_type` 只接受 WORK/INTERNSHIP/CAMPUS/PROJECT/OTHER；
  `ProfileSkillInput.proficiency` 只接受 AWARE/BASIC/PROJECT_READY/PROFICIENT。
- **岗位路由前缀**：mission 相关路由挂在 `/api/v1` 下（`/api/v1/job-missions/{id}/...`）。
- **Studio 文档**需要先有 `TargetResume.status == "CONFIRMED"` 才能创建；确认与预览都用 `If-Match: <revision>`，
  **PATCH 编辑也必须带 `If-Match`**（缺了返回 428「请先读取最新简历修订号」）。
- **事实可信三维**（v1.2）：事实来源（SOURCE_EXTRACTED/USER_PROVIDED/AI_PROPOSED）× 用户核对
  （UNREVIEWED/USER_ATTESTED/REJECTED）× 文案采纳，三者互不推导；旧状态一律降级为 UNREVIEWED。
  事实文本一变，旧签名由 `invalidate_changed_attestations` 退回 UNREVIEWED。
- **已确认档案（CONFIRMED）的锁定范围**：`PUT /profiles/{id}`、换文件、重新解析全部 409
  （`test_profiles.py::test_confirmed_profile_cannot_be_edited` 锁着）；改共享事实的唯一入口是
  `POST /profiles/{id}/facts/attest` + `apply_to_source=true`，且它**只写回描述类文本**。
  已知后果：`sync` 能更新的 title/organization/dates 在产品里够不到（P1 未决，见 v1.2 known-issues）。
- **Studio PATCH 操作类型**：`set_text / add_entry / add_bullet / omit / restore / move /
  set_template / confirm_fact / set_language / set_evidence / set_layout`。
  「填了内容 ≠ 核对过事实」：`set_text` 后节点是 NEEDS_CONFIRMATION，正式版仍被 block，
  必须再 `confirm_fact` 才放行。
- 本地优先模式由 `AI_CAREER_DATA_DIR` 启用；启用后数据库由 `active_dataset` 指针决定，
  未启用时完全回退 `DATABASE_URL`。

## 本地数据与脚本

- 本地数据目录：`%LOCALAPPDATA%\AICareerOS`（`career.db` + `datasets/` + `active_dataset`）。
- **交付/交接类文档放 `docs/` 根目录**（与 `交付验收文档-模型中心v1.2.md` 同级）；
  `docs/handoff/` 已被 .gitignore 忽略（其中 2026-10-11 那份是 ignore 前的遗留）。
  最新交接文档：`docs/交接文档-2026-10-18.md`。
- 一键：`start-all.cmd`；只起本地模式：`start-local.cmd`；浏览器桥：`start-browser-bridge.cmd`。
- 新增迁移后要同步更新 `apps/api/tests/test_alembic_revisions.py` 的链定义与 head 断言。
- **后端必须带 `AI_CAREER_DATA_DIR=%LOCALAPPDATA%\AICareerOS` 启动**，否则回退 `DATABASE_URL`
  （未装 psycopg2）→ 所有写接口 500。

## 可信求职 v1.2 · 评估资产（可复用）

- 分支 `feature/trusted-workflow-v12`；验收文档八份在 `docs/evaluation/trusted-workflow-v12/`。
- 浏览器 E2E：桩模型 8801 / 后端 8100（`AI_CAREER_DATA_DIR=.runtime/e2e-v12`）/ 前端 3100，
  `node docs/evaluation/trusted-workflow-v12/browser/e2e-trusted-workflow.cjs`（6 条主流程 35/35）。
- **桩模型按关键词匹配提示词，顺序即优先级**：「岗位简历生成/What Matters」曾含
  `question`+`interview-ready` 被误判成面试提问（502）；「面试提问」与「评分」都含
  `reference_answer`，必须先按整句区分（422）。宽泛词只能放最后。
- 事实核对面板挂在 `/resumes` 页，**没有独立 `/fact-check` 路由**。
- 面试轮次的评分写在**被回答的那一轮**上；最后一轮常是系统补的追问（`evaluation` 为空）。
- 最新全量基线：后端 1118 passed / 7 failed / 5 skipped；前端 276/0。

## 可信求职 v1.2（FINAL FREEZE，2026-10-19）

- **受控字段修正**：已确认档案整体 `PUT` 仍 409；改单项走 `POST /profiles/{id}/facts/attest`
  带 `apply_to_source=true` + `field_updates`（白名单：经历 title/organization/dates/description、技能 name）。
- **事实签名**：`FactAttestation.signature_text` 覆盖标题/组织/**起止时间**/描述，与展示用的
  `fact_text` 分离；`lock_legacy_signatures()` 必须在改动前调用（保守迁移，不批量升级）。
- **分析过期只标记不替换**：`get_claim_analysis` 返回 `stale=True` + 原因，**不要**静默刷新指纹。
- **确认投递版前必须逐条接受改写要点**，否则 409「还没有任何被接受的要点」（防空白简历的真实闸门）；
  自动化要跑 `PATCH /api/v1/target-resume-bullets/{id}`（`status=ACCEPTED` + `fact_confirmed`）。
- **「简历」页的当前档案读 localStorage**（`ai-career-os-dogfood-profile-id`），**不是** URL 参数。
- 当前稳定版本候选标签：`v1.2.0-rc1`（已推送到远程，指向代码冻结提交 `c518b5c`；未发公开 Release）。

## Git 交付整理（2026-10-19，只做隐私与 Git）

- 远程 `Cassieel-Q/AI-Career-OS` 为 **Public**，默认分支 `main`；`main` 已快进到 `69dc19e`，
  **当前树无真实姓名**；`feature/trusted-workflow-v12` 同点。
- **历史提交里仍有真实姓名（35 个 blob）**，用户决定**暂不执行** filter-repo 重写 + 强推。
  方案、影响范围、回滚办法见 `docs/evaluation/trusted-workflow-v12/git-history-cleanup-plan.md`。
- 本地备份：`D:\ai-career-local-final-20261019.bundle`（35 refs，含标签）；
  更早含隐私历史的 `D:\ai-career-backup-20261017.bundle` **保留不删、绝不上传、绝不纳入 Git**。
  **旧 bundle 里的分支（feat/*、feature/boss-local-app、resumeforge-*、旧 main db9ec58）永远不要推送**，
  它们携带此前删除的隐私截图。
- 扫描结论：无 API Key / 无真实手机邮箱身份证 / 无数据库 / 无简历原件；
  疑似真号 `18381088901`、`19049093719` 是 SHA-256 哈希子串（误报，别再当真号处理）。
- **写文档时不要用真实姓名做 grep/替换示例**——`FINAL-FREEZE.md` 曾因此把姓名写进公开文件，已改占位符。

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
