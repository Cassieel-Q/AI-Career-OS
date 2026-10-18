# AI Career OS v1.2｜可信求职闭环改版 · 最终报告

生成时间：2026-10-19（UTC+8）｜分支 `feature/trusted-workflow-v12`｜HEAD `1ea1c65`

---

## 1. Sprint 完成情况

| Sprint | 主题 | 状态 | 主要产出 |
|---|---|---|---|
| A | 事实可信（P0-1） | ✅ 完成 | 事实来源 / 用户核对 / 文案采纳三维拆分；确定性闸门；结构化参考答案；94 项事实安全用例 |
| B | 匹配与版本一致（P0-2） | ✅ 完成 | 单一匹配契约；输入指纹判过期；过期只标记不替换 |
| C | 首用三动作（P1-1） | ✅ 完成 | 首页单一主线；无模型建档；解析失败降级；**服务端档案恢复（本轮补接）** |
| D | 草稿 / 正式投递版分离（P1-2） | ✅ 完成 | 三级导出门禁；草稿水印 + `_DRAFT` 文件名；正式版落不可变快照 |
| E | 多岗位与面试版本一致性（P1-3） | ✅ 完成 | 逐岗位版本隔离；影响面提示 + 选择性同步；面试读**实际投递**的那版 |
| F | 专项测试与完整回归（P2） | ✅ 完成 | 全量回归 + 4 组专项 + 6 条真实浏览器主流程 35/35 + 隐私边界 |
| P3 | 目标用户研究 | ⚠️ **仅准备** | 招募 / 任务 / 观察模板；**无真实用户，不声称完成** |

**未合并 main**，main 未被改动。

---

## 2. 主要改动文件

### 后端（`apps/api/app/`）

| 文件 | 改动 |
|---|---|
| `fact_trust.py` | 事实来源 / 核对 / 采纳三维契约；`screen_text` / `screen_reference_wording` 确定性闸门（保守降级） |
| `fact_trust_schemas.py` `fact_trust_service.py` `fact_trust_routes.py` | 事实列表、核对记录、写回；**新增 `invalidate_changed_attestations`** |
| `fact_impact_service.py`（新） | `analyze_impact`（只读报告）/ `sync_mission`（一次只改一份） |
| `delivery_version_service.py`（新） | `record_snapshot`、`list_delivery_versions`、`resolve_interview_resume` |
| `resume_studio_service.py` | `export_checks(final=)` 三级门禁、`build_resume_filename`（含隐私清洗） |
| `resume_studio_routes.py` | 草稿 / 正式双通道 PDF、confirm 落快照、`interview-resume`、`delivery-versions` |
| `application_routes.py` | 绑定投递记录时同步落快照 |
| `proof_service.py` | 面试上下文改为走 `resolve_interview_resume`（投递快照优先） |
| `profile_service.py` | 事实变更后撤销旧签名 |
| `interview_provider.py` | 参考答案结构化契约 + 闸门（已知事实 / 待补 / 回答方法 / 示范表达 / 拦截原因） |
| `models.py` | 新增 `FactAttestation`、`DeliverySnapshot` |

### 前端（`apps/web/app/`）

| 文件 | 改动 |
|---|---|
| `page.tsx` | 单一主线 + **服务端档案恢复**（本轮补接） |
| `fact-check.tsx` / `fact-trust.ts` / `fact-impact.ts`（新） | 事实核对面板、影响面提示、「只更新这一份」 |
| `interview-version.ts`（新） | 面试版本横幅、投递版本选择 |
| `resume-studio/export-gate.ts`（新） / `api.ts` / `studio-page.tsx` | 门禁驱动的按钮与双通道下载 |
| `mission-page.tsx` | 面试版本提示 |
| `local-profile.ts` | 无模型建档与档案列表（本轮才被真正调用） |
| `globals.css` | 面板与横幅样式 |

### 测试

新增：`test_fact_trust.py`、`test_fact_safety_reference_answer.py`、`test_fact_edit_reverification.py`、`test_export_gate.py`、`test_export_privacy.py`、`test_match_contract.py`、`test_multi_job_version_consistency.py`、`test_local_profile_routes.py`；前端 `fact-trust.test.mts`、`fact-impact.test.mts`、`interview-version.test.mts`、`export-gate.test.mts`、`home-next-step.test.mts`、`local-profile.test.mts`。

### 评估资产

`docs/evaluation/trusted-workflow-v12/`（本目录八份文档）+ `browser/stub-llm-server.py` + `browser/e2e-trusted-workflow.cjs` + `browser/results/`（截图 11 张、PDF 2 份、`e2e-result.json`）。

---

## 3. 新增 / 修改的数据库迁移

