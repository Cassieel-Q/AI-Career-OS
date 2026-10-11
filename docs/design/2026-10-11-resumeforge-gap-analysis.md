# ResumeForge 差异对比与增强分析

日期：2026-10-11
作者：AI Career OS 功能开发负责人
参考项目：ResumeForge（简历通） `https://github.com/magicapple123/ResumeForge`（FastAPI + React + SQLite，本地优先 AI 简历工作台）

## 0. 结论摘要

逐项对比后，确认我方「已存在但比 ResumeForge 弱」的可增强点有两个，本轮已落地：

1. **防虚构导出拦截**：我方只按 `claim_status`（待核对/缺失）拦截，ResumeForge 额外扫描正文里残留的 `【待补：…】` 等占位符标记并拦截导出。→ 已增强后端 `export_checks()` 与前端导出前检查。
2. **导出格式多样性**：我方只有 Typst PDF + 浏览器打印 HTML，ResumeForge 提供 PDF/docx/Markdown/纯文本/JSON/HTML + 水印 + 脱敏。→ 已新增服务端 Markdown / 纯文本 / JSON 导出（不依赖 Typst，纯文本渲染）。

其余「重合但较弱」点与「全新系统」见下文逐项说明与路线图。本轮刻意**不新增数据库迁移**，所有改动均为不改 schema 的纯逻辑/接口增强。

---

## 1. 功能逐项对比

### 1.1 事实确认 / 防虚构（重合，我方较弱 → 已增强）

| 维度 | ResumeForge | AI Career OS（我方） |
| --- | --- | --- |
| 事实来源 | 「事实台账」`claim` 表，逐条记录原始事实/简历表述/承担程度/个人边界 | `ResumeClaim` 主张 + `readiness_status`（SUPPORTED/DEFENDABLE/WEAK_EVIDENCE/UNSUPPORTED）+ `evidence_refs` + `risk_flags` |
| 核实状态机 | 已确认/待确认/已过期/不采用，硬规则「已确认不得含占位符」 | 主张就绪度 + `FACT_CONFIRMED` / `GROUNDING:NEEDS_CONFIRMATION` / `SYNTHETIC_PROJECT` 风险旗标 |
| 生成与资料逐条比对 | 学校/公司/项目名与资料库逐条比对，不一致给防虚构警告，点名编造的量化结果 | 面试参考回答有 `_gate_reference_answer` 数字事实闸门；简历要点按 `claim_status` 拦截 |
| 导出拦截 | 正文残留 `【待补：…】` 等标记时**拦截导出并指明在哪一节**，可选「仍要导出草稿」 | 后端 `export_checks()` 只拦 `NEEDS_CONFIRMATION`/`BLOCKED_MISSING`，**不扫描正文占位符残留** |

**改进目标**：把「正文还留着 `【待补】` 这类占位符」也纳入导出拦截，与 ResumeForge 对齐，避免把未完成的简历投出去。

**具体修改**：
- 后端 `apps/api/app/resume_studio_service.py::export_checks()`：遍历所有文本节点，用正则检测占位符残留（`【待补：…】`、`【待补充】`、`【待确认】`、`【待核实】`、`【待完善】` 及裸「待补/待补充/待核实/待完善」），命中即 `block`，`message` 指明所在节与条目（`code="placeholder_residue"`）。
- 前端 `apps/web/app/export-resume-checks.ts::buildPreExportChecklist()`：对可导出要点文本做同样的占位符残留检测，产出 `block` 级 `placeholder_residue` 提示（覆盖「投递版导出」路径）。

### 1.2 导出格式多样性（重合，我方较弱 → 已增强）

| 维度 | ResumeForge | AI Career OS（我方） |
| --- | --- | --- |
| 格式 | PDF（直出）、浏览器打印、HTML、Markdown、纯文本、JSON、Word(docx) | Typst PDF（直出）+ 投递版 HTML（浏览器打印） |
| 可选动作 | 水印、一键隐私脱敏、离线分享包 | 无 |

**改进目标**：补齐 Markdown / 纯文本 / JSON 三种文本导出，覆盖「文本存档、继续编辑、结构化备份」场景，与 ResumeForge 的文本导出能力对齐。不追求 docx（依赖 Word 排版库，风险大，写入路线图）。

**具体修改**：
- 后端新增 `apps/api/app/resume_studio_export.py`：纯函数把 `document_json` 渲染为 Markdown、纯文本、JSON 三种格式（不依赖 Typst 二进制，可离线运行）。
- 后端 `apps/api/app/resume_studio_routes.py`：新增 `GET /job-missions/{mission_id}/resume-studio/export?format=markdown|txt|json`，默认跑 `export_checks()` 拦截 block；`?draft=1` 允许「导出草稿」（对齐 ResumeForge 的「仍要导出草稿」）。
- 前端 `apps/web/app/resume-studio/api.ts`：新增 `downloadStudioExport()`；`apps/web/app/resume-studio/studio-page.tsx` 导出区新增三个格式按钮。

