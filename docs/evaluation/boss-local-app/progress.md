# AI Career OS｜本地软件化 + BOSS 求职辅助 · 进度

分支：`feature/boss-local-app`（基于 `feature/resumeforge-overnight` 的 `c3268ac`）
开始时间：2026-10-17
状态标记：`DONE_VERIFIED` / `DONE_UNVERIFIED` / `PARTIAL` / `BLOCKED_EXTERNAL` / `NOT_STARTED`

---

## 环境实况（先记录，后面所有结论都以此为基准）

| 项 | 实况 |
| --- | --- |
| 仓库位置 | `G:\myself\ai-career`，**G 盘是 exFAT 的移动硬盘（My Passport）** |
| 后端 | `apps\api\.venv`（Python 3.13.14 / FastAPI 0.115.6 / SQLAlchemy 2.0.36）完好 |
| 前端依赖 | **发现 `apps\web\node_modules` 严重损坏**：322 个包目录还在，但 `next/package.json`、`next/dist/bin/next`、`react/package.json` 等文件全部丢失（目录下只剩 158 个文件）。已重新 `npm install`（25 分钟，370 个包）修复 |
| 端口 | 8000 = **另一个项目 CityQuest**（`G:\myself\findCity`，绝不能动）；8100 = AI Career OS 后端；3000 = 前端；8770 = 受控浏览器桥 |
| 本地数据 | `%LOCALAPPDATA%\AICareerOS`，当前数据集 `ds2610162021590a18`（221 候选岗位 / 119 岗位 / 101 定向简历 / 22 Studio 文档 / 15 投递记录 / 7 面试记录） |
| Edge | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` |
| Node | `C:\Program Files\nodejs\node.exe` v24.15.0 |

> G 盘 exFAT + 移动盘意味着：Next.js 构建必须走 `--require ./scripts/next-g-drive-fs-compat.cjs`，
> 且 `.next/trace` 有 EPERM 风险；`build-web.ps1` 已内置「G 盘失败 → D 盘 NTFS 隔离构建 → 复制回 G」的兜底。

---

## M1 一键启动 —— `PARTIAL`（脚本完成，实机验收待构建完成后执行）

新增文件：

| 文件 | 作用 |
| --- | --- |
| `scripts/local-app/career-app.ps1` | 启停器（`start` / `stop` / `status` / `restart`） |
| `scripts/local-app/build-web.ps1` | production 构建（G 盘优先，失败自动切 D 盘隔离构建） |
| `start-career.cmd` / `stop-career.cmd` | 命令行入口 |
| `create-desktop-shortcut.ps1` | 生成桌面图标（自动生成 `app.ico`） |

关键设计（对应「不能误杀其他项目」）：

- **端口归属必须证明**：用 `Get-NetTCPConnection` 拿到监听 PID，再用 `Win32_Process.CommandLine`
  确认命令行里带本项目路径才承认是 AI Career OS 的进程。只凭端口存在**不**做任何结论
  （8000 上的 CityQuest 因此永远不会被碰）。
- **端口被外人占用就顺延**：前端 3000→3005、后端 8100→8105、桥 8770→8773；全部被占则报错退出，绝不抢占。
- **单实例**：先按上面的归属规则找「已经在跑的本项目的」前端/后端，健康则不重复启动，直接复用。
- **全部只监听 127.0.0.1**：uvicorn `--host 127.0.0.1`，next `-H 127.0.0.1`，桥本身只绑回环。
- **不省略鉴权**：后端 CORS 仍只允许本地前端（并把实际前端端口写进 `FRONTEND_ORIGINS`）；
  浏览器桥仍要求 `Authorization: Bearer <token>`。
- **无黑窗**：服务用 `Start-Process -WindowStyle Hidden` 启动，桌面快捷方式直接调
  `powershell -WindowStyle Hidden`，双击不会出现开发终端窗口；失败时弹 MessageBox 明确报错。
- **Edge 独立窗口**：`msedge.exe --app=http://127.0.0.1:<port>`，**不指定 `--user-data-dir`**，
  因此复用你日常登录的 Edge 配置（BOSS 直聘登录态可继续用）。

待办：构建完成后执行「双击 → 打开首页 → 岗位 → Studio → PDF → 关闭 → 再启动 → 数据不变」验收。