| 迁移 | 表 | 用途 | down_revision |
|---|---|---|---|
| `028_trusted_facts`（新增） | `fact_attestations` | 只记录用户**明确核对**的行为；`fact_key` 稳定键 + `fact_text` 用于事实变更后重新判定 | `027_application_binding` |
| `029_delivery_snapshots`（新增） | `delivery_snapshots` | 正式投递版不可变快照（`document_json` + `content_hash` + `pdf_path` + `studio_revision`） | `028_trusted_facts` |

两处均写成幂等，重复执行不报错。`tests/test_alembic_revisions.py` 的链与 head 断言已同步更新。
迁移链：`… → 027_application_binding → 028_trusted_facts → 029_delivery_snapshots（当前 head）`。

**旧数据不批量升级**：`CONFIRMED / ACCEPTED / READY / SUPPORTED / DEFENDABLE / NEEDS_CONFIRMATION` 一律映射为 `UNREVIEWED`，只有显式的 `USER_ATTESTED` 才作数（有 8 项参数化用例守着）。

---

## 4. 测试：通过 / 失败 / 跳过

| 套件 | 通过 | 失败 | 跳过 |
|---|---|---|---|
| 后端 `pytest -q` | **1118** | **7** | **5** |
| 前端 `npm test` | **276** | 0 | 0 |
| 前端 `tsc --noEmit` | ✅ 退出码 0 | — | — |
| 浏览器 E2E（6 条主流程） | **35** | 0 | — |
| 离线基准（4 套件） | 4 × `COMPLETED` | — | — |

专项：事实安全 **94**（要求 ≥25）、匹配一致性 **34**（≥10）、版本一致性 **26**（≥10）、导出 / 恢复 **34**（≥10）。

---

## 5. 基线 vs 本轮失败对比

| 文件 · 用例 | 基线（main） | 本轮 |
|---|---|---|
| `test_claim_provider.py::test_claim_provider_normalizes_partial_claim_schema` | 失败 | 失败（一致） |
| `test_gap_analysis.py::test_gap_analysis_uses_confirmed_profile_and_allowed_states` | 失败 | 失败（一致） |
| `test_market_profile.py::test_market_profile_exposes_grounded_capability_clusters_without_discarding_atomics` | 失败 | 失败（一致） |
| `test_priorities.py::test_priority_algorithm_is_stable_and_caps_now` | 失败 | 失败（一致） |
| `test_resume_reliability.py::test_repeated_education_merge_preserves_optional_fields_and_courses` | 失败 | 失败（一致） |
| `test_roadmap.py::test_four_week_roadmap_is_persisted_with_actionable_tasks` | 失败 | 失败（一致） |
| `test_target_jobs.py::test_claim_analysis_fingerprint_requires_regeneration_after_profile_change` | 失败 | 失败（一致） |

**新增失败：0。** 判定方法：`git stash push -u` 后在基线重跑对比，再 `git stash pop`。这 7 项与本轮改动模块不重叠。

**本轮过程中出现过、已修掉的自身问题**（不留残余）：`sync_mission` 内容不落库、投递快照来源误判、桩模型路由导致 502/422、文件名泄露隐私、事实改了不撤销旧签名。

---

## 6. 真实 PDF 与浏览器验收证据

### PDF（`browser/results/`，PyMuPDF 抽文本核对）

| 文件 | 页数 | `DRAFT` 水印 | 姓名 | 说明 |
|---|---|---|---|---|
| `flow1-draft.pdf` | 1 | **有** | 无 | 文件名 `…_v1_DRAFT.pdf`，`%PDF-1.7`，52 KB |
| `flow1-final.pdf` | 1 | **无** | **有（陈林）** | 文件名 `陈林_招聘 AI 产品经理实习生_…_v3.pdf`，`%PDF-1.7`，52 KB |

### 浏览器（Playwright + Chromium，真实点击/填表/读页面文本）

6 条主流程 **35/35 通过**，截图 11 张。最能说明问题的几步：

- **缺姓名 → 409 `missing_name`**；**补了姓名但高风险事实未核对 → 409 `unconfirmed_fact:block`**；核对后才放行。两道门互相独立。
- 桩模型故意编造的「转化率提升 37%、日活三千到一万二、五人小组」**全部被闸门拦下**，参考答案降级为「证据不足，不能把这项动作或数字写入候选人的回答…」。
- 三份岗位简历，改一处共享事实后提示「**这项事实关联了 3 份岗位简历，其中 3 份可能需要更新**」；只更新选中的一份后，修订号 `3 / 2 / 1`，**另外两份没动**。
- 投递后又改 Studio，面试准备仍读 `delivered_snapshot`，投递后才加的那条内容**没有混进来**。
- 清掉 LocalStorage 后首页出现「已有档案」区块，可挑一份继续。

⚠️ 模型侧是**本地桩**（未授权真实模型付费调用），验证的是产品流程与前端行为，**不是模型输出质量**。

---

## 7. Git 状态

