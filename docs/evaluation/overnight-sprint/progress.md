# Overnight Sprint 进度

分支：`feature/resumeforge-overnight`（基于 `feature/resumeforge-48h` 的 `d027426`）

## M1 · 网页一键采集（任务化）

状态：**DONE_VERIFIED**（后端 8 用例验收脚本 + 浏览器 E2E 8/8）

### 本轮新增/修复

- 采集改为**任务接口**：`POST /api/v1/profiles/{id}/job-ingest/collect-runs`（立即返回 task_id），
  `GET /api/v1/job-ingest/collect-runs/{task_id}` 轮询，`POST .../cancel` 取消。
  任务状态机：`IDLE / RUNNING / COMPLETED / PARTIAL / FAILED / CANCELLED`。
- 结果状态：`NEW / DUPLICATE / UPDATED / NEEDS_REVIEW / FAILED`，由 `classify_collected`
  与岗位库逐条比对得出（正文指纹 `content_hash` = role+location+落库文本，去 URL 与来源随机串）。
- 统计条拆分「抓到 / 筛选后 / 新增 / 已存在 / 有更新 / 待确认 / 不可用 / 可保存」，
  不再把「抓到 100 条」与「保存 100 个」混为一谈。
- 新增第 4 个公开来源 **Remotive**（服务端关键词检索）；适配器契约
  `ADAPTER_SPECS`：capabilities（如实声明：目前所有来源都不支持服务端城市/实习过滤，`filter_mode=local`）、
  validate（缺 board token 明确报错）、health_check（真实请求一次）。
  `GET /api/v1/job-ingest/adapters`、`POST /api/v1/job-ingest/adapters/{source}/health-check`。
- HTTP 层加节流（同源最小间隔）、重试（429/5xx 退避）、整轮时间上限（超时标 TIMEOUT/PARTIAL）。
- 前端：任务状态徽章、实时进度、取消按钮、结果状态列、来源「自检」按钮、
  Greenhouse/Lever 已验证预设一键填入（`stripe/airbnb/anthropic/figma/databricks/discord/reddit/roblox/coinbase/thoughtworks/elastic/scaleai/figureai`；
  Lever：`leverdemo/palantir/spotify`）、保存时可选「同时更新有更新的已有岗位」。
- 已保存行无指纹的历史数据：回填指纹后可正确参与去重。

### 修掉的真实缺陷

1. RemoteOK JD 内嵌随机串（`RMS4yMDMuMTEwLjIz` 反垃圾标记）→ 每次采集都误判 UPDATED。
   修复：`stable_text()` 去随机 token 后再哈希。
2. `save-collected` 二次保存同岗位时 `db.get(UUID列, 字符串id)` 抛
   `'str' object has no attribute 'hex'` → 页面显示 Failed to fetch（500）。
   修复：`_load_duplicate_row` 先转 UUID；补回归测试。
3. 统计在 `classify_collected` 之前计算 → new/duplicate 恒为 0。修复：`recompute_result_totals` 在标注后重算。
4. Remotive `job_type` 未映射 → 全职岗位被标 UNKNOWN。

### 证据

- `docs/evaluation/overnight-sprint/m1-collect-acceptance.json`（8 个用例：真实采集/去重/空结果/来源404/字段缺失NEEDS_REVIEW/城市过滤排除/用户取消/保存后导入Mission）
- `docs/screenshots/overnight-m1/01..06.png` + `e2e-result.json`（浏览器 E2E 8/8）
- 测试：`tests/test_job_collect_tasks.py`（19 项）+ `tests/test_job_collection.py`（23 项）

### 复现命令

```powershell
cd apps/api; .venv\Scripts\python -m pytest tests/test_job_collect_tasks.py tests/test_job_collection.py -q
cd apps\api; .venv\Scripts\python scripts\collect_acceptance.py http://127.0.0.1:8100 <profile_id>
cd apps\web; node scripts\e2e-overnight-m1.cjs
```

## M2 · Studio 一键更新（差异确认 + 修订冲突 + PDF）

状态：**DONE_VERIFIED**（两份简历 × 两个不同 JD 全链路验收脚本各 30 步 0 失败 + 浏览器 E2E 19/19）

### 本轮新增/修复