---

## M2 BOSS 岗位导入 —— 后端/前端 `DONE_VERIFIED`，真实站点 `BLOCKED_EXTERNAL`

### 2.2 手动粘贴导入（主路径，已完成）

- 后端 `app/manual_import_service.py`：纯规则解析（**不调模型、不编造**），输出
  公司 / 岗位 / 地点 / 薪资 / 学历 / 经验 / 工作类型 / JD / 原始链接 + 每字段置信度 + warnings。
  - 修掉的真实坑：`【岗位职责】` 这类小节标题曾被当成岗位名（现在用负向前瞻排除
    `职责/描述/要求/介绍…`）；`经验不限 本科` 曾把整行当经验值（现在短字段按已知取值集合规范化）。
  - 提示词注入：检测到只**打告警标签**，解析逻辑不变，不会执行 JD 里的指令。
- 路由 `POST /api/v1/job-import/parse`（只解析不入库）与
  `POST /api/v1/profiles/{id}/job-import/save`（去重 + 差异提示 + 可选导入正式岗位）。
- 去重：复用统一 `dedupe_key(company, role, location)` + `content_hash`。
  - 同岗位同地点 → 不新增（返回 `DUPLICATE`）；
  - JD 变化 → 默认只报告 `changed_fields`，勾选「更新已有岗位」才写；
  - **用户手动改过的字段（`raw_payload.edited`）与备注不被覆盖**；
  - 同公司不同岗位 / 同岗位不同城市不合并（有测试）。
- 前端 `app/jobs/import/page.tsx`：粘贴 → 解析 → 字段可编辑 → 确认 → 保存 → 自动进入匹配。
  岗位广场顶部也加了「导入 BOSS 直聘岗位 →」入口。

### 2.3–2.5 浏览器扩展（已完成，代码级）

- `apps/extension/`（MV3）：权限只有 `activeTab` + `scripting` + `storage`
  + `http://127.0.0.1:*` / `http://localhost:*`。**没有** `cookies`、`webRequest`、`<all_urls>`。
- 只在用户点击后注入 `extract.js` 读取**页面已可见文本**（`innerText`），
  剔除 `script/style/input/textarea/select/button`，不读 Cookie、密码、验证码、聊天记录。
- 选择器命中不到就降级为整页可见文本并把置信度标 `LOW`；读不到就提示改用复制粘贴，
  **不显示虚假成功**。
- 通信鉴权：本地生成高熵令牌（`%LOCALAPPDATA%\AICareerOS\extension.token`），
  用户在设置页生成 6 位配对码（5 分钟有效、单次使用、有尝试次数限制）换取；
  写请求必须带 `X-AI-Career-Token`，且 Origin 必须是扩展或本地前端。
  令牌**不出现在** DOM / URL / 静态资源里。请求体 >1 MiB 直接 413；
  内容里出现 password/cookie/token/验证码 直接 422 拒绝。

### 真实站点

`BOSS_REAL_SITE_PENDING_USER`：BOSS 直聘需要你本人登录，本轮不做自动登录、不取 Cookie。
你回来后只需要做一次人工登录 + 打开一个职位页验证（见 `final-report.md`）。

---

## M3 岗位 → 投递准备 —— `DONE_VERIFIED`（后端+前端）/ 真实发送 `BLOCKED_EXTERNAL`

新增 `GET|POST /api/v1/missions/{id}/boss-kit/*`：

- `GET /boss-kit`：原岗位链接 / 岗位版简历版本 / 投递记录 / 话术 / 快照链接；
- `POST /boss-kit/greeting`：复用既有 `greeting_service`（确定性模板，只引用已确认事实），
  返回简洁版 + 详细版 + `grounded_on`；
- `PATCH /boss-kit/greeting`：保存用户编辑（编辑后不会被自动生成覆盖）；
- `POST /boss-kit/mark-applied`：状态推进 `APPLIED` + 绑定简历版本 + 生成 PDF 快照；
  没有已确认简历时如实提示但不阻断（用户可能线下投的）；
- `POST /boss-kit/reminder`：默认「3 天后跟进」提醒。

修掉的真实缺陷：`candidate_job_service.import_candidate` 之前**没有把候选岗位的
`source_url` 传进正式岗位**，导致导入 BOSS 岗位后「打开原岗位」没有地址。现已带上并加了测试。