| 项 | 值 |
|---|---|
| 分支 | `feature/trusted-workflow-v12`（**未合并 main**） |
| HEAD | `1ea1c6541fa2bd8f2fc1107f0b3a0655076f66a0` |
| 本轮 commit | `41fef66`（事实签名失效 + 档案恢复 + E2E）、`1ea1c65`（文件名隐私） |
| 工作区 | 仅 `.workbuddy/memory/*` 两条工作日志改动，**无未提交代码** |
| main | 未被改动、未被合并 |

本分支相对 main 共 21 个 commit（含此前的模型中心工作），代码改动 87 个文件、+10958 / −264。

---

## 8. 需要你手工验收的步骤

自动化测不到的、必须人过一遍的：

1. **导出的两份 PDF 自己打开看一眼**（`browser/results/flow1-draft.pdf` / `flow1-final.pdf`）：草稿页上是否有肉眼可见的 DRAFT 标记；正式版排版是否正常、姓名在不在。
2. **用自己的真实简历 + 真实 JD 走一遍流程 1**（不要用我造的示例数据）。重点看：事实核对面板里「已核对 / 待核对」的划分是否符合你的直觉。
3. **确认一次「采用 AI 改写」不会变成「事实已核实」**：随便采纳一条改写，然后去事实核对页看它的状态是不是仍为「待核对」。
4. **故意把草稿 PDF 和正式 PDF 混在一起**，看你能不能在 3 秒内分清哪份能发。分不清就是问题。
5. **面试准备页**：确认它明确告诉了你「用的是投出去的那一版」；没投递时是否明说「尚无正式投递版本，当前使用准备中的简历」。
6. **清一次浏览器存储**（DevTools → Application → Local Storage → Clear），刷新首页，确认能找回档案。
7. **真实模型下重跑一次**（我没有授权，需要你配 Key）：桩模型不会编造，真实模型会。闸门在真实输出上的表现是 `NOT_RUN`。
8. **拍板 P1 缺口**：已确认档案改共享事实的入口太窄（见下），三个方案选一个，否则任务 5 的一半场景在真实环境走不通。
9. **跑用户研究**：模板已备好，但**一场都没跑**，不能对外说「用户验证过」。

---

## 9. 未解决的事实可信风险

按严重度排：

1. **【P1】已确认档案改共享事实的入口很窄，字段级同步在产品里够不到。** 确认简历来源会把档案升位到 `CONFIRMED`，之后 `PUT /profiles/{id}`、换文件、重新解析全部 409；唯一入口是「核对 + 写回」（`facts/attest` + `apply_to_source`），而它只写回描述类文本。`sync` 真正能更新的 `title / organization / dates` 因此**没有可达的改法**。我没有单方面改，因为 `tests/test_profiles.py::test_confirmed_profile_cannot_be_edited` 明确锁着这条规则。需要你拍板（见 `known-issues.md` 三个方案）。
2. **【P1】事实签名的比对文本不含时间。** 改经历的 `dates` 不会触发签名失效。修法是把 `dates` 纳入比对文本，但会改变事实核对面板显示的 `original_text`，属于可见改动，本轮没做。
3. **【P2】闸门是保守的，不是完备的。** 高风险词表与覆盖率阈值是经验值；查不出「有依据但被错误拼接」的表述；对抗样本没覆盖真实分布。**不做「未检出编造 ⇒ 系统不会编造」的推断。**
4. **【P2】离线基准 interview 套件仍有 5 次参考答案事实错误**（`reference_answer_fact_error_count=5`）。这 5 次是在**未开闸门**的对照路径上统计的，开闸门后对应对抗用例全部被拦；但基准脚本没把闸门接进去跑，所以这个数字目前只证明「模型会编造」，不能证明「产品放行了编造」。需要补一组开闸门的对照才有意义。
5. **【P2】人工维度 `UNRATED`、`adoption_rate=null`。** 自动指标不能冒充人工结论。
6. **【P3】目标用户研究零场次。** 任何「用户验证过」的说法都不成立。
7. **【P2】真实模型下的表现 `NOT_RUN`。** 真实模型调用 0 次，花费 ¥0。

---

## 附：本轮抓到并修掉的真问题（不是跑通了就完事）

| # | 问题 | 提交 |
|---|---|---|
| 1 | 参考回答编造候选人第一人称事实（交接文档 P10，本轮最严重的一项） | Sprint A |
| 2 | 改了事实，旧签名还在给新文本背书 | `41fef66` |
| 3 | 导出文件名带出手机号 / 邮箱 / `sk-` 形状密钥 | `1ea1c65` |
| 4 | `sync_mission` 只涨修订号、内容没变（SQLAlchemy JSON 原地修改不跟踪） | Sprint E |
| 5 | 有投递快照时仍被判成 `delivered_application` | Sprint E |
| 6 | 服务端档案恢复写了但没人接（清了存储就成新用户） | `41fef66` |
| 7 | 匹配分数 / 等级 / 建议三处口径打架 | Sprint B |
| 8 | 面试准备读的是最新 Studio 而不是投出去的那版 | Sprint E |
