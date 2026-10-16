# 48 小时 ResumeForge 对齐冲刺 · 真实验收报告

> 日期：2026-10-16
> 分支：`feature/resumeforge-48h`（基线 `main` = `b6b806e`）
> 数据目录：`%LOCALAPPDATA%\AICareerOS`（本地优先模式，仅监听 `127.0.0.1`）
> 原则：**只记录真实结果**。未验证的一律标未完成/未验证，不用计划替代交付。

---

## 0. 运行方式（Windows 一键）

| 脚本 | 作用 |
|---|---|
| `start-all.cmd` | 初始化本地库 + 后端 API(8100 可配 8000) + 前端(3000) + 受控浏览器桥(8770) |
| `start-local.cmd` | 本地优先模式：初始化 `%LOCALAPPDATA%\AICareerOS\career.db`，启动 API + 前端 |
| `start-browser-bridge.cmd` | 只启动受控浏览器桥（网申填表用） |
| `start-demo.cmd` | 旧的演示库模式（路径已改为相对仓库根，不再硬编码 `G:\`） |

后端：`cd apps/api && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100`
（`AI_CAREER_DATA_DIR` 指定数据目录，`DATABASE_URL` 指定 sqlite 文件）

> 说明：本机 8000 端口已被另一个无关服务（CityQuest API）占用，因此验收全程使用 8100；
> 默认端口仍是 8000，脚本未改动这一点。

---

## 1. 测试结果（真实运行）

### 后端（`apps/api`，`python -m pytest -q`）

| 指标 | 数值 |
|---|---|
| 通过 | **777** |
| 跳过 | 5 |
| 失败 | 7（**全部为改动前既有失败**） |

- 已在 `git stash` 掉的基线上单独重跑这 7 个测试文件：**同样 7 failed / 185 passed**，
  因此本轮改动**没有引入新的后端失败**。
- 既有失败清单：`test_claim_provider`、`test_gap_analysis`、`test_market_profile`、
  `test_priorities`、`test_resume_reliability`、`test_roadmap`、`test_target_jobs`（各 1 项）。
- 本轮新增测试 **40 项全部通过**：
  `test_webform_matching.py`（8）、`test_backup_restore.py`（6）、`test_job_ingest.py`（10）、
  `test_webform_routes.py`（4）、`test_alembic_revisions.py`（10，含新增迁移链校验）、
  以及其余相关用例合计 40。

### 前端（`apps/web`）

| 指标 | 数值 |
|---|---|
| 测试总数 | 243 |
| 通过 | 241 |
| 失败 | 2（**改动前既有失败**，基线同样 243/241/2） |

- `npm run type-check`：**通过**（`tsc --noEmit` 无错误）。
- `npm run build`：本机在 `.next/trace` 上报 `EPERM`（Windows/G: 盘文件锁），属环境问题；
  `next dev` 可正常编译并返回 200，路由类型已正确生成（`/jobs` `/webform` `/settings` 均被识别）。
- 既有失败的 2 项：`workflow-navigation`（期望英文 `Role Selection`，实际中文 `角色选择`）、
  `workflow-state`（首页重定向断言与当前实现不符）。

---

## 2. 网申填表 E2E（真实浏览器 + 真实 API）

脚本：`apps/api/scripts/e2e_webform.py`
环境：本地测试表单页 `apps/web/public/webform-test.html`（经 `next dev` 在 `127.0.0.1:3000` 提供），
受控浏览器桥为真实 Playwright Chromium 会话（验收时以 `BROWSER_BRIDGE_HEADLESS=1` 无头运行，
默认配置为有头可见窗口）。

**结果：33 / 33 全部通过。**

关键结论：

- 读取到 15 个字段；匹配出 11 项可直接填写（姓名、手机、邮箱、城市、学校、学历、专业、毕业时间、到岗时间、家庭情况等）。
- 写入后**回读页面**校验：姓名 `张三`、手机 `13800000000`、邮箱 `zhangsan@example.com`、
  学校 `示例大学`、下拉框 `硕士` 均真实写入页面。
- **密码框、验证码框保持为空**（写入前后都被拦截）。
- 填写结果 `summary.submitted = false` —— **永不提交**。
- 填写历史落库 1 条，且历史文本中**不含任何密码值**。

### 控件支持程度（明确区分）

| 控件 | 支持程度 | 实测结果 |
|---|---|---|
| 文本框 / 多行文本 / 邮箱 / 电话 | **FULL** | 真实写入并回读校验通过 |
| 下拉框（select） | **FULL** | 选项能匹配时选中「硕士」；匹配不到则标记「待确认」 |
| 日期（date / month） | **PARTIAL** | 值无法标准化为日期时标记「待确认」 |
| 单选框（radio） | **PARTIAL** | 选项文本能匹配才勾选；否则「待确认」 |
| 复选框（checkbox） | **LIMITED** | 仅支持单一确认型勾选 |
| 文件上传（file） | **UNSUPPORTED** | 明确提示「请手动选择文件」 |
| 密码 / 验证码 / 隐藏域 / 提交按钮 | **BLOCKED** | 永不填写，也不进入历史 |

> **未验证**：真实第三方网申页面（需要登录态与验证码），本轮**没有**做真实站点验证，也不做任何宣称。

---

## 3. 岗位采集：真实来源与真实结果

来源：**RemoteOK 官方公开 JSON 接口**（`https://remoteok.com/api`，无需登录，未做任何绕过）。

