# AI Career OS × ResumeForge 对齐与复用台账

> 日期：2026-10-16
> 工作分支：`feature/resumeforge-48h`（从 `main` = `b6b806e` 切出，不动 `main`）
> 参考项目：ResumeForge（MIT，`https://github.com/magicapple123/ResumeForge`，本地克隆于 `G:\myself\resumeforge-ref`）
> 原则：**能在 AI Career OS 内改造就不重写；能复用逻辑就不重造 UI**。技术栈保持 Next.js 15 + FastAPI + SQLAlchemy/Alembic + SQLite/PostgreSQL 不变。

---

## 1. 关键结论（先说判断）

1. **不采用「ResumeForge 本地伴随服务 + 数据交换」的过渡方案。**
   AI Career OS 已经有完整的岗位 → 简历 → Studio → 投递 → 面试闭环，再做双应用互通会产生
   两套事实来源和两套数据边界，且需求明确禁止「把打开第二个应用伪装成统一集成」。
   因此本轮全部在 AI Career OS 内原生实现。

2. **不整包移植 ResumeForge 的 React/Vite 前端。**
   其前端是 Vite SPA + 自研路由（`App.tsx` 的 `MENU_ITEMS`），本项目是 Next.js App Router，
   整包覆盖等于重写。只复用**算法思路、字段目录、安全边界与测试用例设计**。

3. **ResumeForge 里最有价值的三块能力，本项目此前完全没有**：
   通用网申表单引擎（`services/webform/`）、本地数据集备份恢复（`services/data_backup/` + `datasets.py`）、
   受控浏览器（`services/browser/cdp_client`）。本轮按 MIT 许可**重写为 Python 侧实现**，
   保留版权与来源说明（见 §5）。

4. **ResumeForge 中大量能力在 AI Career OS 里已有等价实现**，属于「不要重复造轮子」的部分：
   岗位解析、匹配度、简历生成、事实门禁、投递状态机、面试题库、AI 助手。这些**只做接线与补强**。

---

## 2. ResumeForge 模块 → AI Career OS 现状 对照表

| ResumeForge 模块（来源文件） | 能力 | AI Career OS 现状 | 本轮决策 |
|---|---|---|---|
| `services/job/job_service.py` `jd/jd_parser*.py` | 岗位解析、JD 结构化 | ✅ 已有 `job_description_service` / `jd_analysis_provider` / `mission_service` | 复用，不重写 |
| `services/job/job_match.py` | 简历×岗位匹配度 | ✅ 已有 `job_insight_provider` / `mission_intelligence`（圆环+理由） | 复用，不重写 |
| `services/resume/*`、`prompts/*.md` | 简历定向生成、grounding | ✅ 已有 `resume_intelligence` / `mission_provider` / 事实门禁 | 复用，不重写 |
| `services/resume/resume_layout.py`、`pdf_exporter/` | 版式与 PDF 导出 | ✅ 已有 18 套 Typst 模板 + `resume_studio_render/export` | 复用，不重写 |
| `services/tracker.py`、`api/apply*.py` | 投递跟踪状态机 | ✅ 已有 `job_applications` + `/tracker` + 退回能力 | 复用，不重写 |
| `services/interview/*` | 模拟面试 / 题库 / 面经 | ✅ 已有 `mock_interview` / `question_bank` / `interview_record` | 复用，不重写 |
| `services/assistant/*` | AI 助手 + 工具 | ✅ 已有「顺顺」`assistant_service` + 工具能力 | 复用，不重写 |
| `services/webform/**`（引擎 / 字段目录 / 匹配 / 快照 / 记录 / 实时会话 / AI 兜底） | **通用网申填表** | ❌ 完全没有（只有 `application_profiles` 存资料） | **本轮原生实现**（简化版：通用读取 + 匹配 + 预览 + 受控填写 + 历史） |
| `services/browser/cdp_client/*`、`browser_manager.py` | 受控浏览器（CDP） | ❌ 没有 | **本轮原生实现**（Node + Playwright 桥，Playwright 已是本项目前端 devDependency） |
| `services/data_backup/*`、`datasets.py`、`dataset_registry.py` | 本地数据集备份/恢复/切换 | ❌ 没有（只有 `.runtime/demo-career.db` 演示库） | **本轮原生实现**（zip + manifest + SHA-256 + 恢复为新数据集） |
| `services/sites/*`（Boss 等站点适配器）、`services/apply/*` | 自动投递 | ❌ 没有 | **不实现**：需要绕过登录/反爬，需求明确禁止；只做「明确不支持自动采集」的提示 |
| `services/profile_parser`、`profile_text_parser.py` | 粘贴文本解析资料 | ✅ 已有 `resume_normalization` / `resume_sections`（PDF/文本解析） | 复用 |
| `services/share_package.py`、`trash.py`、`skill_archive.py` | 分享包 / 回收站 / 技能包 | ⚠️ 部分（无回收站） | 本轮不做 |
| `services/materials.py`、`knowledge_service.py` | 资料箱 / 知识库 | ⚠️ 部分（有 `knowledge/` 目录） | 本轮不做 |

