# AI Career OS｜WorkBuddy 交接文档

> 交接日期：2026-10-11  
> 接收方：WorkBuddy  
> 项目根目录：`G:\myself\ai-career`  
> 当前产品主线：`main`  
> 当前主线：`main`；产品代码基线：`2ca4359 feat: align resume studio with mission UI`。开始工作前请执行 `git rev-parse HEAD` 核对主线 tip。

## 1. 先读这些文件

按下面顺序进入项目，不要依赖聊天记录：

1. `AGENTS.md`（如果存在）
2. `00-项目索引.md`
3. `00-当前状态.md`
4. `DECISION_LOG.md`
5. `05-QA-Gate.md`
6. `README.md`
7. `docs/evaluation/2026-10-09-grok-evaluation-handoff.md`
8. `docs/evaluation/2026-10-09-问题汇总.md`
9. `docs/evaluation/findings-and-backlog.md`
10. `docs/evaluation/product-risk-acceptance.md`
11. `docs/evaluation/e2e-2026-10-10/README.md`

如果需要了解当前 UI 交互，再看：

- `apps/web/app/mission-page.tsx`
- `apps/web/app/resume-studio/studio-page.tsx`
- `apps/web/app/resume-studio/studio.css`
- `apps/web/app/interview-records/`
- `docs/screenshots/project-tour-2026-10-10/`

## 2. 当前有效状态

### Git 与工作区

- `main` 已经包含 `feature/eval-benchmark-v1` 的全部提交。
- 本地 `main` 与 `origin/main` 已同步；`feature/eval-benchmark-v1` 与 `origin/feature/eval-benchmark-v1` 保持在产品代码提交 `2ca4359`。
- GitHub 主线已推送成功：<https://github.com/Cassieel-Q/AI-Career-OS/tree/main>
- 当前主检出只有两类未跟踪内容：
  - `apps/api/alembic/versions/014_interview_records.py`
  - `image/`
- 这两类内容来自合并前主检出的本地工作，不属于本次主线提交。不要删除、覆盖、自动加入新提交或把旧迁移混入当前迁移链。
- 合并前本地改动仍保留在 stash：`pre-merge local interview records work`。

### 已完成的产品工作

1. 评测器缺少实际模型输出时改为 `NOT_RUN`，不再用预期值冒充实际结果。
2. 针对 Grok/DeepSeek 评测问题完成一轮产品修复：JD 证据、经历筛选护栏、高信号项目恢复、参考回答事实门控、面经 intel 接线和来源档案联系人误报。
3. Resume Studio 已统一为岗位页的视觉语言：米白背景、深绿色主色、细边框、圆角白卡片、统一阅读宽度和按钮层级；没有改变事实确认、编辑、修订或 PDF 逻辑。
4. README 已补充产品结构、本地启动、验证命令和 Project Tour。
5. Project Tour 使用真实本地浏览器截图，覆盖岗位档案、岗位识别、简历审阅、Resume Studio、模拟面试预览、面试记录库六个页面。

### 当前真实证据

- 截图目录：`docs/screenshots/project-tour-2026-10-10/`
- 机器可读报告：`docs/screenshots/project-tour-2026-10-10/report.json`
- 浏览器说明：`docs/evaluation/e2e-2026-10-10/README.md`
- 6 个截图路由在报告中均为 HTTP 200。
- 本轮没有提交视频；不要把截图描述成视频，也不要自行补造录屏结果。

## 3. 证据、推断与交付边界

### 已验证证据

- Web：`npm test` 为 194 passed。
- Web：`npm run type-check` 通过。
- Web：`npm run build` 通过；仅有已有 ESLint/自定义字体 warning。
- `git diff --check` 通过。
- `origin/main` 与本地 `main` 已核对同步；产品代码提交为 `2ca4359`。
- Project Tour 浏览器报告和截图来自本地实际运行，不是静态 mock HTML。

### 当前可以推断的结论

- 主流程可以从 `/missions` 进入岗位识别、简历来源、岗位定向简历、Studio 和模拟面试预览。
- Studio 的页面外壳已经与岗位页统一，三栏编辑工作台仍然保留。
- 工程回归通过不等于模型质量、招聘转化率或真实用户可用性已经证明。

### 当前不能宣称的结论

- 没有完成 30 JD / 10 简历 / 90 改写 / 50 面试题 / 5 真人用户的完整目标评测。
- 没有完成盲态 Direct LLM A/B 对照。
- 没有完成授权真人数据和真人可用性结论。
- 没有完成生产 PostgreSQL 全链迁移和外部部署验证。
- 不能把合成样本、单元测试通过率或目标阈值写成真实产品效果。

## 4. 下一阶段优先任务

WorkBuddy 应从新的 worktree/feature 分支开始，不要直接在 `main` 上开发。建议：

```powershell
cd G:\myself\ai-career
git status --short
git worktree add .worktrees/workbuddy-next -b feature/workbuddy-next main
cd .worktrees/workbuddy-next
```

### P0：先处理评测已经暴露的高风险

1. **经历筛选四分类校准**
   - 不相关的校园书店、外卖、咖啡师等经历不能被泛化为高亮。
   - 创作、A/B 测试、关键产品/科研项目不能被错误 `OMIT`。
   - 使用代码实际枚举：`KEEP_AND_HIGHLIGHT`、`KEEP`、`DEEMPHASIZE`、`OMIT`。
   - 为负例、关键正例和 `CRITICAL_SELECTION_ERROR` 增加可复现回归。

