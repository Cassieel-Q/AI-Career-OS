# 已知问题与未完成事项

分支：`feature/boss-local-app` · 记录时间：2026-10-17

## 一、环境层面的坑（不是代码缺陷，但会影响结论）

| # | 问题 | 影响 | 状态 |
| --- | --- | --- | --- |
| 1 | **G 盘是 exFAT 移动硬盘**（My Passport） | 不支持符号链接；`readlink` 返回 `EISDIR`（已有 `next-g-drive-fs-compat.cjs` 兜底）；I/O 很慢，一次 `npm install` 约 25 分钟、`next build` 明显偏慢 | 已规避（构建脚本内置 D 盘 NTFS 隔离兜底） |
| 2 | **`apps/web/node_modules` 曾严重损坏** | 322 个包目录还在，但 `next/package.json`、`next/dist/bin/next`、`react/package.json` 等文件全部丢失（整棵树只剩 158 个文件）。推测为移动盘掉盘/非正常移除导致 | 已修复：重新 `npm install`（370 个包，25 分钟） |
| 3 | **8000 端口是另一个项目 CityQuest** | 之前 `start-local.cmd` 默认起在 8000，容易与它冲突 | 已规避：启停器把 8000 视为「他人端口」，永远不抢占、不停止；AI Career OS 用 8100 |
| 4 | 本机存在 `HTTP_PROXY` 环境变量 | 会让 httpx / 浏览器把 `127.0.0.1` 也走代理导致 404 | 启停器的健康检查显式 `Proxy = $null`；E2E 用 `fetch` + 浏览器 |

## 二、功能层面的未完成 / 受限项

| # | 项 | 状态 | 说明 |
| --- | --- | --- | --- |
| 5 | 真实 BOSS 直聘页面读取 | `BOSS_REAL_SITE_PENDING_USER` | 需要你本人登录。扩展与复制粘贴两条路都已就绪，你回来后只需：登录 BOSS → 打开一个职位页 → 点扩展图标「读取当前岗位」→ 核对字段 → 导入。若平台不允许自动读取，就退回复制粘贴（这条已完全可用） |
| 6 | 浏览器扩展在 Edge 的实机加载 | `DONE_UNVERIFIED` | 代码、权限、鉴权、安全测试都已完成，但**没有真人在 Edge 里加载并点过**。需要你执行一次：`edge://extensions` → 开发人员模式 → 加载解压缩的扩展 → 选 `apps/extension` |
| 7 | 桌面快捷方式的双击验收 | `PARTIAL` | 脚本已写好并可执行，实机验收要等 production 构建完成后统一跑 |
| 8 | 后端全量测试有 1 项受环境影响的失败 | 已确认与本次改动无关 | `test_bind_resume_records_version_revision_and_pdf_snapshot` 曾报「Typst 排版超时」；CPU 空闲后复跑通过。全量 916 passed / 7 failed，这 7 项在基线提交 `c3268ac` 上单独复跑**同样失败**，属既有问题 |

## 二·补、本轮修掉的真实缺陷（都是实机踩出来的）

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 9 | 「采集当前网页」报 `浏览器桥拒绝了本次调用（令牌不匹配）` | 本机同时存在**两个桥**（手动 `start-browser-bridge.cmd` 起 8770、桌面启动器起 8771），令牌文件 `<数据目录>/browser-bridge.token` 只反映最后启动的那个；后端写死连 8770，于是永远对不上 | ① 启停器**先起桥再起后端**，并把实际端口以 `BROWSER_BRIDGE_URL` 注入后端进程；② 启动时清理多余的本桥（`Stop-StrayBridges`）；③ 后端 `webform_browser.bridge_url()` 在未显式配置时按 8770–8773 探测真实在跑的桥（`service == ai-career-os-browser-bridge`） |
| 10 | 用相对路径启动的桥（`node scripts/browser-bridge.cjs`）不被识别成本项目进程 | 归属判定只看命令行里有没有项目路径 / `ai-career`，相对路径命令行两者都没有 → 既不能复用也不能清理，长期占着 8770 | `Test-OwnedByApp` 增加规则：命令行匹配 `scripts[\\/]browser-bridge\.cjs` 视为本项目 |
| 11 | 岗位名被解析成「招聘 产品经理（AI方向）」 | BOSS 首行常带「招聘/诚聘/急招」等前缀，解析器原样保留 | 新增 `_ROLE_PREFIX_RE`，对 `provided` / 标签行 / 启发式三条来源都在最后统一剥离 |
| 12 | 来源被虚标：扩展解析时缺省 `source_site` 会被补成 `BOSS_ZHIPIN` | `payload.source_site or "BOSS_ZHIPIN"` 永远不会命中——模型默认值 `"UNKNOWN"` 是真值；反过来若真有空值则把任意网页标成 BOSS 采集 | 改为 `(payload.source_site or "").strip() or "UNKNOWN"`，扩展按页面域名如实上报 `BOSS_ZHIPIN / OTHER / UNKNOWN` |
| 13 | 开发模式 `next dev` 清空 `.next`，把 production 构建删掉（用户因此打不开工作台） | dev 与 prod 共用 distDir | `next.config.mjs` 支持 `NEXT_DIST_DIR`，dev 走 `.next-dev` |

## 三、明确不做（按你的要求 & 平台规则）

- 不做 Electron / Tauri / PyInstaller / NSIS 安装包；
- 不自动登录任何招聘平台、不读取 Cookie / 密码 / 验证码 / 聊天记录；
- 不实现无人值守自动开聊、批量群发、自动海投；
- 不使用隐藏私有接口、不伪装指纹、不绕过反自动化措施；
- 不把岗位数据上传到任何外部服务器（扩展只与 `127.0.0.1` 通信）；
- 不删除、不覆盖用户数据集；不合并 main。

## 四、需要你参与的最小动作

1. 双击桌面「AI Career OS」（我会在构建完成后创建），确认能开；
2. 打开一个 BOSS 职位页 → 点扩展图标 → 生成配对码 → 配对 → 读取 → 导入；
3. 在岗位页点「生成 BOSS 打招呼」→ 复制 → 到 BOSS 粘贴发送（这一步只能你手动发）。