前端 `app/boss-kit.tsx`（挂在岗位详情页）：生成话术 / 复制两版 / 打开原岗位 /
打开岗位版简历 / 标记已投递 / 下载投递快照 PDF / 创建跟进提醒。
**没有任何自动发送、自动开聊、批量群发**。

---

## M4 现有功能回归 —— 进行中

见 `test-results.md`。

## M5 专项测试集与 E2E —— `DONE_VERIFIED`（除真实站点）

见 `test-results.md`。主流程 E2E 18/18、扩展专项 9/9、一键启动 17/17。

### 本轮实机验收时修掉的真实缺陷（用户使用中暴露）

1. **受控浏览器桥「令牌不匹配」**（用户实机报障）
   - 根因：本机同时存在两个桥（手动脚本起 8770 + 桌面启动器起 8771），
     令牌文件只反映最后启动的那个，而后端写死连 8770。
   - 修法：启停器改为「先起桥 → 把实际端口以 `BROWSER_BRIDGE_URL` 注入后端 → 再起后端」；
     启动时清理多余的本桥；后端在未显式配置时按 8770–8773 探测真实在跑的桥；
     归属判定补充「相对路径启动的 `scripts/browser-bridge.cjs` 也认作本项目」。
   - 验证：`POST /api/v1/job-ingest/collect-browser` 不再返回 401，
     而是给出可读提示「当前页面没有读到可识别的岗位内容…」。
2. **岗位名带「招聘」前缀**：新增 `_ROLE_PREFIX_RE`，对 provided / 标签行 / 启发式三条来源统一剥离。
3. **来源虚标为 BOSS**：扩展解析 / 保存时 `source_site` 缺省不再补成 `BOSS_ZHIPIN`，
   改为如实记录 `UNKNOWN`（扩展按域名上报 `BOSS_ZHIPIN / OTHER / UNKNOWN`）。
4. **开发一个 `load-browser-extension.cmd`**：一键打开 Edge 扩展页 + 扩展文件夹，供用户手动加载。

## M6 最终回归与交付 —— 未开始

### 用户实机使用反馈（第二轮）

- 用户已在 Edge 成功安装扩展并完成配对（弹窗显示「已配对（令牌 …）」）。
- 用户在 BOSS **职位列表页**（`/web/geek/jobs`）上点「读取当前岗位」感到困惑；
  「采集当前网页」在受控浏览器空白页（about:blank）下也提示不清。
- 改进（扩展 v1.1.0）：
  1. `extract.js`：识别 BOSS 列表页 → 明确提示「点进包含 /job_detail/ 的详情页再读取」，
     不再用整页卡片文本瞎解析；补齐真实 BOSS 详情页选择器（`.job-banner .name h1` /
     `.job-sider .company` / `.job-sec .job-sec-text` 等）；
  2. `popup.js`：状态非 OK 且没有可解析正文时不再调后端，直接显示引导；
  3. 后端 `collect-browser`：受控浏览器是空白页时，明确说明「先开网页；BOSS 这类要登录的用扩展」。
- 回归：扩展专项 E2E 9/9 通过。

### 用户实机使用反馈（第三轮，扩展 v1.2.0）

- 用户实机截图确认：BOSS 推荐流是「左列表 + 右详情」**双栏布局**，点职位卡片时网址不变
  （仍是 /web/geek/jobs?city=...），详情在右侧面板展开——v1.1.0「等网址变成 /job_detail/」
  的引导在这种布局下永远走不通，判断错误。
- v1.2.0 改进（extract.js 重写抽取根节点逻辑）：
  1. 新增 `findDetailScope()`：在页面里找包含真实 JD 内容的详情面板容器
     （够长 + 有「职位描述/任职要求」标志词 + 不包含左侧职位卡片）；
  2. 找到详情面板时**以其为抽取根节点**，避免整页抽取命中左侧列表卡片；
  3. 岗位名/公司兜底：页面标题「岗位-公司-城市-招聘」（置信度 LOW，字段可编辑）；
  4. `job_url`：详情面板内链接 → 被选中卡片（active/current/selected）→ 岗位名匹配卡片 → 页面第一条；
  5. 未展开详情时提示改为「点左侧职位卡片，右侧展开详情后再读取」；
  6. popup 的 source_url 优先用扩展找到的真实职位链接（双栏流网址不随职位变化）。
