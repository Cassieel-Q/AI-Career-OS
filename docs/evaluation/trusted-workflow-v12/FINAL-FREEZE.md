# AI Career OS v1.2 · FINAL FREEZE 最终交付报告

> 生成时间：2026-10-19
> 分支：`feature/trusted-workflow-v12`　HEAD：**`57972e8`**
> 本报告里的每个数字都来自本轮真实执行。**没有跑过的项一律标 `NOT_RUN`，没有人工金标准的项一律 `UNRATED`。**
> 旧文档（`test-results.md`、`final-report.md`）里的数字对应更早的 HEAD，不要与本报告混用。

---

## A. 最终能力（这个版本到底能做什么）

**一句话**：针对一个真实岗位，拿到一份事实可核对、版本可辨认的投递简历，并用真正投出去的那一版准备面试。

### A1. 三件事严格分开，互不推导

| 概念 | 含义 | 怎么才算成立 |
| --- | --- | --- |
| 事实来源 | 系统提取到 / 用户填写 / AI 建议 | 只看 `fact_attestations.source_kind` |
| 用户核对 | 待核对 / 你已确认属实 / 已标记不属实 | **只有你点过「确认属实」**才算，档案「已确认」不算 |
| 文案采纳 | 采用 AI 改写 | 不等于核实事实 |

### A2. 由此产生的硬规则

| # | 规则 | 验证方式 |
| --- | --- | --- |
| 1 | 采用改写 ≠ 核实事实。点「采用改写 / 下一步 / 生成简历」不会把任何事实变成已核实 | `test_fact_trust.py`；E2E 流程1 两次独立 409 |
| 2 | 草稿与正式投递版分离：草稿带 `DRAFT` 水印、文件名含 `_DRAFT`，永不被标记为已投递 | E2E 流程1；PDF 实物核对 |
| 3 | 正式投递版必须通过导出自检：缺姓名、**未核对的高风险事实**会拦截（表达建议只提醒） | E2E 流程1（409 `missing_name` / 409 `unconfirmed_fact:block`） |
| 4 | 改共享事实会提示「关联 N 份，其中 M 份可能需要更新」，由你逐份选择，**绝不自动改** | E2E 流程3 / 流程7 |
| 5 | 历史投递快照不可变（独立 JSON + SHA-256），改 Studio 不影响已投出去的版本 | E2E 流程4 / 流程7 哈希比对 |
| 6 | 已确认档案不能整体覆盖（`PUT` 仍 409），但可在事实核对里**受控修正**单项 | E2E 流程7（409 + 受控修正 200） |
| 7 | 面试准备默认读**真正投递出去的那一版**，不是最新 Master/草稿 | E2E 流程4（`source=delivered_snapshot`） |
| 8 | 分析过期**只标记不替换**：标「可能过期」并给原因，不静默重算、不伪装新鲜 | `test_target_jobs` 新契约 |

### A3. 用户可见的功能面

- 建档与简历原文编辑（**无模型也能用**本地规则解析）
- JD 导入与岗位识别、多岗位并行（同一份简历关联多个岗位，版本互不影响）
- 岗位定向简历生成、改写要点逐条接受/编辑、Studio 排版（**18 套模板**）
- 事实核对（经历/技能）、影响面提示、定向同步
- 模拟面试、参考回答、事实闸门降级、面试记录/面经
- 投递记录与状态推进、投递快照、AI 模型中心（不改 `.env` 也能配置）
- 助手「顺顺」、简历中心、设置
- Windows 一键安装 + 桌面图标启停（production 模式，自动避开被占用端口）

---

## B. 两个 P1 的修复结果

### B1. P1-A｜已确认档案的字段修正（选定方案 2）

**方案**：保留 `CONFIRMED` 的整体锁定，只允许**受控单项修正**。