2. **JD 学历与 must-have 抽取**
   - 中文“本科”“硕士”等学历表达需要稳定进入结构化字段。
   - 抽取结果要保留 JD 原文证据，不要用模型推断填充事实。
   - 修复后分别报告学历准确率/完整率和 must-have Precision、Recall、F1。

3. **面经 intel 的 demo/CURATED 泄漏**
   - 检查 `apps/api/app/mission_provider.py` 与 `interview_pack_intel` 的全部接线。
   - 演示数据、CURATED 元信息不能被当成目标公司的真实面经显示。
   - 增加服务级测试和浏览器可见文本断言。

4. **参考回答和改写事实门控**
   - 只能使用原始简历或用户已确认的 bullet。
   - 重点回归“分析 50 篇内容”不能被改成“访谈 50 位创作者”一类事实污染。
   - 未确认的 `UNSUPPORTED` / `NEEDS_CONFIRMATION` 内容不能进入正式 PDF。

### P1：随后完成端到端闭环

1. 绑定简历后验证 Studio 预览、档案源预览和 PDF 的联系方式一致。
2. 验证 decision 与中文 why 文案不矛盾。
3. 验证身份编辑后，筛选、改写、面试题都使用新公司/岗位身份。
4. 完成 Studio 编辑、旧来源 reimport、`If-Match` 冲突恢复、确认后导出 PDF 的浏览器路径。
5. 完成模拟面试交卷、评分、追问、复盘和真实面试记录库的完整浏览器证据。

### P2：评测扩展

1. 补齐真实/合成样本清单和授权状态。
2. 实现或完善 `jd / match / rewrite / interview / baseline / report` CLI。
3. 冻结 Direct LLM baseline prompt，按同一案例做盲态配对评分。
4. 未完成项必须标为 `NOT_RUN`、`NOT_EVALUABLE` 或 `UNRATED`，不能静默排除。

## 5. 推荐执行与验证命令

### Web

```powershell
cd apps/web
npm test
npm run type-check
npm run build
```

### API

使用项目实际可用的 Python 环境运行：

```powershell
cd apps/api
python -m pytest -q
python -m compileall -q app
```

如果 API 全量出现既有失败，先与 `docs/evaluation/product-risk-acceptance.md` 和 `docs/qa/combine/2026-10-09-resume-ui-content.md` 对照，逐项记录“基线已存在 / 本次新增”，不要直接归为通过。

### 浏览器 Project Tour

启动 API 和 Web 后，优先使用：

```powershell
node docs/evaluation/e2e-2026-10-10/browser/capture-tour.cjs
```

如字体等待导致截图超时，先保存失败日志；不要覆盖现有成功证据或把部分运行写成完整报告。可以只重跑 Studio 路由，并在报告中明确时间和范围。

## 6. 不要混回当前主线的内容

- 不要把 `apps/api/alembic/versions/014_interview_records.py` 作为新迁移提交；当前有效链是 `013_profile_contacts → 014_resume_studio → 015_interview_records`。
- 不要把主检出的 `image/` 原始素材提交到代码分支。
- 不要把旧 `/workflow/...` 页面当成当前 `/missions` 主流程的浏览器验收结果。
- 不要把历史 17 张 Product Tour 截图当成当前六路由证据；它们只用于历史对照。
- 不要把浏览器打印 PDF、未确认事实或模型自评当成正式产品效果。

## 7. 完成标准

下一阶段至少应交付：

1. 每个 P0 问题有 case ID、复现输入、根因证据、代码修复和回归测试。
2. 更新 `docs/evaluation/findings-and-backlog.md`、`docs/evaluation/product-risk-acceptance.md` 和 `00-当前状态.md`。
3. 浏览器证据覆盖真实持久化结果，不只截图初始页面。
4. README / Project Tour 与实际当前分支同步，不写未运行的结果。
5. 新分支通过 Web/API 验证后，再由用户决定是否合并主线。

## 8. 可直接发送给 WorkBuddy 的启动提示

```text
你接手的是 G:\myself\ai-career\AI Career OS 项目。先读取：
00-项目索引.md、00-当前状态.md、DECISION_LOG.md、05-QA-Gate.md、README.md、
docs/handoff/2026-10-11-workbuddy-handoff.md、
docs/evaluation/2026-10-09-问题汇总.md、
docs/evaluation/findings-and-backlog.md、
docs/evaluation/product-risk-acceptance.md。

当前基线是 main / 624de19（产品代码基线为 2ca4359），GitHub origin/main 已同步。不要直接在 main 开发，
从 main 创建 feature/workbuddy-next worktree。不要删除或提交主检出中的
apps/api/alembic/versions/014_interview_records.py 和 image/，也不要把旧 014
迁移混入当前 013 → 014_resume_studio → 015_interview_records 链。

先复现并修复 P0：经历四分类误判、中文学历抽取、must-have 召回、面经
 demo/CURATED 泄漏、参考回答事实污染。每个问题都要有脱敏 case ID、根因、
回归测试和真实浏览器/API 证据。不要编造真实用户、人工标签、成功率或模型结果；
缺少数据就标 NOT_RUN / NOT_EVALUABLE。完成后运行 Web 测试、API 测试、类型检查、
构建和浏览器路径验证，并更新 findings、risk acceptance、当前状态和 Project Tour。
```