- 新增合成测试页 `apps/web/public/boss-stream-test.html`（双栏布局 fixture）+ E2E 步骤 4b。
- 修复重写引入的两个回归：banner 信息行在详情面板外时回退整页查询；
  `visibleText(document)` 对 Document 节点返回 null（落到 document.body）。
- 回归结果：扩展专项 E2E **10/10**（含 4b 双栏流用例）。
- 环境备忘：`next start` 只在启动时扫描 public/，新增静态文件后需重启 Web 才可访问。

### 用户实机使用反馈（第四轮，扩展 v1.2.1 + 删除「采集当前网页」）

- 用户确认已重载到 v1.2.0，但在 BOSS 推荐流（详情已展开）点「读取当前岗位」仍未成功。
  真实 BOSS DOM 的类名无法远程确认 → v1.2.1 在抽取失败时把页面自诊信息
  （详情面板节点数 / JD 区块数 / 职位卡片数 / 信息栏数 / 是否含「职位描述」/ 正文长度）
  直接显示在扩展弹窗里，用户截图即可定位真实结构差异。
- 按用户要求删除工作台「采集当前网页」整个区块（受控浏览器无登录态，对 BOSS 无用）：
  - jobs/page.tsx：删除 section、handleCapture/handleSaveCapture、bridge/capture 状态与
    readBridgeStatus 加载、CONFIRM_LABEL；区块编号重排（4→3、5→4）。
  - 后端 /job-ingest/collect-browser 接口与 jobs.ts 相关导出保留（网申填表桥不受影响）。
- tsc --noEmit 0 错误；扩展语法/清单校验通过。

### 扩展 v1.2.2：修复「点了读取没反应」的弹窗缺陷

- 根因：警告元素 #read-warning 原本放在默认隐藏的 #result-block 容器里。
  读取失败时脚本写入警告文字后提前 return，外层容器仍是 hidden → 用户什么都看不到，
  表现为「点了没反应」。
- 修复：
  1. #read-warning 移到默认可见的首个区块；新增 showWarning/hideWarning 封装；
  2. 每次读取结论持久化到 chrome.storage（时间 + 成败 + 摘要/诊断），
     弹窗顶部显示「上次读取（时间）：✓/✗ 摘要」，重开弹窗不丢状态；
  3. 成功时记录解析出的公司/岗位/地点摘要。
- 结论：用户此前 v1.2.0/v1.2.1 的失败原因无法远程确认（报错被隐藏），
  v1.2.2 起任何结果都可见，诊断行可用于定位真实 BOSS DOM 差异。

### 扩展 v1.2.3：真实页面「页面没有返回可读内容」的两层透明化

- 用户 v1.2.2 弹窗首次露出真实报错：executeScript 成功但 result 为空。
- 两层修复：
  1. extract.js：核心逻辑包 try/catch，页面内任何异常都返回 status=ERROR 的
     可序列化对象（带 probe 自诊），不再因异常导致 result=undefined；
  2. background.js：results[0].error 存在时原样抛出页面错误；
     result 为空时把原始注入结果 JSON 带出并提示「先 F5 刷新页面再试」。
- 回归：扩展专项 E2E 10/10。
- 下一步：用户刷新 BOSS 页后重试；若仍失败，弹窗会给出可定位的真实错误文本。

### 扩展 v1.3.0：根因定位——MV3 `files` 注入不返回值（不是 BOSS 页面的问题）

- 用户 v1.2.3 弹窗报错原文：
  `页面没有返回可读内容（注入结果：[{"documentId":"E84E...","frameId":0,"result":null}]）`。
- **真正根因（我方代码缺陷，非站点结构差异）**：
  `background.js` 用的是 `chrome.scripting.executeScript({ target, files: ["extract.js"] })`。
  MV3 规范下 **`files` 注入不会把脚本的最后一个表达式作为返回值**，`results[0].result` 恒为 `null`。
  也就是说 extract.js 一直都执行成功、也抽到了内容，只是结果从来没传回后台。
  → 这也是为什么「F5 刷新」永远无效：刷新改变不了注入方式。
  v1.2.1/1.2.2/1.2.3 加的 probe / 透明化只是把症状显示出来，没有碰到病根。
