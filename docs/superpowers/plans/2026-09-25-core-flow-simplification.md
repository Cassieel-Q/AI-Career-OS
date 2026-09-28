# AI Career OS 核心链路精简实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将岗位准备主链路收拢为“目标岗位 → 选择简历 → AI 优化简历 → 确认/导出 → 模拟面试 → 面试记录”，隐藏压力测试和 Evidence/Proof 术语，同时保留现有底层数据模型与兼容接口。

**Architecture:** 复用现有 Mission、TargetResume、InterviewPack、InterviewSession、InterviewOutcome 数据。前端只调整 Mission 导航与 mission-page 的用户文案/入口；旧 proof 路由保留但从主导航断开。后端让 InterviewPack 直接依赖已确认 TargetResume，并由 TargetResume/面经生成问题；导出函数使用 TargetResume 的 section_order（无值时教育→经历→项目→技能的保守默认顺序）。

**Tech Stack:** Next.js 15、React、TypeScript、FastAPI、SQLAlchemy、Pydantic、Node test runner、pytest。

## Global Constraints

- 不新增平行数据库模型；复用现有 Mission、TargetResume、InterviewPack、InterviewSession、InterviewOutcome。
- 主用户界面不出现 Evidence、Claim、Gap、Provider、CURATED、RAG、Interview Skills、压力测试、补强等开发术语。
- AI 优化最多展示 4 条核心建议；禁止把无证据事实写入最终简历。
- 最终导出保留原简历 section_order；未知时使用教育→经历→项目→技能→证书。
- 每个行为先写失败测试并确认失败，再实现最小改动。

---

### Task 1: 锁定核心导航、建议数量和导出顺序

**Files:**
- Modify: `apps/web/app/missions.ts`
- Modify: `apps/web/app/mission-state.ts`
- Modify: `apps/web/app/export-target-resume.ts`
- Test: `apps/web/tests/core-flow.test.mts`
- Modify: `apps/web/package.json`

- [ ] **Step 1: Write the failing test**
  - 新增测试断言主导航只显示 role/resume/interview/outcome，标签是“目标岗位/简历优化/模拟面试/面试记录”；建议上限为 4；导出 HTML 的教育 section 位于经历/项目之前，并优先使用 `section_order`。
- [ ] **Step 2: Run test to verify it fails**
  - Run: `npm --prefix apps/web test -- --test-name-pattern="core flow"`
  - Expected: FAIL，因为当前 MISSION_TABS 含 proof、标签仍是旧文案、没有建议上限/section_order 排序。
- [ ] **Step 3: Write minimal implementation**
  - 增加 `CORE_MISSION_TABS`、`CORE_RESUME_SUGGESTION_LIMIT=4`、`coreMissionTabLabel`；保留 `proof` 类型与兼容 href，但不加入 `MISSION_TABS`。
  - 为导出类型增加 `section_order?: string[]`，按 section key 渲染；缺省顺序为 education、experience、project、skills、certifications。
- [ ] **Step 4: Run test to verify it passes**
  - Run: `npm --prefix apps/web test -- --test-name-pattern="core flow"`
  - Expected: PASS。

### Task 2: 收拢 MissionShell 和简历页主交互

**Files:**
- Modify: `apps/web/app/mission-shell.tsx`
- Modify: `apps/web/app/mission-page.tsx`
- Modify: `apps/web/app/mission-state.ts`
- Test: `apps/web/tests/mission-state.test.mts`

- [ ] **Step 1: Write the failing test**
  - 增加纯函数测试：已确认 TargetResume 的下一步必须是“进入模拟面试”，不能返回压力测试；优化建议展示只取前 4 条；技术状态不应参与用户导航。
- [ ] **Step 2: Run test to verify it fails**
  - Run: `npm --prefix apps/web test -- --test-name-pattern="简历优化|核心链路"`
  - Expected: FAIL，因为当前 CTA 仍是“检查简历风险/开始压力测试”，页面渲染全部 bullets 和压力测试卡片。
- [ ] **Step 3: Write minimal implementation**
  - 从可见 MISSION_TABS 移除 proof；保留旧 `/proof` 直链兼容。
  - `renderResume()` 将 target 卡片改为“AI 优化简历”：每条显示原文、建议、修改原因、岗位关注点和真实性确认提示；最多 4 条；隐藏 evidence_refs、grounding_status、原始 ID。
  - 删除主页面压力测试 section；已确认简历显示最终简历预览、导出 PDF、进入模拟面试按钮。
  - `advanceResume()` 在 TargetResume 确认后直接进入 interview；不再调用 red-team。
  - 将 source/selection/strategy 文案改成普通求职者可理解的简短文案。
