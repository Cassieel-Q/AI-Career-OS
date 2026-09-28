# Resume Optimization and Mock Interview Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Resume Optimization 收拢为“原始简历 → AI 优化版本 → 逐条确认”，并确保 Mock Interview 读取最终确认版简历、连续回答不丢状态。

**Architecture:** 保留现有数据库和 API 结构。后端把经历排序、highlight/avoid 和逐条改写放在一次 Resume Optimization 生成上下文中；前端将选择、策略、目标简历合并成双栏展示，策略只作为每条改写的后台字段。面试沿用现有 session/turn/debrief 记录，修复按钮状态与刷新链路。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Next.js/React, TypeScript, Node test runner, pytest.

## Global Constraints

- 不新增产品概念，不重新设计数据库。
- 原始简历是左栏 source of truth，保留原有 section 顺序。
- highlight/avoid 留在后台推理；用户界面每条只显示原文、AI 改写、短理由、接受/编辑/拒绝。
- 真实事实与用户确认状态分开；模型新增事实必须可确认后才进入正式简历。
- 无项目/实习/科研时只能生成“建议补做项目”，不能当作已完成经历。
- 面试只读取最终确认简历与 JD/面经/技能上下文。

---

### Task 1: Reproduce and lock backend ranking/rewrite behavior

**Files:**
- Modify: `apps/api/app/mission_provider.py`
- Modify: `apps/api/app/mission_service.py`
- Test: `apps/api/tests/test_mission_provider.py`
- Test: `apps/api/tests/test_integrated_mission_api.py`

- [ ] Add failing tests that assert a Baidu physical-AI JD ranks the wind-energy competition/research projects above 心理委员 and that strategy guidance contains non-empty Chinese highlight/avoid fields.
- [ ] Add a failing test that a real project rewrite includes concrete original facts and a concise one-sentence reason.
- [ ] Make the provider prompt send complete JD + complete source resume + decision fields in one optimization operation.
- [ ] Make fallback ranking use concrete relevance and only use generic fallback when the source lacks fields.
- [ ] Ensure `what_to_highlight` and `what_to_avoid` are persisted and attached to each rewrite context.
- [ ] Ensure source-less entries are “建议补做项目” and never become completed resume experience.
- [ ] Run targeted pytest.

### Task 2: Build a source/AI optimization dual-column resume view

**Files:**
- Modify: `apps/web/app/mission-page.tsx`
- Modify: `apps/web/app/mission-state.ts`
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/app/missions.ts`
- Test: `apps/web/tests/mission-state.test.mts`
- Test: `apps/web/tests/core-flow.test.mts`

- [ ] Add failing UI-state tests for a combined optimization view and for unrelated campus work showing “AI 建议：暂不放入”.
- [ ] Render the bound source profile in original section order on the left.
- [ ] Render AI rewritten bullets and short why-changed text on the right.
- [ ] Hide standalone strategy page from the ordinary resume path while retaining its API state.
- [ ] Display one compact “AI 优化方向” line; do not show Evidence/Claim/Capability/RAG fields.
- [ ] Add non-overlapping layout for fact-confirmation warnings in normal document flow.
- [ ] Keep accept/edit/reject actions per bullet and preserve user overrides.
- [ ] Run web tests and type-check.

### Task 3: Separate acceptance from fact confirmation

**Files:**
- Modify: `apps/api/app/mission_schemas.py`
- Modify: `apps/api/app/mission_service.py`
- Modify: `apps/web/app/mission-page.tsx`
- Modify: `apps/web/app/missions.ts`
- Test: `apps/api/tests/test_integrated_mission_api.py`
- Test: `apps/web/tests/mission-flow.test.mts`

- [ ] Add failing tests that a bullet can be accepted while still requiring fact confirmation, and cannot enter final export until fact confirmation is complete.
- [ ] Persist acceptance and fact status using existing fields/JSON risk metadata without a database redesign.
- [ ] Render warnings below the rewritten bullet instead of overlaying content.
- [ ] Add explicit “确认事实” action for NEEDS_CONFIRMATION bullets.
- [ ] Run targeted API/web tests.

### Task 4: Fix Mock Interview state transitions and final-resume context

**Files:**
- Modify: `apps/web/app/proof-steps.tsx`
- Modify: `apps/web/app/proof-route.tsx`
- Modify: `apps/web/app/proof-shell.tsx`
- Modify: `apps/web/app/proof-flow.ts`
- Modify: `apps/api/app/proof_service.py`
- Modify: `apps/api/app/interview_provider.py`
- Test: `apps/api/tests/test_interview_sessions.py`
- Test: `apps/web/tests/proof-flow.test.mts`
- Test: `apps/web/tests/proof-state.test.mts`

- [ ] Add failing tests for QUESTION_READY → ANSWERING → SUBMITTING → EVALUATED → NEXT_QUESTION/COMPLETED and retry after API failure.
- [ ] Ensure continue/next always gives visible busy/error feedback and never leaves a disabled no-op state.
- [ ] Refresh the returned session after submit and use the returned next question directly.
- [ ] Pass final confirmed resume bullets, not just the original claim, into interview context.
- [ ] Run targeted interview tests.

### Task 5: Real-case E2E and verification report

**Files:**
- Modify: `docs/superpowers/qa/2026-09-26-dogfood-fixes-verification.md`
- Create: `docs/superpowers/qa/2026-09-26-resume-interview-retest.md`

- [ ] Run the real Baidu JD/profile case and record AI ranking for wind-energy project, 心理委员, and 体育部副部长.
- [ ] Record original vs rewritten wind-energy bullets and the exact prompt structure.
- [ ] Run five consecutive interview turns and record API/session/UI state transitions.
- [ ] Run full web tests/type-check, targeted/full API tests, and `git diff --check`.
- [ ] Record DeepSeek provider status and remaining legacy test failures without declaring PO PASS.