- 修复（改成「注入 → 回读」两段式，三条互不依赖的通道）：
  1. `extract.js`：不再依赖返回值，把结果 JSON 写到
     `document.documentElement[data-ai-career-capture]`（DOM 属性，最可靠）、
     `window.__AI_CAREER_CAPTURE__`（隔离世界全局变量）、
     `chrome.storage.local.aiCareerCapture`（兜底）；
  2. `background.js`：新增 `clearCapture`（先清残留，避免读到旧结果）→ 注入 →
     `readCapture`（先用 `func` 读 DOM 属性，失败退回 `chrome.storage.local`）→ `JSON.parse`；
  3. 错误文案不再误导用户去刷新，改为「注入成功但页面没写回结果」并带上原始帧信息。
- 可观测性：弹窗顶部显示 `扩展版本：vX.Y.Z`，用户可确认是否真的重载到最新版。
- 回归：扩展专项 E2E **11/11**（新增 4c：守住「MV3 回读通道」这条回归用例，
  直接断言 `data-ai-career-capture` 里能解析出与 4b 一致的岗位结果）。
- 下一步：用户重载扩展到 v1.3.0 后点「读取当前岗位」；若仍失败，说明抽取逻辑与真实
  BOSS DOM 不匹配（此时弹窗会给出 status=NOT_A_JOB_PAGE + probe 自诊），按 probe 数值调选择器。

### 扩展 v1.3.1：第二个根因——重复注入触发顶层 const 重复声明的 SyntaxError

- 用户重载到 v1.3.0 后（弹窗已确认版本），报错变成：
  `注入成功但页面没写回结果（[{"documentId":"F28F...","frameId":0,"result":null}]）`。
  三条回读通道（DOM 属性 / 全局变量 / storage）**全空** → 脚本在求值阶段就炸了，一行都没执行。
- 复现实验（Playwright，同一文档连续 addScriptTag 两次）：
  ```
  1st-inject: OK
  SyntaxError: Identifier 'CAPTURE_ATTR' has already been declared   ← 第二次
  2nd-inject: OK          ← 注入 API 仍"成功"，但脚本未执行
  ```
  原因：同一个隔离世界里的**顶层 `const`/`let`** 会进入共享的全局词法环境，
  重复注入含顶层 const 的脚本 → SyntaxError。
  而 `executeScript` 对这种**求值期 SyntaxError 既不上报 error，也不填 result**
  （result 恒为 null），所以表现为「注入成功但什么都没发生」。
  用户的 BOSS 页此前被 v1.2.x / v1.3.0 注入过，词法绑定残留，v1.3.0 一注入就炸。
- 修复：
  1. `extract.js` 整体包进 IIFE，顶层不再有任何 `const`/`let` 声明 → 重复注入永不报
     SyntaxError（顺带也让已被旧版污染、未刷新的页面直接可用）；
  2. 抽取函数挂到 `window.__aiCareerExtract`，`background.js` 改用 **func 注入调用它**
     来拿结果（MV3 只有 func 注入有返回值），DOM 属性 / storage 降级为通道 2、3；
  3. 页面内函数抛错时以 `__EXTRACT_ERROR__` 前缀带回真实错误信息，不再静默。
- 回归：E2E 4c 改为「连续注入两次 + 断言 pageerror 为空 + 回读通道可用」，**11/11 通过**。
- 通用教训（写 MV3 内容脚本必记）：
  被 `executeScript({ files })` 注入的脚本**一律用 IIFE 包裹**，禁止顶层 `const`/`let`；
  并且不要依赖 `files` 注入的返回值，要结果就用 `func` 注入。

### 扩展 v1.3.2：修复「假已配对」死锁（令牌失效后无法重新配对）

- v1.3.1 让读取链路全线跑通后，暴露出下一个问题：弹窗报
  「扩展令牌无效或已轮换，请重新配对」，但「本机配对」区块仍显示
  「已配对（令牌 24295a696210）」且**配对码输入框被藏住**——用户令牌失效了
  却没有地方重新输入（点「清除配对」只清扩展本地，服务端仍报已配对，输入框照样不出现）。