| 要求 | 实现 | 证据 |
| --- | --- | --- |
| 不开通用 `PUT` 口子 | `PUT /profiles/{id}` 对 `CONFIRMED` 仍返回 **409** | E2E 流程7；`test_controlled_fact_correction` |
| 支持 标题 / 组织 / 起止时间 / 描述 | 白名单 `CONTROLLED_FIELDS`：经历 `title/organization/dates/description`，技能 `name` | 同上 |
| 必须显示 旧值 / 新值 / 影响范围 | 响应 `field_changes: [{field, old_value, new_value}]`，页面显示「原值：X → 新值：Y」 | E2E 流程7 `old=2025.03 → new=2025.03-2025.09` |
| 用户明确确认后才写入 | 必须 `apply_to_source=true`；不带写回的核对**不会**改原始事实（状态仍 `UNREVIEWED`） | 19 项新测试中的 3 项 |
| 撤销旧核对并留清晰新记录 | 修正后重算签名并写入新的核对记录 | `attest_fact()` + `lock_legacy_signatures()` |
| 相关岗位版本提示「可能需要更新」 | 影响面接口返回「这项事实关联了 3 份岗位简历，其中 3 份可能需要更新。」 | E2E 流程7 |
| 只写用户选中的那一份 | `POST /facts/{kind}/{id}/sync` 带 `mission_id`，`changed=true`，其余不动 | E2E 流程3 / 流程7 |
| 历史投递 PDF 与面试快照引用不变 | 快照 `content_hash` 前后一致（`2b1f81732949` → `2b1f81732949`） | E2E 流程7 |
| 白名单外字段必须被拒 | `field_updates: {full_name: ...}` → **422** | E2E 流程7 |
| 不为了「能改」而移除所有 `CONFIRMED` 限制 | 整体 `PUT` 409 保持 | 同上 |

**新增测试**：`apps/api/tests/test_controlled_fact_correction.py`（**19 项，全通过**）。
既有编辑保护测试仍然有效。

### B2. P1-B｜时间进入事实签名

**问题**：`fact_trust_service` 的签名不覆盖 `dates`，改起止时间后旧 `USER_ATTESTED` 仍在背书。

| 要求 | 实现 |
| --- | --- |
| 标题 / 组织 / 起止时间 / 描述 全部触发失效 | 新增 `signature_text` 列（`\x1f` 连接四字段） |
| 内部签名与页面展示文本分离 | `signature_text` 只用于判定；`fact_text` 仅展示 |
| 保守的存量迁移，不批量升级 | `lock_legacy_signatures()` 在**改动前**为旧行锁存当前签名；`signature_text IS NULL` 的旧行按「展示文本仍一致」判定，命中时补写 |
| 不自动升级缺历史的字段 | 无历史的行不会被批量置为已核对 |

**验证链路**（`test_controlled_fact_correction.py`）：已核对 → 改起止时间 → 失效/需重新核对 → 影响面提示 → 只同步选中的岗位 → 旧快照不变。

**迁移**：`apps/api/alembic/versions/030_fact_signature.py`（`down_revision=029_delivery_snapshots`，幂等）。
`test_alembic_revisions.py` 已同步链定义与 head 断言。

---

## C. 最终测试（真实结果）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `apps/api: pytest -q`（`AI_CAREER_DATA_DIR` 隔离） | **1140 passed / 6 failed / 5 skipped**（259.63s） |
| 前端单测 | `apps/web: npm test` | **276 passed / 0 failed** |
| TypeScript | `apps/web: npm run type-check` | **0 error** |
| 生产构建 | `apps/web: NEXT_PUBLIC_API_BASE_URL=… npm run build` | **EXIT=0**（编译 + 类型检查通过） |
| 浏览器 E2E | `node …/e2e-trusted-workflow.cjs`（跑在 production 构建上） | **43/43 通过**，7 条主流程 |
| 闸门 A/B 重放 | `python evals/benchmark/scripts/gate_replay.py` | 见 `gate-replay.md`，**模型调用 0 次** |
| PDF 实物 | PyMuPDF 抽文本 | 见下表 |
| 档案恢复 | E2E 流程5（清 LocalStorage） | **通过**，服务端列表可用，不需要记 UUID |
| 备份 / 恢复 | 真实 API 导出 → inspect → restore → 激活 → 比对计数 | **通过**，105,631 B，计数完全一致 |

### C1. 与基线对比

基线（`main` `a033b21`）后端 **7 项**失败 → 现在 **6 项**：修掉 1 项，**新增失败 0**。

修掉的正是本轮被点名的那一项：

| 用例 | 基线 | 现在 |
| --- | --- | --- |
| `test_target_jobs::test_claim_analysis_fingerprint_requires_regeneration_after_profile_change` | FAILED | **PASSED（已改造）** |

> 旧断言要求 409，实现却是「静默刷新指纹」——等于把旧分析伪装成新鲜结果。已改为
> **只标记不替换**（返回 `stale=True` + 原因），并补了「空主张仍必 409」的对照用例。

### C2. 剩余 6 项失败：风险分类（不隐藏）

