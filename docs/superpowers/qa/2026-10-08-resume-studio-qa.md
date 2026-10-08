# Resume Studio QA Gate Report

Project: `AI Career OS`
Project root: `G:\myself\ai-career\.worktrees\resume-studio`
Date: 2026-10-08

## 任务

交付岗位专属完整简历工作台：18 套真实 Typst 模板、同一修订版的 Agent/网页编辑、事实核对、实际页面预览与可下载 PDF。

## 1. Entry Check

- 已读取：项目 `README.md`、既有像素 UI 规格、Resume Studio 设计规格与实施计划、`G:\_codex_workflow` 的用户工作流说明。
- 已确认不存在：本项目根目录的 `AGENTS.md`、`00-项目索引.md`、`00-当前状态.md`。
- 当前主文件：`apps/api/app/resume_studio_*`、`apps/web/app/resume-studio/`、`apps/web/app/missions/[missionId]/resume/studio/page.tsx`。
- 结论：在独立 Git 工作树实施，没有覆盖主检出的未提交面试记录工作。

## 2. Verification Check

### 证据

- Typst CLI：`typst 0.15.1 (9dfd3a08)`；当前机器 `typst fonts` 可见 `Microsoft YaHei` 和 `Arial`。模板源与虚构样本为项目原创，二进制与字体未提交。
- 渲染：针对性 pytest 实际编译全部 18 个 manifest，检查 PDF 头、每页 SVG、页数、姓名可提取及节点热区；两份不同简历得到不同可选中文字。`23 passed`，包含迁移链、来源变更、冲突、事实阻塞与面试桥接。
- API 完整回归：`598 passed, 3 failed, 5 skipped`。三个失败分别来自原有 `test_claim_provider_normalizes_partial_claim_schema`、`test_mission_provider_classifies_structured_output_failures`、`test_claim_analysis_fingerprint_requires_regeneration_after_profile_change`；开工前同三项已失败。新增迁移链测试已更新并通过。
- Web：`npm test` 为 `175 passed`；`npm run type-check` 通过；`npm run build` 完成生产编译和全部路由生成。G 盘 `readlink` 返回异常通过项目内仅对 G 盘生效的兼容脚本处理。
- 浏览器：在 1265px 桌面与 390px 手机视口实测工作台；点击真实预览姓名并保存，修订号从 1 到 2；核对事实后到 3；切换模板后到 4；中文与英文画廊各 9 张真实样本页显示；手机预览点击后自动进入编辑视图。截图在浏览器验收中已检查，但未归档为仓库 PNG。
- PDF：浏览器确认后下载；API 返回 `200`、`attachment` 和 `Ada%20Lin-Acme-PM-zh.pdf` 文件名。保存的虚构样本 PDF 为 26,357 字节、1 页，PyMuPDF 可提取 `Ada Lin` 和 `Built product evaluation dashboards`。
- `python -m compileall -q app` 与 `git diff --check` 通过。

### 推断

- 同一修订版生成预览与 PDF、内容变更使旧确认失效、显式来源重新导入与不覆盖原则都有服务端测试支撑。
- 浏览器移动版与模板画廊已人工确认可见；未建立自动化视觉回归门槛。

### 未验证

- 无专用 PostgreSQL `TEST_DATABASE_URL`，未运行 PostgreSQL 集成门槛。整条旧 Alembic 链无法在 SQLite 完整升级：既有 002 迁移使用 SQLite 不支持的约束 `ALTER`。新迁移结构和链关系由测试覆盖。
- 当前机器没有 Noto Sans CJK SC / Libertinus Sans 系统字体；其他平台的字形回退、部署字体配置仍需发布环境检查。
- PyMuPDF 的 AGPL-3.0/商业许可边界需在公开分发前按部署方式复核，见 `docs/licenses/resume-studio-NOTICES.md`。

## 3. Preservation Check

- 所有开发在 `feat/resume-studio` 独立工作树进行；主检出的未提交工作保持原样。
- 原 `TargetResume` 作为历史改写账本保留。新版改写只显示差异，主动重新导入前不覆盖 Studio 精修内容。省略内容保留追溯记录。
- 许可证及版本信息、设计决策、构建环境处理写入项目文档；真实用户简历、数据库、Typst 二进制不进 Git。

## 4. Missed-Scope Check

- 并行的 `aioscaree-UI` 工作尚需在其提交后做最终分支集成；它会触及 `mission-page.tsx`、`package.json` 与全局 CSS。
- 现有导出打印函数留在旧页面源中作为遗留代码，但用户可见入口已指向 Studio 的真实 PDF 流程；后续可删去死代码。

## 5. Innovation Check

- 下一步最有价值的增强是“事实变更影响图”：用户改动一个量化主张时，自动定位 Profile 证据、目标岗位改写和面试问题中的引用，并显示哪些输出需要重新确认。

## 6. Gap Check

- 当前热区宽度依据 Typst 锚点与页面余量估算；极端长文本、两页跨页布局需要更细粒度的视觉回归样本。
- 需要把桌面和手机的浏览器验收截图持久化，并在发布环境以真实字体、PostgreSQL 和 PDF 文本抽取复验。

## Final Decision

- 核心 Resume Studio 可在独立工作树中运行并展示；正式合并需完成并行 UI 分支冲突检查与回归。
- 三个既有 API 失败不由本次改动引入，未把全套 API 错报为通过。