证据文件：`docs/evaluation/resumeforge-48h/remoteok-collection.json`

| 步骤 | 实测结果 |
|---|---|
| 采集（关键词 `product manager`） | 状态 `OK`，返回 8 条真实在招岗位 |
| 保存进岗位库（前 4 条） | 保存 4 / 跳过 0；岗位库 4 条 |
| 同一批重复保存 | 保存 0 / 跳过 4，原因全部为 `DUPLICATE`；岗位库仍为 4 条 |
| 记录字段 | 公司 / 岗位 / 地点 / 来源链接 / 采集时间 / 解析状态 全部落库 |

真实采集样例（原文照录）：

- Thyme Care — Principal Product Manager Strategic Initiatives — Remote
- Bjak — Technical Product Manager AI Stockbroking App — Germany
- Magic Eden — Senior Growth Product Manager AI Native — Melbourne
- DomainTools — Principal Product Manager — Remote

其它入口实测：

| 入口 | 实测结果 |
|---|---|
| 粘贴 JD | 解析并保存到岗位库（`PASTE`） |
| 公开链接 | 公开页面抓取 → 成功时 `PARSED`；403/429 → `BLOCKED`；HTTP 404 → `ERROR` 并提示手动粘贴，**不做任何绕过** |
| PDF / txt / docx 上传 | `PARSED`（txt 实测通过；docx 走 zip+XML 抽取，有单测） |
| 图片上传 | `UNSUPPORTED_IMAGE` — 明确提示不支持自动 OCR，需手动粘贴 |
| 筛选 | 关键词 / 公司 / 地点 / 类型（候选草稿 | 正式岗位）均实测可用，返回 facets |

---

## 4. 备份与恢复（真实往返测试）

脚本：E2E 第 7 段（`e2e_webform.py`）+ `apps/api/tests/test_backup_restore.py`

真实执行链路：**建立数据 → 导出 → 完整性校验 → 恢复为新数据集 → 核对记录**

| 检查项 | 实测结果 |
|---|---|
| 导出 | 19,659 bytes 的 zip（含 `manifest.json` + `data/career.db`） |
| 完整性 | SHA-256 逐文件校验 **通过**；被篡改的档案会被拒绝恢复（有单测） |
| 清单计数 | `user_profiles: 5, education: 2, application_profiles: 2, web_form_records: 2` 等真实计数 |
| 恢复 | 生成新数据集 `ds2610162021590a18`，**不覆盖**原数据集（`previous_dataset_id` 与新 id 不同） |
| 恢复后核对 | 切换指针后回读，`user_profiles` 仍为 5，记录一致 |
| 密钥排除 | 备份内容中不含 `OPENAI_API_KEY` 的值（`.env` 不入库、不入包；manifest 明确列出排除项） |