| 用例 | 失败原因 | 影响事实可信 / 投递版本 / 数据安全？ | 结论 |
| --- | --- | --- | --- |
| `test_claim_provider::test_claim_provider_normalizes_partial_claim_schema` | 降级文案断言（`做过` 前缀 vs 原句） | 否 | 保留在已知问题 |
| `test_gap_analysis::test_gap_analysis_uses_confirmed_profile_and_allowed_states` | 能力簇名称本地化后找不到英文键 | 否 | 保留 |
| `test_market_profile::…grounded_capability_clusters…` | 期望英文 `Technical capability`，实际中文 `技术能力` | 否 | 保留 |
| `test_priorities::test_priority_algorithm_is_stable_and_caps_now` | 期望 `Product execution`，实际 `产品落地` | 否 | 保留 |
| `test_resume_reliability::test_repeated_education_merge_preserves_optional_fields_and_courses` | 教育经历去重合并后条数 2 ≠ 1 | 否（解析质量） | 保留 |
| `test_roadmap::test_four_week_roadmap_is_persisted_with_actionable_tasks` | 同能力簇中文/英文标签 | 否 | 保留 |

其中 4 项同根因：能力簇名称已本地化成中文，测试仍断言英文。属历史遗留的**断言口径**问题，
不影响用户可见功能，也不触碰事实签名 / 投递版本 / 数据安全。

### C3. PDF 实物核对（2026-10-19 12:45，PyMuPDF）

| 文件 | 页数 | 大小 | 含 `DRAFT` 水印 | 含姓名 |
| --- | --- | --- | --- | --- |
| `flow1-draft.pdf` | 1 | 59,790 B | **是** | 否（草稿下载发生在补姓名之前） |
| `flow1-final.pdf` | 1 | 59,978 B | **否** | **是（陈林）** |

两份都是真实 PDF（`%PDF-1.7`）。PDF 内出现的姓名/手机/邮箱/学校均为**合成数据**
（陈林 / 13800000000 / chenlin@example.com / 示例大学）。

### C4. 17 条主流程覆盖

| # | 主流程 | 证据 | 结果 |
| --- | --- | --- | --- |
| 1 | 无模型建档与简历原文编辑 | E2E 流程6；`test_local_profile_routes` | PASS |
| 2 | 测试 JD 导入 | E2E 流程1 / 流程3 | PASS |
| 3 | 岗位匹配及建议一致性 | `test_match_contract.py` | PASS |
| 4 | 事实提取 / 用户核对 / 采纳状态分离 | `test_fact_trust.py`；E2E 流程2 | PASS |
| 5 | 经历字段受控修正 | `test_controlled_fact_correction.py`（19 项）；E2E 流程7（8 项） | PASS |
| 6 | 修改事实后相关分析过期 | 本轮修复；`test_target_jobs` 新契约 | PASS（本轮修复） |
| 7 | 三个岗位版本互相隔离 | E2E 流程3；`test_multi_job_version_consistency.py` | PASS |
| 8 | Studio 18 套模板可用 | `list_templates()` → **18**；`test_template_layout.py` | PASS |
| 9 | 草稿 PDF 含 DRAFT 标识 | E2E 流程1；PyMuPDF 核对 | PASS |
| 10 | 正式投递 PDF 通过事实与导出检查 | E2E 流程1（缺姓名 409 → 补姓名 → 通过） | PASS |
| 11 | 修改 Studio 后历史投递 PDF 不变 | E2E 流程4 / 流程7；快照哈希比对 | PASS |
| 12 | 面试使用对应投递版本 | E2E 流程4（`source=delivered_snapshot`） | PASS |
| 13 | 清 LocalStorage 后可恢复档案 | E2E 流程5 | PASS |
| 14 | 顺顺 `list_jobs` / `list_applications` | `test_assistant_write_proposals.py` | PASS |
| 15 | 模型中心既有配置不回归 | `test_model_config.py` | PASS |
| 16 | 桌面图标启动应用 | 2026-10-19 12:48–12:56 实跑 | PASS（见下） |
| 17 | 数据备份与恢复不丢资料 | 真跑：导出 105,631 B → 恢复为新数据集 → 计数一致 | PASS |

### C5. 桌面启停实跑（2026-10-19）

```text
career-app.ps1 -Action status → 后端/前端/浏览器桥 未运行，模式 production
career-app.ps1 -Action start  → 浏览器桥 8770 就绪
                               → 后端 8100 就绪（/health 探活通过，数据目录 %LOCALAPPDATA%\AICareerOS）
                               → 前端 production 自动落到 3002（3000/3001 已被其它项目占用，未强抢）
                               → Edge 独立窗口打开 http://127.0.0.1:3002
career-app.ps1 -Action stop   → [OK] 已停止（其他项目的服务未受影响）
复查端口：本项目 8100/3002/8770 全部释放；其它项目的 3000 与 8000 仍在监听（未被误杀）
```

