# AI Career OS — PRD v1.0 FINAL FROZEN

**Status**：FINAL / PRODUCT GATE PASSED  
**Freeze Date**：2026-09-02  
**Next Stage**：TECH_SPEC_v0.1

## 1. Core Product Definition
面向正在探索或准备进入 AI / 大模型相关职业，但对岗位选择、能力差距和行动路径缺乏清晰判断的学生与职场人士。

> 基于用户真实背景、目标岗位证据和执行进度，持续识别最值得解决的职业差距，并转化为下一步行动。

Primary Outcome：

> 用户明确知道“接下来具体应该做什么，以及为什么”。

## 2. Frozen P0 — 14 Capabilities
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

除正式 Change Request 外，不新增 P0。

## 3. Final Business Rules

### Resume
Parser 只提取事实，不直接判断技能熟练度；保留 evidence text。

### Skill Self-assessment
关键技能由用户确认：
了解 / 基础使用 / 能独立完成小项目 / 熟练应用。

### Role Exploration
首次探索使用内置粗粒度 Role Profile，并明确标注“探索性建议”。

### Market Evidence
真实 JD 导入后，岗位显性要求以 JD 为主要 Source of Truth。

### JD Sample
最少 3 个，推荐 5–10 个，上限 10 个。

### Evidence Trace
Gap 和推荐必须能追溯到 User Evidence 或具体 JD。

### Gap
区分 ACTIONABLE / STRUCTURAL。

### Gap Priority
综合岗位重要度、当前差距、补齐成本、求职期限。成本仅使用 LOW / MEDIUM / HIGH。

### Planning
Roadmap 负责目标、任务、预计时间和完成标准；不负责完整学习资源搜索。

### Progress
Task Completion 不自动等于 Skill Mastery。

### Replanning
用户可手动触发。日常偏差优先调整近期任务，重大目标变化才调整大 Roadmap。

### Dashboard
Dashboard 是主入口，Chat 不是主入口。

## 4. Acceptance Criteria

### AC-01 Resume
Given 用户上传有效 PDF  
When Parser 完成  
Then 输出 Draft Profile，至少包含 education / skills / experience，并保留对应原文证据。

### AC-02 Profile
Given Draft Profile  
When 用户确认字段与关键技能水平  
Then 状态变为 confirmed，之后才能进行岗位推荐。

### AC-03 Role Exploration
Given Confirmed Profile + Career Preferences  
When 进入岗位探索  
Then 基于 Built-in Role Profiles 输出至少 2 个候选岗位、推荐原因和主要挑战，并标记为探索性建议。

### AC-04 Multi-JD
Given 用户已选择 Target Role  
When 提交不少于 3 个同类 JD  
Then 保存原始 JD 并生成 Market Profile。

### AC-05 JD Aggregation
Then 输出标准化技能、出现频率、source_jd_ids、高频要求、低频特殊要求和样本数量。

### AC-06 Gap
Given User Profile + Market Profile  
Then 输出 category / type / current_state / target_state / rationale / evidence。

### AC-07 Priority
Then 输出 NOW（最多 3 个）/ NEXT / NOT NOW，并提供排序依据。

### AC-08 Override
When 用户修改 Gap 顺序  
Then 保存新顺序并允许重新生成 Roadmap。

### AC-09 Roadmap
Then 输出长期粗粒度阶段 + 最近 4 周计划 + 当前周目标 + Daily Tasks。

### AC-10 Daily Task
每个 Task 至少包含 title / objective / estimated_minutes / completion_criteria / linked_gap_id。

### AC-11 Progress
用户可将任务标记 completed / incomplete；不得因此自动将 Skill 标记为 mastered。

### AC-12 Manual Replanning
基于 Progress、Gap Priority、剩余时间和用户反馈生成后续任务调整。

### AC-13 Dashboard
无需聊天即可看到 Target Role / Top 3 Gaps / This Week / Today Tasks / Roadmap Progress / Evidence Summary。

## 5. Out of Scope
自动招聘抓取、自动社区抓取、自动投递、面试模拟、简历润色、课程平台、完整学习资源推荐、Skill Verification、AI 成果验收、历史 Plan UI、精确成功率预测、复杂 Multi-Agent、微服务、本地 LLM。

## 6. Gate Result
**PRODUCT GATE PASSED**

下一份正式文档：`TECH_SPEC_v0.1.md`
