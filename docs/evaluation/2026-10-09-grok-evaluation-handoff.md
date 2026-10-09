# TASK-EVAL-001｜AI Career OS 当前集成版系统化评测交接

> 接收方：Grok；交接日期：2026-10-09。本文可直接作为执行任务发送。目标是评测当前集成版产品，并在现有仓库内补足可复现的评测能力；不是重写产品或制造好看的测试结果。

## 1. 先确认评测对象

- 仓库：`https://github.com/Cassieel-Q/AI-Career-OS`。
- 本机当前有效工作树：`G:\myself\ai-career\.worktrees\aioscareer-combine`。
- 本机当前分支：`feat/aioscareer-combine`；审计时 HEAD：`dea66f0572b2ac3b19885e2b2d3eff0ec5a5144b`。
- 本地 `G:\myself\ai-career` 主检出有未提交内容；不要在那里直接开发，也不要清理或覆盖其 `image/` 原始素材。
- **上述提交是否已推送到 GitHub 未核实。** 如果你只能访问远程仓库，先比较远程 HEAD 与上述提交；若远程缺少当前集成版，报告“评测对象不可用”，索取当前分支或 Git bundle。不要拿远程旧版 `main` 充当本次评测对象。
- 开工前重新检查 `git status`、分支、HEAD、远程、未提交文件，并在当前有效提交上建立独立评测分支或 worktree。`feature/eval-benchmark-v1` 是建议名称，若已占用则按仓库约定另取名称。不要把本交接日期、提交号当作永久不变的事实。

优先阅读：`AGENTS.md`（若存在）、`00-项目索引.md`、`00-当前状态.md`、`DECISION_LOG.md`、`README.md`、`05-QA-Gate.md`、`docs/qa/combine/2026-10-08-integration-qa.md`、`docs/qa/combine/2026-10-09-resume-ui-content.md`。`docs/release/final-project-manifest.md` 是 **2026-09-28 的历史发布快照**，可作背景，不是本次代码基线。

### 当前代码入口，已在上述本地提交核对

| 领域 | 当前入口 |
|---|---|
| Web 产品主线 | `apps/web/app/missions/`；岗位 `/missions/[missionId]/role`、简历 `/missions/[missionId]/resume`、模拟面试 `/missions/[missionId]/interview`、结果 `/missions/[missionId]/outcome` |
| 简历工作台 | `apps/web/app/missions/[missionId]/resume/studio`，页面逻辑在 `apps/web/app/resume-studio/` |
| 真实面试记录库 | `apps/web/app/interview-records/`；独立于模拟面试会话，可关联岗位任务 |
| 岗位任务与定向简历 API | `apps/api/app/mission_routes.py`、`mission_service.py`、`mission_provider.py`、`mission_schemas.py` |
| JD 分析 | `apps/api/app/jd_analysis_provider.py`、`job_description_service.py`、`job_description_routes.py`；确认真正的主流程调用链后再选评测入口 |
| PDF 上传与事实确认 | `apps/api/app/mission_routes.py` 中 `/job-missions/{id}/resumes`、`/resumes/text`、`/confirm-resume-source`；Web 逻辑在 `mission-page.tsx`、`mission-profile-confirm.tsx` |
| 经历筛选和改写 | `/job-missions/{id}/experience-selection/generate`、`/resume-strategy`、`/target-resumes`；定向改写接收与编辑经 `/target-resume-bullets/{id}` |
| 简历工作台与 PDF | `apps/api/app/resume_studio_routes.py`、`resume_studio_service.py`、`resume_studio_render.py`；当前工作台提供预览、修订确认及 PDF 下载 |
| 模拟面试 | 预览包由 `/job-missions/{id}/interview-pack` 生成；真实会话端点在 `apps/api/app/proof_routes.py`，即 `/resume-claims/{id}/interview-sessions` 与 `/interview-sessions/{id}/turns`；Web 调用在 `apps/web/app/proof-flow.ts` |
| 面试记录 | `apps/api/app/interview_record_routes.py`、`interview_record_service.py` |
| 知识包 | `knowledge/interview_skills/`、`knowledge/interview_skills/curated/`、`knowledge/resume_skills/` |
| 旧评测 | `evals/README.md`、`evals/schema.py`、`evals/seed_cases.json`、`apps/api/tests/test_v02_evals.py` |