- 原因：
  1. 后端令牌持久化在数据目录 `extension.token` 且**配对不轮换**令牌
     （`exchange_code` 返回 `ensure_token()` 的现有值）；数据目录被重置过时
     旧扩展令牌即失效；
  2. 弹窗的「已配对（令牌 …）」只是把 `/extension/status` 返回的**服务端**
     指纹回显，从未校验扩展本地存的那份 → 假安心；
  3. 弹窗逻辑「服务端 paired=true → 隐藏输入框」在令牌失效时构成死锁。
- 修复：
  1. background 新增 `verifyPair`：用扩展本地令牌真实调 `/extension/ping`；
  2. popup 打开时先 status 再 verifyPair：ok → 已配对；401 → 明确提示
     「本机令牌已更换，原配对失效」并**自动露出配对码输入框**；连不上 → 单独提示。
- v1.3.1 的读取链路（注入/抽取/回读）已在真实 BOSS 页验证通过（否则不会走到 401）。

### 扩展 v1.3.3：清理 BOSS 反爬水印与动作条噪声（真实导入首秀发现）

- 用户首次用 v1.3.2 完整走通「读取 → 导入」，真实导入落库成功
  （candidate_jobs 新增：美菜·供应链产品经理 17:17、北京焱法科技·产品实习生 17:18，
  均为 CONFIRMED）。工作台没显示的原因：候选草稿还需在岗位库点「导入」才成为
  正式岗位（job_missions）——这是产品设计，不是 bug。
- 新发现的质量问题：真实 BOSS 页面 JD 正文被反爬机制污染——
  「紧BOSS直聘追全球AI模型」（水印随机插进句子）、零宽字符、
  动作条噪声（收藏/立即沟通/举报/微信扫码分享/不适合职位描述）混进正文；
  薪资显示 000-000（未登录时站点打码，如实读取）。
- 修复（extract.js cleanBossNoise，仅对 BOSS 或含水印的文本生效）：
  删零宽字符、删水印「BOSS直聘」、删「立即沟通/继续沟通/微信扫码分享/
  不适合职位描述」（任何位置）、删独立成词的「收藏/举报/分享」（仅顿号/逗号
  分隔时，避免误伤「收藏品」「举报机制」）、折叠删词后的连续逗号。
  只删已知噪声，不做任何“聪明”改写。
- 测试页注入水印+噪声，E2E 4b 增加 5 项断言（水印/零宽/噪声词不得进入正文、
  清理后句子完整），**11/11 通过**。
- 踩坑记录：清理最初挂在 site==="BOSS_ZHIPIN" 条件上，测试页 hostname 是
  127.0.0.1 → 清理被跳过、4b 失败；改为「BOSS 站点或正文含水印」双条件。
  另：next start 只在启动时扫描 public/，改测试页后需重启 Web 才生效（本轮
  恰好服务已重启过，curl 验证生效）。

### 扩展 v1.3.4：导入默认直接进工作台（消掉「候选草稿」这一步的困惑）

- 用户反馈：「导入成功了但工作台看不到」。核查结论：**工作台没错**——
  工作台读 job_missions（正式岗位），而扩展导入先进 candidate_jobs（候选草稿，
  `imported_mission_id` 为 NULL），必须在岗位库再点一次「导入」才成为正式岗位。
  对「在 BOSS 上读一个岗位、立刻想在工作台分析」的场景，这一步是纯摩擦。
- 修复：
  1. background 的 save 默认带 `import_to_mission: true`（后端 /extension/job-import/save
     本来就支持该字段），读一个就落一个正式岗位；
  2. 弹窗新增复选框「导入后直接进入工作台」（默认勾上，可取消退回候选草稿）；
  3. 导入结果文案明确说明落点（工作台 / 岗位库候选草稿），不再让人猜。
- 同时把用户已导入但卡在候选草稿的三条真实岗位用 API 推进了工作台
  （美菜·供应链产品经理、焱法科技·产品实习生、焱法科技·AI研发实习生；
  job_missions 由 121 → 124）。
- 回归：扩展 E2E 11/11。

### v1.3.4 补全：后端 extension_save 漏掉 import_to_mission（半截修复）

- 用户第二次反馈：「又读了新的岗位，工作台还是不更新」。核查：新导入的
  明树数据·AI实习生（09:43）、GatherOne·产品一号位（09:42）仍是候选草稿
  （imported_mission_id 为 NULL）。