> 注：启动器拉起的进程会随本工具会话结束被回收，所以 HTTP 探测以启动器自带的就绪探活为准；
> 真实使用时由 Explorer 双击启动，进程常驻。更完整的 start → start → stop → start 序列验收
> 是 2026-10-17 的记录：**17/17 通过**（`docs/evaluation/boss-local-app/launcher-test.json`），
> 启动器本轮未改动。

### C6. 安全检查结果（任务四）

| 检查项 | 结果 |
| --- | --- |
| 是否提交了 API Key | **否**（`sk-` / `ghp_` / `AKIA` / `xoxb-` / `AIza` 全库扫描 0 命中） |
| 公开测试资产是否含真实简历/手机/邮箱/身份证 | **否**（扫描 0 命中真实号码与真实邮箱；身份证模式 0 命中） |
| 是否有未脱敏截图 | **否**（E2E 全部使用合成数据：陈林 / 13800000000 / chenlin@example.com / 示例大学） |
| 合并是否会重新引入敏感历史的 Git 对象 | **否**（分支与 `main` 的关系是快进，见 D） |
| 仓库里是否有真实用户数据库 | **否**（`.db`/`.sqlite` 均未被跟踪；`.runtime/` 在 `.git/info/exclude`） |
| 是否含带密钥的备份 | **否** |
| 模型配置是否经公开前端 API 泄露密钥 | **否**（模型配置接口只返回 `key_masked` 等元数据） |
| `D:\ai-career-backup-20261017.bundle` | **未纳入 Git、未上传**（含隐私历史，保留不删） |

---

## D. Git 状态

| 项目 | 实际值 |
| --- | --- |
| 当前分支 | `feature/trusted-workflow-v12` |
| HEAD | **`57972e8`**　`chore(freeze): 隐私脱敏 + 最终回归记录 + E2E 缺陷修复` |
| HEAD 的父提交 | `684a163`（P1-A / P1-B / 主张分析只标记不替换 / 闸门 A/B 重放） |
| `main` | `a033b21` |
| 与 `main` 的关系 | `merge-base(HEAD, main) == a033b21 == main HEAD` → **`main` 是 HEAD 的祖先，合并为快进** |
| 领先 `main` | 24 个提交 |
| 工作区 | **干净**（`git status --porcelain` 为空） |
| 是否强推过 | **否**（本轮未强推任何分支，未 force-push `main`） |

### D1. 隐私历史检查（既有 filter-repo 清理是否仍有效）

- **分支 HEAD 的树是干净的**：`git grep '潘佳琪' HEAD` → 0 命中（本轮 `57972e8` 清掉了 9 处）。
- **`main` 当前的树不干净**：仍有 9 个文件含真实姓名（`.workbuddy/memory/2026-10-17.md`、
  `apps/api/app/main.py`、3 个前端测试夹具、3 个文档、`apps/api/tests/test_profile_contacts.py`）。
- **历史提交里也存在**：`daf50ff`、`3e7ca60` 等仍含该姓名。
- 因此本轮做了一次**树级脱敏**（HEAD 干净），但**历史级脱敏尚未完成**。

**合并安全性结论**：把 `57972e8` 合并进 `main` 是**快进**，不会重写历史、不会重新引入
`git-filter-repo` 已抹掉的截图对象；合并后 `main` 的**当前树**会变干净。
但**历史里的真实姓名仍在**，需要再跑一次 `git-filter-repo` + 强推才能根除。

> **本轮不自行强推。** 按指令，这是明确的**发布阻塞**：在历史级清理完成前，
> 请不要把本仓库设为公开。

---

## E. 未完成项（如实记录，分四类）

### E1. 不影响正常使用

| 项 | 状态 |
| --- | --- |
| 后端 6 项历史断言失败（能力簇中英文标签等） | 已知，不触碰事实/投递/数据安全，保留 |
| 确定性闸门对「没数字、只是前提不成立」的动作类主张仍漏放（15 条里 4 条） | 边界已固化成测试；**未调阈值**（0.79–0.80 是 15 条样本上的过拟合） |
| 主张分析过期只标记、不自动重算 | **这是刻意设计**，不是缺陷 |
| 受控修正白名单只覆盖 标题/组织/起止时间/描述（技能仅名称） | 刻意收窄，避免放大器 |
| 简历解析偶发质量瑕疵（教育经历去重合并） | 1 项测试记录，不影响主流程 |

### E2. 真实模型未验证（`NOT_RUN` / `UNRATED`）