---

## 3. 功能差距表（本轮目标 vs 实际交付）

状态口径：**完成** = 前后端已实现且有测试/实测证据；**部分** = 主干可用但范围收窄；**未完成** = 未实现。

| # | 需求 | 状态 | 落地位置 / 说明 |
|---|---|---|---|
| 1 | 保护现有项目、独立分支、不破坏 main | 完成 | 分支 `feature/resumeforge-48h`，工作树针对 `b6b806e`；未执行任何 `git clean/reset --hard` |
| 2 | 保留 Next.js + FastAPI + SQLAlchemy/Alembic 栈 | 完成 | 未更换框架；新增迁移 `026_webform_and_ingest` |
| 3 | 保留原有简历优化工作台（四分类、逐条接受/编辑/拒绝、Master 不被覆盖） | 完成（未改动） | `mission_provider` / `mission_service` / `apps/web/app/mission-page.tsx` 原样保留 |
| 4 | 保留 Resume Studio（18 套 Typst 模板、画廊、编辑、撤销重做、多修订、PDF） | 完成（未改动） | `resume_studio_*` / `apps/web/app/resume-studio/*` 原样保留 |
| 5 | 一键把已确认岗位简历更新到 Studio（差异 → 确认 → 一次性替换 → 重渲染 PDF） | 部分（复用既有实现） | 后端已有 `GET .../resume-studio/source-diff` + `POST .../reimport`（`If-Match` 并发保护）；本轮**未新增 UI**，见 §6 待办 |
| 6 | 本地优先模式（免注册、稳定数据目录、重启数据完整） | 完成 | `app/local_mode.py` + `scripts/init_local_db.py` + `start-local.cmd` |
| 7 | SQLite 持久化岗位/简历/事实/投递/面试 | 完成 | 既有表 + 新表 `web_form_records`；`init_local_db.py` 建表补列 |
| 8 | 本地业务与 PDF 导出不依赖模型 | 完成（既有） | 模型降级为本地规则；Typst 本地渲染 |
| 9 | 明确提示哪些资料会发给云模型；不默认上传敏感字段 | 完成 | 设置页「模型」区块说明 + 网申页 `sensitive_keys_used` 展示；`resume_visible_facts` 不含网申敏感字段 |
| 10 | 仅监听 127.0.0.1，不暴露公网 | 完成 | `start-local.cmd` / `start-all.cmd` / 浏览器桥均绑定 `127.0.0.1` |
| 11 | 岗位统一入口：粘贴 / 链接 / 截图 / PDF / 文档 | 完成（图片明确不支持） | `app/job_ingest_service.py` + `app/job_ingest_routes.py` + `apps/web/app/jobs/page.tsx` |
| 12 | 岗位按关键词/地点/公司筛选 | 完成 | `GET /api/v1/profiles/{id}/job-ingest/library`（含 facets） |
| 13 | 重复岗位检测 | 完成 | `dedupe_key(company, role, location)`；采集保存时跳过并说明原因 |
| 14 | 显示来源 / 采集时间 / 原文 / 解析状态 | 完成 | `candidate_jobs` 新增 `source_url` / `collected_at` / `parse_status` / `dedupe_key` |
| 15 | 真实可用的岗位采集适配器 | 完成（1 个真实来源，已实测） | **RemoteOK 官方公开 JSON 接口**（`https://remoteok.com/api`，无需登录），实测采集到 8 条真实在招岗位并成功入库；通用公开链接抓取作为第二适配器 |
| 16 | 不做绕过：不能自动采集就明确说不支持 | 完成 | `fetch_url_text` 识别登录/验证码/403/429 → `BLOCKED` 并提示手动粘贴 |
| 17 | 网申填表：读取 → 匹配 → 预览 → 填写 → 检查 | 完成 | 后端 `webform_matching.py` / `webform_routes.py` / `webform_browser.py`；Node 桥 `apps/web/scripts/browser-bridge.cjs`；前端 `/webform` |
| 18 | 使用用户明确启动的本地浏览器会话 | 完成 | `start-browser-bridge.cmd` → Playwright 持久化 Chromium，仅 `127.0.0.1:8770` |
| 19 | 未知字段标记「待确认」 | 完成 | 匹配引擎 `NEEDS_CONFIRM` 状态 + 原因 |
| 20 | 用户逐条编辑 / 勾选 / 取消 | 完成 | `/webform` 表格逐行 checkbox + 可编辑取值 |
| 21 | 点击按钮后才执行填充 | 完成 | 只有「执行填写」会调用桥的 `/fill` |
| 22 | 返回成功/失败/待确认数量与原因 | 完成 | `summary` + `results[]` + `rejected[]` |
| 23 | 区分文本框/下拉/日期/单选框支持程度 | 完成 | `CONTROL_SUPPORT`：FULL / PARTIAL / LIMITED / UNSUPPORTED / BLOCKED |
| 24 | 记录填写历史，不记录密码或验证码 | 完成 | `web_form_records`；密码/验证码在匹配与写入两侧双重拦截 |
| 25 | 永不自动点击最终提交 | 完成 | 桥与后端均拒绝 `submit/button` 控件；`summary.submitted = false` |
| 26 | 本地测试页 E2E + 尽可能验证真实网申页 | 完成（本地测试页） | `apps/web/public/webform-test.html` 覆盖全部控件类型 |
| 27 | 求职管理：收藏/备选、状态、投递日期、简历版本、打招呼话术、面试提醒、面试官问题、渠道备注、统计筛选 | 部分 | 复用既有 `job_applications`（状态/日期/渠道/备注/可退回）+ `/tracker`；**打招呼话术、面试提醒、PDF 版本绑定未新增** |
| 28 | 备份导出（DB+附件+SHA-256 清单，排除密钥） | 完成 | `app/backup_service.py` + `app/backup_routes.py` + `/settings` |
| 29 | 从备份导入恢复（预览、不覆盖、恢复为新数据集） | 完成 | `restore_as_new_dataset` + `local_mode` 数据集指针 |
| 30 | 实际「建立数据→导出→重启→导入→核对」恢复测试 | 完成 | `tests/test_backup_restore.py` + 见 §6 实测报告 |
| 31 | 自动投递与外部网站操作 | **未完成（有意不做）** | 需绕过登录/反爬，违反需求与合规要求；界面明确标注不支持 |
| 32 | 主导航整理为 首页/岗位/简历/投递/网申/面试/设置 | 完成 | `apps/web/app/app-shell.tsx`；证据库/助手/网申资料收进「工具」组 |
| 33 | 每个操作有 loading/success/failure 反馈；禁止假入口 | 完成 | 新页面均实现 busy/error/info 三态；导航指向的页面全部存在 |
| 34 | 从已保存岗位直达 定向简历 → Studio → PDF → 投递记录 | 部分（既有链路） | `/missions/{id}` 已串联；`/jobs` 行可直达岗位工作台 |

