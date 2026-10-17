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
| 8 | 后端全量测试有 1 项受环境影响的失败 | 观察中 | `test_bind_resume_records_version_revision_and_pdf_snapshot` 报「Typst 排版超时」，与构建抢占 CPU 有关；将在 CPU 空闲时复跑确认 |

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
