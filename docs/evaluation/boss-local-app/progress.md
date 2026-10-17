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