---

## 4. 系统边界（明确写清，避免误解）

- **网申资料（ApplicationProfile）与简历事实（ResumeProfile）严格分界。**
  简历生成只读 ResumeProfile；网申填表可读两者；助手默认不读网申敏感字段。本轮**未改变**该边界。
- **备份只含本机数据。** 不含模型 API Key（存放在根目录 `.env`，不入库）、Cookie、密码、验证码。
- **自动投递不做。** `/jobs` 与 `/webform` 都只到「用户确认后执行允许的操作」，任何真实提交都由用户手动完成。
- **RemoteOK 是唯一自动采集来源。** 其它平台若需登录/验证码，界面返回「不支持自动采集」，由用户粘贴导入。

---

## 5. 许可证与来源说明

- ResumeForge 采用 **MIT License**，`Copyright (c) 2026 ResumeForge Contributors`。
- 本轮**未复制 ResumeForge 的源码文件**；复用形式为：**阅读其架构文档与实现，按同等思路用本项目技术栈重写**。
  因此不产生新的许可证传染问题，但按需求保留来源说明如下：

  | 本项目文件 | 参考的 ResumeForge 模块 | 复用性质 |
  |---|---|---|
  | `apps/api/app/webform_matching.py` | `services/webform/field_catalog.py`、`field_synonyms.py`、`service/preview.py` | 字段目录与匹配思路借鉴，代码自写 |
  | `apps/api/app/webform_routes.py` | `api/webform/fill_routes.py`、「只填不交」边界 | 流程与安全边界借鉴，代码自写 |
  | `apps/api/app/backup_service.py` | `services/data_backup/*`、`datasets.py` | manifest/SHA-256/恢复为新数据集的思路借鉴，代码自写 |
  | `apps/api/app/local_mode.py` | `dataset_registry.py` | 数据集指针设计借鉴，代码自写 |
  | `apps/api/app/job_ingest_service.py` | `services/job_parser/*`、`text_extraction.py` | 正文抽取思路借鉴，代码自写 |
  | `apps/web/scripts/browser-bridge.cjs` | `services/browser/cdp_client/*` | 受控浏览器角色定位借鉴；本项目改用 Node + Playwright |

- 若后续需要**直接复制** ResumeForge 的代码片段，必须在本文件登记具体文件、行号与 MIT 许可声明。

---

## 6. 未完成 / 待办（如实记录）

1. **Studio「一键更新」的 UI**：后端 `source-diff` / `reimport` 已具备并带 `If-Match` 并发保护，
   但本轮未在 Studio 页面补「差异弹窗 → 确认 → 一次性替换」的交互，用户目前需经接口或既有入口触发。
2. **求职管理补强**：打招呼话术、面试时间提醒、投递时绑定的简历 PDF 版本，尚未新增。
3. **真实网申页面验证**：仅完成本地测试页 E2E；真实第三方网申页需要登录态，未做验证，不做宣称。
4. **图片岗位截图的 OCR**：明确返回 `UNSUPPORTED_IMAGE`，未实现 OCR。
5. **自动投递**：有意不实现。
6. **PostgreSQL 全链升级验证**：本轮新增迁移 `026` 未在真实 PostgreSQL 上跑过升级验证。
