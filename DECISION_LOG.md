# AI Career OS 决策记录

## 2026-10-08 三线集成

- 基线采用 `feat/resume-studio` 的 `7a60118`，在 `feat/aioscareer-combine` 独立工作树正式合并 `feat/pixel-ui-copy` 的 `1ac2934`，保留双亲历史。依据：`git range-diff` 显示 Resume 分支摘取的 UI 补丁只在 Studio 入口和构建脚本处有意分歧。
- 最终简历的 PDF 操作进入 Resume Studio，保留 UI 分支的四阶段导航和预览行为。依据：`mission-page.tsx` 的真实冲突、Studio PDF 服务端路由和模板验收。
- 原主检出的面试记录库按文件级只读移植，保留原主检出和 `image/`；`main.py`、`models.py`、`missions-home.tsx` 做语义合并，避免覆盖 Studio 或像素 UI。
- 迁移保留 `014_resume_studio`，面试记录改为 `015_interview_records` 并接在其后。依据：原两条工作均占用 014，Alembic 图与隔离升级/降级测试。
- 删除岗位时保留用户写的真实面试记录并清除 `mission_id`，删除档案时清除记录和题目；Studio 文档在两种删除路径中清理。依据：本地 SQLite 关闭外键时的回归测试与 PostgreSQL 外键语义。
- 面试记录 PATCH 与新建采用相同的岗位归属、轮次、必填字段和问答排序约束。替换问答时先 flush 删除旧行，再插入新行，避免 `(record_id, sort_order)` 唯一键冲突。依据：独立代码审查、红灯复现和回归测试。

不要把早期 `014_interview_records` 或 UI 的浏览器打印 PDF 入口混回当前产品。
