# 简历 UI 与内容 QA（2026-10-09）

## 交付范围

- 上传页：缩小标题，上传与已有档案并列，文件选择控件统一视觉样式，档案 ID 恢复折叠显示。
- 技能：事实核对页按类别合并显示；熟练度与证据保留在展开区；Typst PDF 将技能压成横向分类段落，并保留各项可编辑节点。
- 项目：模型产生的同一项目要点合成一份审阅建议，前端分条展示，Studio 导出恢复分条。新增事实确认约束，避免无证据要点自动进入 PDF。

## 验证证据

- `apps/web`: `npm test` → 194/194；`npm run type-check` → 通过；`npm run build` → 通过。
- `apps/api`: `pytest -q` → 614 通过、5 跳过、3 失败；相关功能和 Typst 渲染测试通过。
- 三项全量失败在独立的 `822403c` 干净工作树用相同 Python 环境复现：`test_claim_provider_normalizes_partial_claim_schema`、`test_mission_provider_classifies_structured_output_failures` 中的 schema_validation 参数、`test_claim_analysis_fingerprint_requires_regeneration_after_profile_change`。它们不是这次改动引入。
- 浏览器查看桌面上传页；390 px 宽度下两个卡片各宽 343 px，页面滚动宽度 375 px，小于 390 px 视口。
- 使用虚构简历与 22 个技能词条生成真实 PDF：1 页，22 个技能均保留，分类段落自然换行，项目要点与标题未重叠。中间 QA 文件保存在 `.runtime/qa-structured-resume.pdf` 与 `.runtime/qa-structured-resume.png`，未提交。

## 保留的边界

- 已保存的岗位版本不自动改写；通过页面上的“重新生成岗位版本”获取新结构，避免覆盖用户已确认或编辑的内容。
- 项目数字、奖项、技术工具以已确认简历事实为依据；提示词要求 2–4 条，但事实稀疏时允许更少条，避免补写未经证实的结果。
- PostgreSQL 旧库升级及外部部署仍待独立验收。