`/workflow/...`、`/proof/...` 仍有旧路由和部分模拟面试底层实现，但浏览器验收应从 `/missions` 主线进入，避免把旧页面误当新产品。当前产品阶段以代码为准：岗位 → 简历 → 模拟面试 → 结果；面试记录库另有入口。简历阶段含原始简历绑定、事实核对、经历筛选、岗位定向改写、人工接受/编辑、Resume Studio 精修、修订确认与 PDF。后台的证明、补强、Claim 环节应按实际触发条件检查，不强行套入旧线性流程。

## 2. 评测目的与不可逾越的边界

用可复现、可审计、有人类标准答案及通用 LLM 基线的评测回答：

1. 不同公司 JD 的身份、职责、必备与加分要求是否读对？
2. 同一份真实简历面对不同岗位时，经历四分类是否正确，关键项目是否被遗漏？
3. 项目改写是否真实、岗位相关、信息充分、可采纳；多要点、技能分类与 PDF 是否保真？
4. 相比直接把 JD 和简历交给同一基础模型，产品的分步工作流与人工确认是否带来可测价值？
5. 模拟面试的题目、追问、评分、参考回答和面经引用是否有依据？
6. 用户能否从 JD 到确认 PDF、模拟面试、复盘，再到真实面试记录完成任务？
7. 失败案例对应哪个具体服务、提示词、交互或事实门槛，如何转成可复验的改进任务？

**禁止编造**测试数据、人工标签、评价者、真实用户、反馈、成本或成功率。测试通过数、合成案例结果、模型自评、目标阈值和真实产品效果必须分开报告。缺少模型密钥、授权简历、人工标注或真实用户时，用 `NOT_RUN` / `NOT_EVALUABLE` 标示，并说明缺口；不可填入“通过”。不修改原始真实简历、用户历史记录和生产数据；个人信息、原始模型输出和浏览器录屏进入 Git 忽略的隔离目录，报告仅放脱敏摘要与受控证据引用。

## 3. 第一阶段：仓库审计与评测器口径修正

先生成 `docs/evaluation/implementation-audit.md`，逐项记录：当前实际流程、可复用 service / provider / API、线上调用点、已有离线回归、拟增文件、数据库迁移必要性、密钥及隔离数据要求。按“已实现 / 需要扩展 / 未运行”区分，附文件和行号。

已知要核查的旧评测缺陷：`evals/schema.py` 的 `compare_case(case, actual=None)` 使用 `actual = actual or expected`，`compare_cases()` 又会给缺失案例传入 `None`。因此 `test_v02_evals.py` 中 15 个样例通过，不能解释为真实模型输出通过。先把缺失实际结果明确记为 `NOT_RUN`，空对象不得回退到预期；增加能捕捉此问题的回归，再使用它作离线评测。保留旧样例作为确定性夹具，不得写成真实质量数据。现有三项全量 API 测试失败在集成前基线已复现，详情见 `docs/qa/combine/2026-10-09-resume-ui-content.md`；新评测如触及相关逻辑须单列验证，不能静默忽略，也不能归咎于本次改动。

## 4. 数据集与人工标准答案

以下是**目标规模，不是现成样本或已完成指标**。先做数据清单和缺口表，再开发可用部分；未凑齐样本时报告实际覆盖量。

| 单位 | 目标 |
|---|---:|
| 来源可追溯的独立 JD | 30 |
| 不同简历 | 10 |
| 每份简历匹配的预选代表 JD | 3 |
| JD × 简历匹配任务 | 30 |
| 每任务重点改写经历 | 3 |
| **经历级**改写审阅单元 | 90 |
| 代表性模拟面试案例 | 10 |
| 每案例主问题 | 5 |
| 主问题评估单元 | 50 |
| 真实可用性参与者 | 5 |