- [ ] **Step 4: Run test and type-check**
  - Run: `npm --prefix apps/web test -- --test-name-pattern="简历优化|核心链路"` and `npm --prefix apps/web run type-check`
  - Expected: PASS。

### Task 3: 让 InterviewPack 不再依赖压力测试

**Files:**
- Modify: `apps/api/app/mission_service.py`
- Modify: `apps/api/app/mission_provider.py`
- Test: `apps/api/tests/test_mission_service.py` or nearest existing mission service test

- [ ] **Step 1: Write the failing test**
  - 使用无 RedTeamReport 但有已确认 TargetResume 的 mission，调用 `generate_interview_pack`，断言能生成/回退出 topics，且 provider payload 含 JD、TargetResume、company intel。
- [ ] **Step 2: Run test to verify it fails**
  - Run: `python -m pytest apps/api/tests -q -k interview_pack_core_flow`
  - Expected: FAIL，当前服务要求 report 且返回“请先完成压力测试”。
- [ ] **Step 3: Write minimal implementation**
  - 移除 report 必须存在和 high-risk 阻断；无 report 时传空 RedTeamPayload，并由现有 fallback 依据 target resume bullets 生成问题。
  - 更新 target resume prompt：明确只输出 3–4 个高价值建议、保留输入简历 section_order、所有新增事实标记 NEEDS_CONFIRMATION，不得虚构数字/公司/工具/结果。
  - 在 service 中为 `section_order` 缺省值写入教育→经历→项目→技能→证书的保守顺序。
- [ ] **Step 4: Run API tests**
  - Run: `python -m pytest apps/api/tests -q`
  - Expected: PASS。

### Task 4: 简化面试页和面试记录入口

**Files:**
- Modify: `apps/web/app/mission-page.tsx`
- Modify: `apps/web/app/mission-state.ts`
- Add: `apps/web/app/missions/[missionId]/memory/page.tsx` only if route alias is needed; otherwise reuse outcome route
- Test: `apps/web/tests/core-flow.test.mts`

- [ ] **Step 1: Write the failing test**
  - 断言面试页核心 CTA 不再包含“压力测试/补强/证据”，面试记录标签使用“面试记录”。
- [ ] **Step 2: Run test to verify it fails**
  - Run: `npm --prefix apps/web test -- --test-name-pattern="面试页核心文案"`
  - Expected: FAIL，因为当前面试页状态说明和 CTA 仍暴露旧流程。
- [ ] **Step 3: Write minimal implementation**
  - 面试页仅显示“面试问题/我的回答/本题评价/参考回答/下一题”；准备包详情只显示问题和准备提示，不展示来源类型、置信度、Provider 等字段。
  - 保留现有 interview session engine；结束后跳转“面试记录”并复用现有 outcomes API。
  - outcome 页重命名为“面试记录”，隐藏“进入后续通用面试情报”复选框，保留公司/岗位/轮次/问题/卡点/反馈/备注。
- [ ] **Step 4: Run tests and type-check**
  - Run: `npm --prefix apps/web test` and `npm --prefix apps/web run type-check`
  - Expected: PASS。

### Task 5: 真实回归与交付报告

**Files:**
- Add: `docs/_audit/core-flow-e2e-20260925.md`
- Modify: `docs/superpowers/plans/2026-09-25-core-flow-simplification.md`

- [ ] **Step 1:** 强制刷新 `/missions`、`/resume`、`/interview`、`/outcome`，确认主导航无补强入口、简历页无压力测试、优化建议最多 4 条、导出顺序正确。
- [ ] **Step 2:** 用真实 JD 与 `G:\myself\个人简历2.pdf` 或 `G:\myself\潘佳琪-简历.pdf` 跑一遍；记录 API/页面证据。
- [ ] **Step 3:** 跑 `npm --prefix apps/web run type-check`、`npm --prefix apps/web test`、`python -m pytest apps/api/tests -q`。
- [ ] **Step 4:** 写 Before/After flow、改动 routes/files、数据链路、Prompt 结构、E2E 结果和未完成项。