| 项 | 状态 |
| --- | --- |
| 真实付费大模型下的完整效果 | **`NOT_RUN`**（本轮未授权付费调用，全部用本地桩模型或离线重放） |
| 闸门 A/B 重放里的「A 侧原始输出」 | 是**确定性重放语料**，不是真实模型输出 |
| 人工评分维度 | **`UNRATED`**（没有人工金标准，因此**不计算「事实错误率」**） |
| 真实模型下的事实错误率 | **不可推断**。不做「未检出编造 ⇒ 系统不会编造」的推断 |

### E3. 真实招聘网站需用户登录

| 项 | 状态 |
| --- | --- |
| BOSS 直聘 / 实习僧等中文招聘网站 | **未做真实验证**（标记 `CHINESE_JOB_SITES_UNVERIFIED`） |
| 需要登录的平台 | 唯一合规入口是「**粘贴完整 JD**」，不做绕过登录的抓取 |
| 已验证的公开来源 | RemoteOK / Remotive / Greenhouse / Lever（均不支持服务端城市或实习过滤，只能本地过滤） |
| 采集口径 | 采集时间 ≠ 发布时间；接口成功 ≠ 岗位仍在招；无人工标签时相关性记 `UNREVIEWED` |

### E4. 没有真实用户研究

| 项 | 状态 |
| --- | --- |
| 真实用户可用性研究 | **未做**（`docs/evaluation/trusted-workflow-v12/user-study-plan.md` 仅为计划） |
| 「用户是否真的理解三态分离」 | **没有数据**，不作为结论 |

### E5. 发布阻塞（必须知道）

| 阻塞 | 说明 |
| --- | --- |
| **Git 历史里仍有真实姓名** | `main` 的树与历史提交（`daf50ff`、`3e7ca60` 等）仍含真实姓名。**在历史级清理（再跑一次 `git-filter-repo` + 强推）完成前，不要把仓库设为公开。** 本轮未自行强推。 |
| **不要发布公开 GitHub Release** | 按指令，本轮不发布公开 Release |

---

## F. 最短用户路径（从双击桌面图标到导出岗位版 PDF）

```text
1. 双击桌面「AI Career OS」图标
   （首次使用先双击 install.cmd：建 venv、装依赖、生成桌面图标）

2. 粘贴简历文字建档 → 档案出现在「简历中心」
   （不配模型也能建档，走本地规则解析）

3. 添加目标岗位 → 粘贴完整 JD

4. 一路「继续」：确认简历来源 → 选择经历 → 简历策略 → 生成岗位定向简历
   → 在岗位简历页逐条「接受」改写要点 → 确认投递版

5. Studio：选模板 → 下载草稿 PDF 自查（带 DRAFT 水印，不会误当正式版）

6. 「简历」页 → 事实核对：逐条点开确认属实
   （需要改标题/公司/起止时间/描述时，用「受控修正」改，改完点确认属实）

7. 回到 Studio → 确认正式投递版 → 导出 PDF（无 DRAFT 水印）

8. 创建投递记录并绑定这一版 → 面试准备自动读取这一版
```

**想少走几步**：第 5 步的草稿 PDF 可以直接跳过；但如果**从未核对过事实**，
第 7 步一定会被拦下（409 `unconfirmed_fact:block`）——这是设计，不是故障。

---

## 附：本轮改动的文件（相对 `main` `a033b21`）

**产品代码**
- `apps/api/app/fact_trust_service.py`、`fact_trust_schemas.py`、`models.py`、`profile_service.py`
- `apps/api/app/proof_service.py`、`proof_schemas.py`、`delivery_version_service.py`
- `apps/api/alembic/versions/030_fact_signature.py`（新增迁移）
- `apps/web/app/fact-check.tsx`、`fact-trust.ts`、`globals.css`

**测试**
- `apps/api/tests/test_controlled_fact_correction.py`（新增，19 项）
- `apps/api/tests/test_target_jobs.py`、`test_alembic_revisions.py`
- `apps/api/tests/test_fact_safety_reference_answer.py`、`test_fact_edit_reverification.py`
- 9 个文件的真实姓名脱敏（含 3 个前端测试夹具）

**评测与文档**
- `evals/benchmark/scripts/gate_replay.py`（新增）+ 报告 JSON
- `docs/evaluation/trusted-workflow-v12/`：`FINAL-FREEZE.md`（本文件）、`final-freeze-tests.md`、
  `gate-replay.md`、`known-issues.md`、`browser-e2e.md`、`browser/e2e-trusted-workflow.cjs`
- `README.md`、`docs/操作手册.md`