30 份 JD 用于解析；从中**事先固定相同的 3 份代表 JD**，每份简历均与它们配对，不看输出后挑容易的岗位。90 个改写单元按“经历/项目”计，而不是按最终 PDF bullet 计：当前产品将同一项目的多条模型建议合为一份可审阅建议，Studio 再拆成多个要点；每个单元保存建议文本、拆分后的 bullet 数、事实来源和采纳状态。若事实不足，少于 2–4 个 bullet 不自动判失败，重点看是否编造。

建议在现有 `evals/` 下新增 `benchmark/`，如 `schemas/`、`manifests/`、`annotations/`、`baselines/`、`reports/`；**这些目录和下面 CLI 均为待实现建议，并非仓库现有能力**。将公开或明确授权的脱敏材料与私有样本分开。每份 JD 记录 `jd_id/company/role_title/role_family/source_url/collected_at/raw_text/annotation_status`；每份简历记录 `resume_id/source_type(synthetic|consented_real)/consent_status/experiences/skills/education/verified_facts`；每条经历有稳定 ID，例如 `resume-003-exp-004`。匹配案例记录 `case_id/jd_id/resume_id/expected_high_priority_experience_ids/experience_labels/selected_rewrite_experience_ids`。外部 JD 的 `source_url`、抓取时间、快照哈希与使用范围要可审计；不可用时明确写缺失，不造来源。

先写 `docs/evaluation/annotation-guidelines.md`：

- JD：公司、岗位、地点、年限、学历、职责、必备/加分/非技术要求，每条保留原文证据，并区分 `required / preferred / inferred`；推测不当原文事实。
- 经历筛选：使用代码真实枚举 `KEEP_AND_HIGHLIGHT / KEEP / DEEMPHASIZE / OMIT`，中文含义分别为重点展示、保留、弱化、暂不放入。每条记录 JD 对应要求、简历证据、理由、优先级、评价者 ID；关键项目被误 `OMIT` 单记 `CRITICAL_SELECTION_ERROR`。
- 改写：事实真实性、JD 匹配、重要信息完整性、清晰度、可采纳程度各 1–5 分；另记虚构数字/职责/工具、关键事实改变、重要经历遗漏、人工编辑次数和计时时长。先判事实，关键事实未经确认不可标“直接可采纳”。人工接受文案和事实确认是不同状态。
- 面试：每题记录 JD 依据、已确认简历依据、面经包 ID / 来源、重复情况和评分依据；参考回答中的未经证实事实单独判错。来自其他公司的面经不能显示成目标公司的真实面经，合成 Demo 包不能当作真实面经。
- 标注质量：优先两名独立评价者；资源不足时至少 20% 重叠标注并报告实际比例、Cohen's Kappa 或适用的一致性/评分差异；保留初标、争议、裁决。只有一人时标 `single_rater`。

## 5. 自动化评测套件

所有套件保存 `run_id`、代码提交、数据 manifest/hash、提示词版本、模型/版本、参数、时间戳、执行模式、输入 ID、原始输出受控位置、结构化输出、失败类型、延迟、token、评分人与评分版本。实际输出缺失是 `NOT_RUN`；超时/非法 JSON 是失败；人工未打分是 `UNRATED`。评测器只读既有输出，不得自行生成“预期输出”。

### EVAL-JD：岗位解析，目标 30 份独立 JD

逐字段报告公司、岗位、地点、年限、学历的准确率/完整率，职责与必备要求 Precision、Recall、F1，无依据要求生成率，结构化输出有效率，请求失败率，P50/P95 延迟。技能可做语义匹配，但匹配证据须留存并人工抽检；不能仅用同一个 LLM 自评。核对人工更正岗位身份后的后续任务是否使用更正值。

### EVAL-MATCH：经历四分类，目标 30 组

计算整体准确率、Macro-F1、每类 Precision/Recall、`KEEP_AND_HIGHLIGHT` 召回、关键项目错误 `OMIT` 率、无依据新增经历率，并输出混淆矩阵。经历 ID 与来源证据绑定；排序变化不能改变标签对齐。单列同一简历跨 3 个岗位的选择差异，避免所有岗位输出同一排序。

### EVAL-REWRITE：目标 90 个经历级单元