- 根因：上一轮只改了扩展侧（save 带 import_to_mission=true），但**后端
  `/extension/job-import/save` 完全没处理该字段**（只有 `save_manual` 处理了），
  所以不管扩展怎么传，都被丢掉 → 仍然停在候选草稿。
- 修复（两侧都补齐）：
  1. 后端 `extension_save` 补上与 `save_manual` 一致的 import_to_mission 处理，
     返回 mission_id / mission_reused / mission_error；
  2. 新增后端回归测试 `test_extension_save_import_to_mission_lands_in_workbench`
     （断言进工作台 + 不带字段时仍是草稿），manual_import 测试 **24/24 通过**；
  3. 扩展自愈：save 返回没有 mission_id 时，扩展自己再调一次
     `/candidate-jobs/{id}/import`——这样在本机服务还没重启到新版后端时也能直接进工作台；
  4. 弹窗以返回结果为准说明落点（进工作台 / 失败原因 / 仍是草稿），不再靠前端猜。
- 同时用 API 把用户卡在草稿的两条推进工作台（job_missions 124 → 126，
  五条 BOSS 岗位全部可见）。
- 教训：跨端字段（客户端新增参数 → 服务端必须接住）要**同时**加端到端断言，
  只改一侧会变成假修复；本次是后端测试才暴露的。

### 修复「岗位库显示 0」+ 两处建议相关性缺陷（2026-10-17 晚）

- 用户反馈：岗位库页面「已保存岗位（0）」，且质疑统计页大量数据是测试集。
- 核查结论：
  1. 岗位库按 profile_id 过滤；浏览器 localStorage 没有档案 ID 时页面直接不发请求
     → 永远显示 0。数据实际都在（档案 0e5d9c0d 名下 11 条，含 5 条真实 BOSS 岗位）。
  2. 统计页数字基本全是测试种子：262 个简历档案几乎全部是「孙七」等批量种子
     （用户真实档案 0e5d9c0d 甚至还没有简历：0 经历/0 教育/0 技能）；
     124 个正式岗位中 119+ 条是种子，5 条真实 BOSS 导入；候选 229、定向简历 101 等同理。
- 修复：
  1. 后端新增 `GET /api/v1/profiles`（轻量档案列表）；
  2. 岗位库页面在本地无档案 ID 时自动取第一个档案并写入 localStorage（提示「已自动选择档案」），
     与扩展保存时「取第一个档案」的兜底逻辑对齐，两端落到同一档案；
  3. 相关性修复一：`_bullet_claim_status` 不再把 REJECTED 要点当 SUPPORTED——
     用户明确拒绝的简历要点此前会带证据混进「已验证事实」，污染面试题与建议；
  4. 相关性修复二：题库生成新增门槛条件过滤（学历/年限/相关专业等），
     不再产出「你如何满足本科及以上学历」这类无效题。
- 验证：题库测试 11/11（新增 2 条相关性回归），题库+面试+导入 36/36；
  真实 GatherOne 岗位重新生成：门槛题 0 条，题目全部锚定真实 JD 要点
  （ComfyUI/LoRA、AIGC 技术栈、0到1 SaaS、短剧 SOP 等），NO_VERIFIED_EXPERIENCE 风险标记诚实。
  test_claim_provider 1 例失败在基线（stash 后同样失败）即已存在，与本次无关。
- 坑：直接操作 SQLite 时 UUID 是 32 位 hex（无连字符），带连字符的 WHERE 条件静默匹配 0 行。

### 岗位体验重构：统一档案身份 + 删「简历来源」步骤 + 精简岗位广场（2026-10-17 晚 2）

用户五点反馈：①岗位匹配侧栏让「先去简历中心上传简历」，但已上传；②岗位流程里的
「简历来源」三选一多余；③岗位广场（/jobs）混乱，只留手动导入+岗位库并重编号；
④进入岗位分析后应能直接开始优化，不要每次重传 PDF/重复点击；⑤一切基于简历中心那份简历。

- 根因（档案分裂）：简历中心上传会新建档案（示例用户 cf5c774b），而此前扩展导入的
  5 条真实岗位挂在空档案 0e5d9c0d（「取第一个档案」兜底所致）→ 匹配分析读的是
  没简历的档案 → 提示去上传简历。且重复上传同一 PDF 会再建一个档案（19:01/19:09 两份）。