- `source-diff` 升级为**板块级差异**：逐板块返回 `added/removed/kept` 与状态
  （`added/removed/changed/unchanged`），并统计**人工编辑内容**
  （`source_kind == "user_entered"` 的文本）——重新导入会整体替换文档，
  弹窗必须提前列出这些内容（`manual_edit_count` + 样本）。
- 前端差异确认弹窗：板块表格（状态/新增/移除/保留）→ 逐条差异 → 人工编辑警告
  →「确认更新（生成新修订版）」/「先不更新」。`reimport` 不再使用 `window.confirm`。
- **换模板不改正文**：`set_template` 只改 `template_id`，正文逐条不变（验收实测 4→4 条一致）。
- **换模板后必须重新确认才能下载正式 PDF**（修订号推进 → 旧确认失效）——防呆而非缺陷。
- **零接受要点防呆**：`confirm_target_resume` 在 `accepted_count == 0` 时返回 409，
  明确指引回岗位简历页逐条接受/编辑，不允许确认出一版全被拒绝的空简历。
- 占位符防呆（`待补充/待核实/待完善/待补全`）拦截确认 → 属预期行为；验收脚本模拟用户补齐
  （能留实质内容的改写，否则整条省略，**不凭空补量化成果**）。

### 修掉的真实缺陷

1. `_section_breakdown` 把 **section** 传给了期望 **document** 的
   `_included_bullet_texts` → 板块差异恒为 `unchanged/kept=0`，与顶层 `added_bullets`
   自相矛盾。修复：拆出 `_section_bullet_texts()`；同名板块用「标题+出现序号」配对，
   避免重复标题被 dict 覆盖。补纯函数回归测试。
2. `_same_hash` 对无指纹的存量记录一律判「已变化」→ 相同内容反复保存永远 UPDATED。
   修复：按同一口径现算存量正文指纹再比。
3. 旧测试与新契约不一致（`generic_url`→`browser`；UPDATED/DUPLICATE 语义）→
   更新测试并补完整语义链（UPDATED → 用户选择更新 → 再保存才是 DUPLICATE）。
4. `test_bulk_confirmation_never_auto_accepts_unsupported_point` 与零接受防呆冲突 →
   保留原意（不自动接受不支持要点），补一条已接受要点。

### 证据（两份简历 × 两个不同 JD）

| 用例 | 步骤 | 失败 | 修订 | 人工编辑提示 | 板块差异 | PDF |
|---|---|---|---|---|---|---|
| ai-pm（张三 × AI 产品经理 JD） | 30 | 0 | 2→3，确认 rev4 | 1 条（手工补充被识别） | 工作与项目 a4/r4 | 88,841 B + 换模板后 89,102 B |
| data-analyst（李四 × 数据分析师 JD） | 30 | 0 | 2→3，确认 rev3 | 1 条 | 工作与项目 a3/r3 | 77,340 B + 换模板后 77,579 B |

每步验证：428（缺 If-Match）→ 409（过期修订）→ reimport 成功（rev+1）→ 确认投递版 →
真实 Typst PDF → 换模板（正文逐条不变）→ 重新确认 → 二次 PDF → 刷新恢复（修订/模板/正文）。

- 浏览器 E2E 19/19：`docs/screenshots/overnight-m2/01..06.png`（新版提示横幅、差异弹窗、
  取消后保留原稿、更新后新修订版、换模板后正文不变、刷新恢复）+ `e2e-result.json`
- 验收 JSON：`m2-studio-acceptance-{ai-pm,data-analyst}.json`
- 测试：`tests/test_resume_studio_reimport.py`（4 项，含板块差异回归）+ grounding 全绿

### 复现命令

```powershell
cd apps\api; .venv\Scripts\python scripts\studio_update_acceptance.py http://127.0.0.1:8100 ai-pm
cd apps\api; .venv\Scripts\python scripts\studio_update_acceptance.py http://127.0.0.1:8100 data-analyst
cd apps\web; $env:NODE_PATH="C:\Users\覆水\.workbuddy\binaries\node\workspace\node_modules"; node scripts\e2e-overnight-m2.cjs
```

### 基线失败（非本轮引入，已用 worktree 在 bb5b140 逐一验证）