报告五维人工均分、直接采纳率、关键事实错误率、无依据数字率、重要事实遗漏率、平均生成耗时、token 与可验证的 API 成本。对一个项目的多个 bullet 分别检查来源和事实；同时核对审阅页合并建议、Studio 拆分要点、导出 PDF 中保留原意与顺序。抽检技能归类（产品 / AI 产品 / 技术工具 / 语言等）、紧凑横向排版、重复技能、遗漏技能和技能熟练度是否被夸大。`UNSUPPORTED` / `NEEDS_CONFIRMATION` 要点、未完成作品集项目不得在未确认事实前进入正式 PDF。LLM-as-Judge 仅作辅助列，不能替代人工事实判定。

### EVAL-INTERVIEW：目标 10 案例、50 道主问题

检查岗位相关率、已确认简历相关率、去重、无依据事实引用率、同公司真实面经引用准确率、问题能力覆盖、逐题评分/参考回答/补强建议的合理性。对每案例提供至少不同质量的**合成模拟回答**来验证追问是否随回答调整，保存每轮上下文；不得把首题相关性当追问能力。合成回答不记为真实用户。实际会话轮数和上限按当前代码及运行配置记录，不把“5 题目标”冒充每次真实模型都必然完成 5 题。检查面试引用的是最新已确认 Studio 修订，旧任务回退逻辑另列。

### EVAL-E2E：浏览器真实路径与异常路径

从 `/missions` 建立岗位并粘贴 JD → 解析并更正岗位身份 → 选择 Master Resume / 上传本岗位 PDF / 粘贴文本 → 核对来源事实 → 确认经历筛选 → 生成、接受/编辑定向改写 → 确认岗位版本 → 进入 `/missions/{id}/resume/studio` → 选择模板、修改、核对事实、确认当前修订并下载 PDF → 进入模拟面试、提交答案并查看评分/复盘 → 在 `/interview-records` 建立或查看真实面试记录。区分“模拟面试历史”与“用户自己记录的真实面试”，不能把后者说成模拟会话自动创建。

每步保存 `step_name/status/duration_ms/error_type/retry_count/evidence_reference/browser_url`。重点异常：扫描版或空白 PDF、过大文件、空 JD、非法 JSON、超时、重复点击、刷新/会话恢复、换简历来源后旧改写、Studio 新旧来源差异和显式 reimport、陈旧 `If-Match`、编辑后未重新确认即导出、未确认事实即导出、缺 Typst/字体、3 页溢出、PDF 文本无法抽取、手机窄屏布局。执行成功需浏览器动作、持久化记录、真实下载文件及 PDF 文本/页数证据；API 单测不等于 E2E。真实参与者另按任务完成率、阻塞点和人工观察记录，未招募则 `NOT_RUN`。

## 6. Direct LLM 对照

对同一 JD、同一原始简历、同一基础模型与版本运行：A 组用预先冻结的 `direct_llm_prompt.md` 直接生成岗位定向简历；B 组走 AI Career OS 的 JD 解析、筛选、改写、事实确认和 Studio 流程。尽量固定生成参数，保留双方完整 Prompt 和输出；人工评委在盲态下按同一标准逐对评价。不要看结果后只为 A 或 B 修改提示词；需要改版则新增版本并重跑双方。

比较事实准确性、JD 匹配、关键经历保留、直接采纳、人工修改次数与**真实计时**、生成延迟、token 和可核验成本。明确把 B 组人工操作耗时计入端到端时间，同时可另报纯模型延迟。输出每案例配对差值、均值与样本分布；小样本不夸大显著性。这只是产品工作流对照，不是招聘录用率实验。

## 7. 指标、CLI 与交付

`precision = TP/(TP+FP)`，`recall = TP/(TP+FN)`，`F1 = 2PR/(P+R)`；`adoption_rate = 人工直接采纳数/已完成有效评分的改写数`；`critical_error_rate = 有关键事实错误数/成功生成且完成事实检查数`；`completion_rate = 完成全部关键步骤的有效用户会话数/有效用户会话数`。延迟与人工编辑节省率分别用配对 `(A-B)/A` 计算，分开报告。每项给出分子、分母、缺失和排除原因；零分母返回 `null` / `NOT_EVALUABLE`，绝不能默认为 100%。区分计划数、实际执行数、生成成功数、有效评分数、失败数和未评分数。