---

## 5. 实际生成的 PDF

- 产物：`.runtime/e2e-resume.pdf`（**39,270 bytes**，1 页，文字可提取）
- 链路：建档案 → 建岗位（粘贴 JD）→ 绑定 Master 简历 → 经历四分类 → 确认筛选 →
  简历策略 → 确认策略 → 生成定向简历 → 确认 → 创建 Studio 文档（`zh-classic`）→
  Studio 确认（`If-Match` 修订号）→ 导出 PDF（**14 步全部 HTTP 200**）
- 脚本：`apps/api/scripts/e2e_resume_pdf.py`
- 校验：PDF 文字可提取，包含姓名；页数为 1（Studio 自检要求 1–2 页）
- 说明：仓库 `.gitignore` 有 `*.pdf` 规则，因此该 PDF **不进入版本库**；
  已归档到 `docs/evaluation/resumeforge-48h/e2e-resume.pdf` 供本地查看，
  任何环境下重跑 `scripts/e2e_resume_pdf.py` 可再次生成。

---

## 6. 浏览器截图（真实本地运行）

目录：`docs/screenshots/resumeforge-48h/`，机器可读报告 `report.json`（含 HTTP 状态与控制台错误）。

| 文件 | 页面 | HTTP |
|---|---|---|
| `01-jobs-intake.png` | `/jobs` 岗位统一入口 + 岗位库筛选 | 200 |
| `02-webform.png` | `/webform` 网申填表（显示「已连接 / 会话已开启」） | 200 |
| `03-settings.png` | `/settings` 本地模式 / 数据集 / 备份恢复 | 200 |
| `04-webform-test-page.png` | `/webform-test.html` 本地测试表单 | 200 |

截图脚本：`apps/web/scripts/capture-48h.cjs`（Playwright 真实 Chromium，1440×900）。

---

## 7. 已知失败与未完成（如实记录）

1. **后端 7 项、前端 2 项既有测试失败**仍在，均为改动前既有，本轮未修复（不在本次范围）。
2. **Studio「一键更新到 Studio」的 UI 未新增**：后端 `source-diff` 与 `reimport`（带 `If-Match`）
   已存在且可用，但缺少「差异弹窗 → 确认 → 一次性替换」的页面交互。
3. **求职管理补强未做**：打招呼话术、面试时间提醒、投递绑定的简历 PDF 版本。
4. **真实第三方网申站点未验证**：只完成本地测试页 E2E。
5. **图片岗位截图 OCR 未实现**（明确返回不支持）。
6. **自动投递未实现**（有意为之：需绕过登录/反爬，需求禁止）。
7. **PostgreSQL 未验证**：新增迁移 `026_webform_and_ingest` 只在 SQLite 上跑通；
   与既有 `013 → 026` 链的 PostgreSQL 升级未验证。
8. **`npm run build` 在本机报 `.next/trace` EPERM**：环境/文件锁问题，非代码问题；
   `next dev` 与 `tsc --noEmit` 均通过。

---

## 8. 如何复现全部验收

```bat
REM 1) 初始化本地库
cd apps\api
set AI_CAREER_DATA_DIR=%LOCALAPPDATA%\AICareerOS
set PYTHONPATH=.
.venv\Scripts\python.exe scripts\init_local_db.py

REM 2) 启动三件套（另开窗口）
start-local.cmd
start-browser-bridge.cmd

REM 3) 网申 + 备份恢复 E2E
set AIOS_API=http://127.0.0.1:8100
.venv\Scripts\python.exe scripts\e2e_webform.py

REM 4) 真实 PDF
.venv\Scripts\python.exe scripts\e2e_resume_pdf.py

REM 5) 测试
.venv\Scripts\python.exe -m pytest -q
cd ..\web && npm test && npm run type-check && node scripts\capture-48h.cjs
```