`test_claim_provider` / `test_gap_analysis` / `test_market_profile` / `test_priorities` /
`test_resume_reliability` / `test_roadmap` / `test_target_jobs` 共 7 个，与 M1 基线完全一致，
不依赖本轮改动（多为 LLM 输出不确定性相关的断言）。当前全量：**825 passed / 7 failed（基线）/ 5 skipped**。

## M3 · 求职管理补齐（版本绑定 / 打招呼话术 / 看板 / 提醒）

状态：**DONE_VERIFIED**（真实服务验收 18 步 0 失败 + 浏览器 E2E 14/14 + 后端测试 8 项全绿）

### 本轮新增

- **投递版本绑定**（迁移 `027_application_binding`，job_applications 补六列，全部可空）：
  `resume_version_id` + `studio_revision` + `pdf_snapshot_path` + `jd_source` +
  `greeting_short`/`greeting_long`。
  - `POST /applications/{id}/bind-resume`：绑定**最新已确认**岗位定向简历，
    渲染 PDF 快照存 `%LOCALAPPDATA%\AICareerOS\pdf_snapshots\`；
    Studio 未确认当前修订版时 409（投出去的必须是用户确认过的内容）。
  - `GET /applications/{id}/resume-snapshot`：随时下载投递时的 PDF 快照——
    直接回答「我当初投的是哪份简历」。
- **打招呼话术**（`greeting_service.py`，确定性模板、不调用模型）：
  - `POST /applications/{id}/greeting` 生成简洁版 + 详细版草稿；
  - **只引用真实事实**：姓名来自档案、经历要点来自用户已确认（ACCEPTED/EDITED）的定向简历、
    JD 要求来自 `parsed_jd`；没有简历事实时如实降级（只保留姓名+岗位+附件指引），**不编造**；
  - 可编辑（PATCH 保存）、可复制（前端一键复制）；系统只生成草稿，**不自动发送**。
- **求职看板** `GET /profiles/{id}/applications/board`：
  按状态分列（阶段数量）+ **简历版本使用记录**（哪版简历投过哪些岗位）+
  最近面试（复用 InterviewRecord）+ 待办提醒（复用 Reminder）——**不建第二套事实来源**。
- **提醒 CRUD**：`GET/POST /profiles/{id}/reminders`、`POST /reminders/{id}/complete`；
  界面明确标注「提醒仅在应用内展示，不会发送系统推送」。
- 前端投递页：状态/渠道/关键词筛选、绑定按钮、投递版本显示（vN + rM + 快照下载）、
  话术生成/编辑/复制面板、看板三卡（版本使用/最近面试/待办提醒）。

### 证据

- `docs/evaluation/overnight-sprint/m3-tracker-acceptance.json`（18 步：建档→改写→确认 Studio→
  建投递（mission+JD 来源）→ 绑定版本（版本 ID+修订号+快照一致）→ 下载快照 57,654 字节真实 PDF →
  话术生成（含姓名/岗位、不编造）→ 编辑保存 → 推进/退回 → 提醒/面试记录 → 看板断言）
- `docs/screenshots/overnight-m3/01..05.png` + `e2e-result.json`（浏览器 E2E 14/14）
- `docs/evaluation/overnight-sprint/m3-delivery-snapshot.pdf`（投递快照样例）
- 测试：`tests/test_application_binding.py`（8 项：绑定记录版本+修订+快照、未确认 Studio 拒绝绑定、
  无确认简历拒绝、话术只引用真实事实、无简历降级、看板聚合、JD 来源、提醒 CRUD）

### 复现命令

```powershell
cd apps\api; .venv\Scripts\python scripts\tracker_acceptance.py http://127.0.0.1:8100
cd apps\web; $env:NODE_PATH="C:\Users\覆水\.workbuddy\binaries\node\workspace\node_modules"; node scripts\e2e-overnight-m3.cjs
```

## M4 · 网申填表真实兼容性与安全

状态：**DONE_VERIFIED**（真实浏览器桥 + 本地表单页验收 11 步 0 失败 + 安全测试 23 项全绿）

### 本轮新增/修复

- **字段生命周期六态**（`READ / MATCHED / CONFIRMED / FILLED / SKIPPED / FAILED`）：
  规则层 plan 输出 `state`（READY→MATCHED、NEEDS_CONFIRM→READ、BLOCKED/UNSUPPORTED→SKIPPED），
  执行层由 fill 结果给出 FILLED/FAILED，用户确认后 CONFIRMED。summary 增加六态统计。
- **确认类勾选绝不代劳**（真实缺陷）：checkbox（隐私政策/同意条款）此前会被 label 启发式
  误读成普通字段（实测被误标「姓名」并**自动勾选**）→ matching 层一律 SKIPPED +
  fill 执行层 `_NEVER_FILL` 加 checkbox 双保险。
- **「code」误判修复**（真实缺陷）：`ref_code`（内推人工号）因 name 含 "code" 被误判为
  验证码 BLOCKED → 收紧为 captcha/verify/vcode，裸 code 需同时出现验证相关词。
- **SSRF 防护**（新模块 `url_guard.py`）：只允许公网 http(s)；环回/私网/链路本地
  （含云元数据 169.254.169.254）/保留地址/域名解析到内网一律 422 拒绝；
  重定向不再交给 httpx 自动跟随——逐跳手动跟随（≤5 跳）且**每一跳重新校验**，
  堵住「公网 URL 302 跳内网」绕过。
- 隐藏/禁用/只读控件如实 SKIPPED；必填字段资料缺失 → 明确「必填」提示（不静默跳过）；
  标签不规范时用 name/id/placeholder 兜底匹配。
- **模型不可用不影响确定性字段**：匹配引擎是纯规则（`webform_matching` 无任何模型调用），
  测试文件全部不配置模型即通过——确定性字段（姓名/手机/邮箱/城市/学历/毕业时间/专业）
  永远可填，低置信字段标 READ 等人工确认。

### 证据（真实浏览器桥 + 本地测试表单 `docs/evaluation/webform-testpage/index.html`）

- `docs/evaluation/overnight-sprint/m4-webform-acceptance.json`（11 步 0 失败）：
  建档（真实 LLM 抽取）→ 会话打开表单 → 读取 + 匹配（14 项六态断言全过：7 字段 MATCHED、
  自我介绍/内推/到岗 READ、禁用/密码/验证码/文件/checkbox/隐藏 SKIPPED）→
  执行填写 8 项成功 → 重新读取逐字段验证（姓名/手机/邮箱/城市/学历本科/专业已填，
  密码/验证码/附件空，禁用控件原样 AUTO-9527，**同意条款未被代勾**）→
  提交按钮未点击（页面仍是表单）→ SSRF 元数据/环回 422。
- `docs/screenshots/overnight-m4/01-填写前.png`、`02-按计划填写后.png`（填写后截图可见
  7 字段已填、其余留空待人工、禁用控件原样、提交按钮未动）
- 测试：`tests/test_webform_safety.py`（23 项）+ webform 原有 12 项回归全绿

### 复现命令

```powershell
cd docs\evaluation\webform-testpage; python -m http.server 8123 --bind 127.0.0.1   # 测试表单
cd apps\api; .venv\Scripts\python scripts\webform_acceptance.py http://127.0.0.1:8100   # 需浏览器桥 8770
cd apps\web; $env:NODE_PATH="C:\Users\覆水\.workbuddy\binaries\node\workspace\node_modules"; node scripts\e2e-overnight-m4-shot.cjs
```

## M5 · Benchmark（evals/overnight-v1）

状态：**DONE_VERIFIED**（数据集 30 JD / 10 简历 / 30 配对 / 90 改写 / 15 对抗用例，全量真实跑通）

### 交付物

- `evals/overnight-v1/schema/*.json`（6 个 draft-07 schema）+ `scripts/{build_dataset,validate,run,score,report}.py`
- `evals/overnight-v1/annotations/{GUIDELINES.md,template.json}`（人工标注规范与模板）
- 报告：`docs/evaluation/overnight-benchmark-report.md`

### 真实运行结果（`run-20261016T192635Z.json` / `score-20261016T192635Z.json`）

| 路径 | 结果 |
|---|---|
| B（AI Career OS） | **30/30 配对全部执行**，38 条要点参与机械评分 |
| A（Direct LLM） | **30/30 NOT_RUN**（未配置 `BASELINE_DIRECT_LLM_*`，如实标注，不伪造） |
| 对抗/安全 | **15/15 全部执行**；`bc_safe=15`、`bc_unsafe=0`，其中 `bc-09`（空 JD）按预期被系统 422 拒绝 |
| 疑似编造数字 | **0**（白名单覆盖整份简历 + JD 后，误报归零） |
| 空改写 | 0 |

### 修掉的三个方法学缺陷（否则会得出假结论）

1. `run.py` 曾强行把每条经历写成 `KEEP_AND_HIGHLIGHT` 再与 ground_truth 比对——
   等于替被测系统作答。改为**只确认、不改写**系统自己的四分类。
2. `score.py` 曾把 `NOT_RUN` 计入 `bc_safe`（**把没执行当成安全通过**）。
   现单独统计 `bc_not_run`，未执行的 `safe` 为 `null`。
3. `score.py` 曾靠 `risk_flags` 反推四分类，得出「准确率 2/5」——系统并不输出要点级四分类，
   那个数字是假的。现如实标 `b_decision_comparable=0`，四分类交人工标注。
4. 数字白名单原只用单条要点 → 把「跨要点合并改写」误判成编造（实测 2 例均为误报）。
   白名单改为整份简历 + 对应 JD。

### 复现命令

```powershell
cd evals\overnight-v1\scripts
python build_dataset.py && python validate.py
python run.py --api http://127.0.0.1:8100     # 全量 30 配对 + 15 对抗用例，约 25 分钟
python score.py ..\results\run-<时间戳>.json
python report.py
```

## M6 · 全链路回归与最终交付

状态：**DONE_VERIFIED**（A~F 六场景 E2E **40 步 0 失败** + 安全边界测试 31 项全绿 + 隔离 production build 通过）

### A~F 全链路（`m6-full-chain.json`，40/40）

| 场景 | 覆盖步骤 | 结果 |
|---|---|---|
| A 采集 | 建档 → 采集任务终态 → **抓到 vs 保存分开统计** | 6/6 |
| B 改写 | JD → 经历四分类 → 策略 → 定向简历 → 逐条接受 → 确认 | 10/10 |
| C 更新 | 修订号 → 板块差异 → **428 / 409** → 换模板不改正文 → 重新确认 | 7/7 |
| D 投递 | 绑定（版本 ID + 修订号 + 快照）→ **下载真实 PDF 快照** → 话术 → 看板 | 5/5 |
| E 网申 | 六态读取 → 按计划填写 → **绝不自动提交** → SSRF 元数据/环回 422 | 5/5 |
| F 备份 | 导出 → 完整性校验 → 损坏包拒绝 → **恢复为新数据集** → 原数据集仍在 → **切回原数据集** | 7/7 |

### 安全测试 `tests/test_security_boundaries.py`（31 项全绿）

SSRF（10 个内网/元数据/协议用例全部 422）· 桥跨站与缺令牌拒绝 · 桥不提供本地文件读写 ·
**Zip Slip 路径穿越** · **解压炸弹** · 备份损坏/篡改拒绝 · 备份不含密钥 ·
未确认不得绑定投递版 · 不存在自动投递接口 · 数据集切换不删除原数据集。

### 修掉的真实安全缺陷

1. **Zip Slip（备份恢复路径穿越）**：`restore_as_new_dataset` 直接拼接压缩包成员名，
   `attachments/../../evil.txt` 会写到数据集目录之外。已加 `_safe_attachment_rel()`
   （拒绝 `..`/绝对路径/反斜杠/盘符）+ `Path.is_relative_to()` 二次兜底。
2. **解压炸弹无上限**：新增单成员 256 MiB / 整包 1 GiB 限制，`inspect_archive` 先按声明大小拦截。

### 隔离 production build（G 盘 EPERM 是环境问题，非代码问题）

在 `D:\temp\aicareer-webbuild`（NTFS，非 G 盘）完整复制前端源码与 node_modules 后
`next build` **成功**（Next.js 15.5.24，编译 27.5s，`BUILD_EXIT=0`），全部路由产出。
原工作树未被触碰（未生成 `.next`）。

### 复现命令

```powershell
# 后端（必须带 AI_CAREER_DATA_DIR，否则回退 DATABASE_URL 会 500）
cd apps\api; $env:AI_CAREER_DATA_DIR="$env:LOCALAPPDATA\AICareerOS"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100

cd apps\api; .venv\Scripts\python scripts\e2e_full_chain.py http://127.0.0.1:8100
cd apps\api; .venv\Scripts\python -m pytest tests\test_security_boundaries.py -q
```

## M7 · 补充任务：岗位采集真实验收与 Benchmark

状态：**DONE_VERIFIED**（四个真实公开来源采集成功、去重通过、浏览器 E2E 17/17、`COLLECTION_E2E_VERIFIED = True`）
同时标记 **`CHINESE_JOB_SITES_UNVERIFIED`**（中文招聘网站未做真实验证）。

### 隔离测试数据集

- 新建 `ds261017041218fd59`（复制自用户原数据集 `ds2610162021590a18`，原文件**只读未删**）
- 所有采集/入库都写在这个副本里；验收结束已把指针切回原数据集

### 测试集 `evals/job-collection-v1/`

- `fixtures/`：RemoteOK / Greenhouse 结构样例、标准详情页、结构改版页、登录墙页、
  提示词注入页、特殊字符页、空数组样例、固定去重标注样本 `dedupe_labels.jsonl`
- `cases.jsonl` / `expected.jsonl`：15 类场景，外加 C16 手动编辑保留
- `test_collection.py`：**27 项全绿**（15 场景 + 1 手动编辑保留 + 11 安全专项）
- `run_live_smoke.py`：真实在线采集（RemoteOK / Remotive / Greenhouse / Lever）
- `report.py`：6 项指标 + 报告 + 158 条人工审核清单

### 真实在线采集结果（BROAD 阶段首次采集）

| 来源 | 原始返回 | 解析 | 入库新增 | 重复采集新增 | 指纹一致 |
|---|---|---|---|---|---|
| RemoteOK | 99 | 30 | 30 | **0** | 是 |
| Remotive | 15 | 14 | 14 | **0** | 是 |
| Greenhouse（anthropic/figma/stripe） | 1526 | 30 | 30 | **0** | 是 |
| Lever（palantir/leverdemo） | 320 | 30 | 30 | **0** | 是 |

### 本轮修掉的真实缺陷

1. **Greenhouse 去重完全失效**：适配器在 `normalize_job` 之后才把公司名从空改成招聘板标识，
   但没重算 `dedupe_key`，库里存着用空公司名算出的 key，下次按真实公司名现算永远匹配不上，
   同一批岗位每次重复采集都被当成「新增」。新增 `retag_company()` 修复。
2. **保存时启发式解析覆盖来源字段**：`save_collected` 只在启发式结果为空时才用来源字段补齐，
   RemoteOK 岗位因此被切成「Remote / Independent Contractor」（取自 JD 首行），
   用户在岗位库里看到的是错误公司名与岗位名。改为来源字段优先。
3. **抓取无体积上限**：`fetch_url_text` 整体读入响应体，恶意站点可用超大响应拖死进程。
   改为流式读取 + 5 MiB 上限（可用 `AI_CAREER_COLLECT_MAX_BYTES` 调整）。
4. **招聘板标识未过白名单**：`../..` 造成路径穿越、`?` 截断查询串。新增 `validate_board_token()`。
5. **去重指纹漂移**：随机 token 被剥离后残留 `(# )` 空括号，同一岗位两次采集指纹仍不同。

### 浏览器 E2E（15 步）

`apps/web/scripts/e2e-job-collection-v1.cjs` → **17/17 通过**，15 张截图存于
`docs/screenshots/job-collection-v1/`。

### 复现命令

```powershell
cd apps\api
$env:AICAREER_API="http://127.0.0.1:8100"
.venv\Scripts\python -m pytest ..\..\evals\job-collection-v1\test_collection.py -q
.venv\Scripts\python ..\..\evals\job-collection-v1\run_live_smoke.py --api http://127.0.0.1:8100
.venv\Scripts\python ..\..\evals\job-collection-v1\report.py

cd apps\web
node scripts\e2e-job-collection-v1.cjs
```