建议命令接口如下；**不是已存在命令**，先依赖审计，再实现或合理调整并更新 `evals/README.md`：

```powershell
python -m evals.benchmark.validate
python -m evals.benchmark.run --suite jd --mode offline
python -m evals.benchmark.run --suite match --mode live
python -m evals.benchmark.run --suite rewrite --mode live
python -m evals.benchmark.run --suite interview --mode live
python -m evals.benchmark.run --suite all --mode offline
python -m evals.benchmark.run --suite rewrite --mode baseline
python -m evals.benchmark.report --run-id <RUN_ID>
```

`offline` 只跑固定输入与评测器回归，严禁调用真实 provider；`live` 明确调用项目当前 provider/service，保存实际返回；`baseline` 用独立冻结 Prompt；`report` 只汇总既有运行，不重新调用模型。支持运行中断恢复、幂等 run ID、失败重试记录、密钥缺失安全退出。旧 `evals/README.md` 目前只说明 15 个合成样例；新说明应写清楚数据隐私、运行模式和结果口径。

交付至少包含：

1. `docs/evaluation/implementation-audit.md` 与 `annotation-guidelines.md`。
2. 可校验的数据 schema / manifest、实际样本清单和授权/合成比例；敏感原始材料不得提交。
3. 已实现的离线、在线、基线 runner、指标计算、缺失状态和有意义的回归测试。
4. 运行报告：各套件指标、样本分母、混淆矩阵、失败案例、对照差值、证据索引和明确 `NOT_RUN` 项。
5. `docs/evaluation/findings-and-backlog.md`：每个高优先级失败给出 case ID、复现步骤、根因假设、产品改进建议、验收标准；区分证据与推断。
6. 浏览器 E2E 与 PDF 证据，以及真实用户可用性测试记录或未执行原因。
7. 变更文件、迁移情况、复现命令、Git 分支/提交、测试结果和剩余风险。若创建 PR，附 PR 链接。

## 8. 现有验证与本次特别关注

最新集成 QA 记录：Web `194/194` 测试通过，类型检查和构建通过；API `614 passed / 5 skipped / 3 failed`，三项失败在旧基线复现；虚构简历的 Typst PDF 实际渲染与 22 个技能保留检查通过。10 月 8 日 QA 还记录过真实模型的三题面试和**固定服务替代提问**的五题浏览器流程，这两类证据必须分开。以上全是工程验证，不是本次 30 JD、90 改写或 5 真实用户的产品效果。

特别关注：一处历史 QA 曾发现 AI 参考回答把“分析 50 篇内容”说成“访谈 50 位创作者”；本轮应检查参考回答事实污染。另有旧来源档案预览和 Studio 投递版预览的数据源差异；评测时明确取哪个版本，确认后不让旧预览误导结论。PostgreSQL 旧库全链升级与外部部署仍未验证，隔离 SQLite 迁移回归不能替代生产库验收。

## 9. 执行顺序与停止条件

先核对目标提交 → 写审计和数据可用性表 → 修评测器自比较口径 → 写标注规范与 schema → 用合成夹具跑离线回归 → 有授权样本和配置后跑 live / baseline → 浏览器与 PDF 验证 → 人工评分及一致性 → 报告与失败任务。每阶段提交可复现证据，不要等全部样本凑齐才暴露工程问题。没有用户授权、真实用户或 live 密钥时继续完成可独立完成的工程与离线工作，把依赖项标为 `NOT_RUN`；不得假装做完。若 GitHub 没有当前集成提交，先停止对旧版的产品效果评判并报告缺失基线。

最终回答先给一张表：评测对象提交、各套件计划/实际/有效样本数、真实模型调用情况、人工评分情况、真实用户情况、发现的最高风险。随后给证据路径、指标口径、可复现命令、优先级最高的 3–5 个改进任务及剩余未验证项。