- 修复：
  1. 数据迁移：0e5d9c0d 名下全部真实数据（5 missions/6 candidates/题库等）迁到
     cf5c774b；删除重复上传产生的旧档案 98faa1f4；
  2. GET /api/v1/profiles 与 extension_save 兜底排序改为「有简历者优先（最新在前）」
     ——所有「取第一个」的兜底从此都落在有简历的档案上；
  3. 简历中心：已有档案时上传改走 POST /profiles/{id}/resumes（换文件重解析，
     档案 ID 不变，岗位/投递记录保留），不再新建重复档案；
  4. mission-page：进入简历步骤自动绑定「已有简历」（bindResume 支持显式 mode），
     仅在无简历/绑定失败或用户主动「更换简历来源」时才显示三选一；
     岗位页「下一步」改为「开始简历优化」；
  5. /jobs 岗位广场精简：删除「一键采集岗位」（RemoteOK/Greenhouse/Lever）与
     「采集结果」两个区块及全部相关状态/回调，保留「1 · 手动导入」+
     「2 · 已保存岗位」，标题改为「岗位导入与岗位库」。
- 验证：tsc 通过；manual_import+question_bank 35/35。

## 2026-10-17 晚：第七轮反馈（排版/题库/顺顺）

用户反馈（含 3 张截图）：①经历卡「产品负责人」与「AI Career OS…·时间」上下位置要互换；
②简历改写要支持 STAR / STAR-C / 能力证据链三框架并由 AI 判断套用；③证书别硬性识别，
四六级并入技能；④技能分类后每类独占一行；⑤面试题库按宝洁八大问组织；⑥顺顺发送报
network error；⑦题库要随反复面试积累、支持定向回答与模拟面试闭环。

- 修复：
  1. 顺顺 network error 根因：assistant_routes.get_db_gen 直接读 DATABASE_URL 环境变量，
     本地模式（数据集指针）下为空 → SSE 流中途 RuntimeError。改用
     local_mode.resolve_database_url()，与 get_db 同源；岗位上下文读取挪进 try；
     前端把裸 network error 换成中文可操作提示，createConversation 挪进 try。
  2. 证书→技能：resume_normalization（CET 不再提升为证书、显式 CET 证书降级为技能）+
     main.py 确定性恢复（_recover_explicit_cet_skills，CET 移出 _EXPLICIT_CREDENTIAL_PATTERNS，
     LLM 提示词同步）+ 存量数据迁移（cf5c774b 的「六级（504）」→ 技能 CET-6）。
  3. 技能分类每类一行：resume_studio_typst/base.typ（每组一个 block，去掉组间「；」）；
     投递版导出 export-target-resume.ts 用 groupSkillNames 每类一行。
  4. 经历卡标题互换：mission-page.tsx 新增 experienceHeading（项目名+时间在上、角色在下），
     原始简历列/经历筛选/暂不放入/待改写卡全部同步；export experienceHeading 改 org 在前。
  5. STAR 框架：mission_provider build_target_resume 提示词要求每段经历选
     STAR / STAR-C / 能力证据链并写入 reason 开头「改写框架：X（理由）」；
     前端 RewriteReason 解析成徽章展示。
  6. 宝洁八大问：question_bank_service 新增 BEHAVIORAL_8 分类与 8 道能力题（目的性/领导力/
     计划性/说服力/协作力/创新性/前瞻性/学习力，要求按 STAR 作答）；classify_question 支持
     行为面归类；模拟面试 BEHAVIORAL/MIXED/HR 类型优先出八大问；前端分类标签同步。
  7. 面试积累闭环：generate_bank_from_context 自动回流 interview_records（REAL_INTERVIEW
     真题，带「你当时的回答已存档」）与已完成的 mock_interview_sessions（练习题，带改进建议），
     按题面去重、幂等，岗位相关记录优先。
- 验证：后端全量 922 passed（7 失败均为基线既有：claim_provider/gap_analysis/market_profile/
  priorities/repeated_education_merge/roadmap/target_jobs，stash 基线复核确认）；tsc 通过；
  export-target-resume 测试通过。
