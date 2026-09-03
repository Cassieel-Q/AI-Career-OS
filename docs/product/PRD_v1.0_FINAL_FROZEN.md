# AI Career OS — PRD v1.0 FINAL FROZEN

**Status**：FINAL / PRODUCT GATE PASSED  
**Freeze Date**：2026-09-02

## Target User

正在探索或准备进入 AI / 大模型相关职业，但对岗位选择、能力差距和行动路径缺乏清晰判断的学生与职场人士。

第一版聚焦 6 类方向：AI 产品、AI 应用开发、AI 解决方案、大模型算法、AI 数据、AI 运营。

## Primary User Outcome

> 用户明确知道“我接下来具体应该做什么，以及为什么”。

## Frozen P0 — 14 Capabilities

1. Resume Upload & Parse
2. Profile Confirm & Supplement
3. Basic Career Preferences
4. Basic Role Exploration
5. Target Role Selection
6. Multi-JD Input
7. JD Parse + Normalize + Aggregate
8. Basic Evidence Trace
9. Gap Analysis
10. Gap Prioritization
11. User Override
12. 4-Week Roadmap + Daily Tasks
13. Progress + Manual Replanning
14. Dashboard

## Frozen Critical Path

```text
Resume → Draft Profile → Confirm + Skill Self-assessment → Preferences → Role Exploration → Target Role → 3–10 JDs → Parse/Normalize/Aggregate → Market Profile → Gap → NOW/NEXT/NOT NOW → User Override → 4-Week Roadmap → Daily Tasks → Progress → Manual Replan → Dashboard
```

## Key Rules

- Resume Parser 只提取显式事实，不自动判断“熟练”。
- 关键技能由用户轻量自评：了解 / 基础使用 / 能独立完成小项目 / 熟练应用。
- 首次 Role Exploration 使用 Built-in Role Profiles，并标注“探索性建议”。
- 导入真实 JD 后，岗位显性要求以 JD 为主要 Source of Truth。
- JD 最少 3 个，推荐 5–10 个，上限 10 个。
- Gap 分六类，并区分 ACTIONABLE / STRUCTURAL。
- Gap Priority 综合岗位重要度、当前差距、补齐成本、求职期限；成本只用 LOW/MEDIUM/HIGH。
- 用户可 Override AI 的 Gap 顺序。
- Roadmap 采用“长期粗略 + 最近 4 周详细”。
- Task Completion 只更新 Progress，不等于 Skill Mastery。
- Dashboard 是主入口，Chat 不是主入口。

## Acceptance Criteria（摘要）

- PDF 简历可生成带 Evidence 的 Draft Profile。
- Profile 未确认不得进入岗位推荐。
- 至少输出 2 个探索性岗位方向。
- 3 个以上同类 JD 可形成 Market Profile。
- JD Pipeline 输出标准化技能、频率、source_jd_ids、样本数。
- Gap 输出 category/type/current_state/target_state/rationale/evidence。
- Priority 输出 NOW（最多 3）/ NEXT / NOT NOW。
- 用户修改 Priority 后可以重生成计划。
- Roadmap 输出长期阶段、4 周计划、本周目标和 Daily Tasks。
- Daily Task 至少有 title/objective/estimated_minutes/completion_criteria/linked_gap_id。
- Dashboard 无需聊天即可看到 Target Role、Top Gaps、This Week、Today、Progress、Evidence Summary。

## Out of Scope

自动招聘抓取、自动社区抓取、自动投递、面试模拟、简历润色、课程平台、完整资源推荐、Skill Verification、AI 成果验收、历史 Plan UI、精确成功率、复杂 Multi-Agent、微服务、本地 LLM。