### 1.3 简历改写质量门控（基本持平，暂不增强）

| 维度 | ResumeForge | AI Career OS（我方） |
| --- | --- | --- |
| 版面诊断 | 测量页占用率，给「自动一页」逐档收紧 | Studio `confirm` 强制 1–2 页，页数超限报错 |
| 事实门控 | 防虚构警告 + 占位符拦截 | `export_checks` 高风险未核对拦截 |

**结论**：我方已有页数门禁与事实门禁，差距主要在「自动一页」的逐档字号收紧交互。该能力需要前端 `iframe` 测量 + 后端逐档版式探针，属较大交互改动，**本轮不实现**，写入路线图。

### 1.4 模拟面试（基本持平）

| 维度 | ResumeForge | AI Career OS（我方） |
| --- | --- | --- |
| 追问 | 逐轮追问、四维度评分报告 | 5 轮追问 + `followup_dimensions` + `gap_type`（四类缺口）+ 复盘 |
| 事实闸门 | 深挖用证据状态说话 | 参考回答 `_gate_reference_answer` 数字事实拦截 |

**结论**：我方模拟面试已具备逐轮追问、维度评分、复盘与参考回答事实闸门，与 ResumeForge 的「模拟面试」相当。ResumeForge 另有独立的「面试深挖」（契约制、证据状态、不评总分），属**全新子系统**，写入路线图。

### 1.5 岗位管理便捷性（部分较弱，暂不增强）

| 维度 | ResumeForge | AI Career OS（我方） |
| --- | --- | --- |
| 录入 | 手动/粘贴/截图/pdf/docx 多源识别 | 粘贴 JD 文本 + 岗位识别（公司/岗位/地点/核心要求） |
| 技能标签 | 保存时自动提取技能标签 | JD 解析不提取技能标签 |
| 匹配度 | 五类结论（已匹配/表达缺口/证据不足/真实缺口/待确认）+ 参考分 | 无 |

**结论**：岗位录入与识别我方已有，但缺「技能标签自动提取」与「匹配度分析（五类结论）」。前者需要 JD 技能词典 + 前端标签 UI + 可能的 schema 字段；后者是与「岗位需求解读」独立的全新链路。两者均属**较大改动 / 全新子系统**，本轮不实现，写入路线图。

---

## 2. 暂不实现的全新系统路线图

以下为 ResumeForge 有、我方**完全没有**的全新大系统，按依赖与价值排序，写入后续路线图，本轮不直接开建：

1. **自动投递台**（采集 → 匹配 → 显式确认 → 自动投递）：需浏览器桥接层（CDP）+ 站点适配器 + 任务运行器，是 ResumeForge 里唯一主动访问外部站点的链路，工作量与合规风险都最大。若我方要做，建议先从「备选岗位暂存区 + 投递进度记录」这种无浏览器依赖的部分起步。
2. **求职进度与数据看板**（一家公司一岗位一条记录、漏斗统计/转化/节奏）：可与自动投递台解耦，只做「粘贴邮件/截图识别进展 + 状态漏斗」即可独立落地。
3. **面试深挖**（独立 drill：契约制、证据状态、不评总分）：与我方「模拟面试」正交，是我方面试能力最值得补的第二块，建议优先于投递台。
4. **求职助手**（查库多轮、工具读写、联网搜索可选）：需要独立的 ChatConversation 历史表 + 工具注册表，规模较大。
5. **网申填表**（专用浏览器整页读取 + 只填不交）：依赖浏览器桥接，属投递台的延伸。
6. **匹配度分析（五类结论 + 参考分）**：与我方「岗位识别」独立，需要逐条对照 JD 与简历事实的判定链路。
7. **全局搜索 / 回收站 / 离线分享包 / 水印与一键脱敏**：横切型体验增强，可与导出增强逐步补齐（其中「一键脱敏」与「水印」最接近我方导出链路，可作为下一次导出增强的自然延伸）。

---

## 3. 风险与边界

- 本轮不新增 Alembic 迁移，不改动 `013_profile_contacts → 014_resume_studio → 015_interview_records` 迁移链。
- 不提交/不覆盖主检出的 `apps/api/alembic/versions/014_interview_records.py` 与 `image/`。
- 文本导出为纯函数渲染，不依赖 Typst 二进制，避免把「导出格式」能力绑定到本机排版环境。
- 占位符检测采用确定性正则（只认 `【待…】` 括号标记与裸「待补/待补充/待核实/待完善」），不做模糊语义匹配，避免误拦正常正文（对齐 ResumeForge「宁可少拦、不可误拦」的导出闸门原则）。
