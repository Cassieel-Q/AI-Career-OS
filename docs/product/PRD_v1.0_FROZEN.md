# AI Career OS — PRD v1.0 FROZEN

**Document Type:** Product Requirements Document  
**Version:** v1.0  
**Status:** FROZEN  
**Freeze Date:** 2026-09-02  
**Owner:** Project Owner  
**Rule:** 除 Blocker、核心假设被证伪或明确批准的 Change Request 外，不新增 MVP Scope。

---

## 1. Product Goal

AI Career OS 面向正在探索或准备进入 AI / 大模型相关职业，但对岗位选择、能力差距和行动路径缺乏清晰判断的学生与职场人士。

核心目标不是“生成职业建议”，而是：

> 基于用户真实背景、目标岗位证据和当前进度，持续告诉用户此刻最值得做什么，以及为什么。

---

## 2. Primary User Outcome

用户完成首次主流程后，应明确获得：

1. 一个明确的目标岗位方向；
2. 自己与该目标之间的关键能力差距；
3. 当前最值得优先解决的 Top 3 Gap；
4. 一份最近 4 周 Roadmap；
5. 今天具体应该完成的任务。

---

## 3. MVP Critical Path

```text
Resume Upload
→ Resume Parse
→ Profile Confirm
→ Career Preferences
→ Role Exploration
→ Target Role Selection
→ Import 3–10 JDs
→ JD Parse / Normalize / Aggregate
→ Evidence Trace
→ Gap Analysis
→ Gap Prioritization
→ User Override
→ 4-Week Roadmap
→ Daily Tasks
→ Progress
→ Manual Replanning
→ Dashboard
```

---

## 4. Frozen P0 Capabilities

### P0-01 Resume Upload & Parse
用户上传 PDF 简历，系统提取教育、技能、项目/经历等结构化信息。

### P0-02 Profile Confirm & Supplement
AI 提取结果先进入 Draft Profile；用户必须确认或修改，并补充编码偏好、时间约束等信息。

### P0-03 Basic Career Preferences
用户选择最看重的职业因素，例如尽快就业、长期发展、薪资、编码偏好、当前匹配度。

### P0-04 Basic Role Exploration
系统基于用户画像与偏好推荐 2–3 个 AI 相关岗位方向，并解释主要推荐原因和主要挑战。

### P0-05 Target Role Selection
用户选择一个目标岗位方向进入后续分析。

### P0-06 Multi-JD Input
用户手动粘贴 3–10 个同类真实 JD。

### P0-07 JD Parse + Normalize + Aggregate
系统解析多个 JD，统一同义技能并形成基于该样本的岗位能力画像。

### P0-08 Basic Evidence Trace
核心 Gap 和推荐应能追溯到用户画像或具体 JD 证据。

### P0-09 Gap Analysis
从技术、产品/业务、项目、实习/工作、学历/专业、英语六类识别差距，并区分 Actionable Gap 与 Structural Constraint。

### P0-10 Gap Prioritization
综合岗位重要度、当前差距、补齐成本、求职期限等因素，输出 NOW / NEXT / NOT NOW；NOW 默认只突出 Top 3。

### P0-11 User Override
用户可调整 Gap 优先级；系统提示影响但不阻止，并基于新顺序重新规划。

### P0-12 4-Week Roadmap + Daily Tasks
系统生成粗粒度长期路线、最近 4 周详细计划、Weekly Goal 和 Daily Tasks。

### P0-13 Progress + Manual Replanning
用户自行勾选任务完成；可手动触发“生成明天计划”和“重新规划”。

### P0-14 Dashboard
Dashboard 展示 Target Role、Top 3 Gaps、本周 Milestone、Today Tasks、Roadmap 进度和 Evidence 概况。

---

## 5. Out of Scope

MVP 明确不做：

- 自动抓取招聘网站；
- 自动抓取小红书/知乎/牛客；
- 自动投递；
- AI 模拟面试；
- 简历润色；
- 在线课程；
- 社区；
- MBTI/性格决定岗位；
- 伪精确成功率/匹配率；
- 复杂 Multi-Agent；
- 微服务；
- 本地大模型部署；
- 完整双岗位比较；
- AI 成果验收；
- 历史 Career Plan 管理。

---

## 6. Acceptance Criteria

### AC-01 Resume
**Given** 用户上传可读取 PDF  
**When** 解析成功  
**Then** 至少得到 education、skills、experience 三类结构化字段。

### AC-02 Profile Confirmation
未被用户确认的 Draft Profile 不得用于正式岗位推荐。

### AC-03 Role Exploration
Confirmed Profile 完成后，系统至少给出 2 个候选 AI 岗位方向，并为每个方向提供推荐原因和主要挑战。

### AC-04 Multi-JD
用户至少输入 3 个同类 JD 后，系统可以形成岗位样本分析。

### AC-05 JD Aggregation
系统必须输出：
- 样本 JD 数量；
- 高频能力；
- 低频特殊要求；
- 标准化后的技能名称。

### AC-06 Evidence Trace
Top Gap 至少关联一条可见 Evidence；岗位要求类 Evidence 应指向具体 JD。

### AC-07 Gap Analysis
系统能够输出六类 Gap，并区分 Actionable Gap / Structural Constraint。

### AC-08 Gap Priority
系统输出 NOW / NEXT / NOT NOW，且 NOW 默认不超过 3 个核心 Gap。

### AC-09 Override
用户改变 Gap 顺序后，保存新优先级，并能基于新优先级重新生成计划。

### AC-10 Roadmap
系统输出：
- 粗粒度长期阶段；
- 最近 4 周计划；
- 当前周目标；
- 当日任务。

### AC-11 Daily Task
每个任务至少包含 title、estimated_minutes、completion_criteria。

### AC-12 Progress
用户可将任务标记为 completed / incomplete。

### AC-13 Manual Replanning
系统可根据当前 Progress、未完成任务、剩余时间和 Gap Priority 手动重新生成后续任务。

### AC-14 Dashboard
用户进入主页面后，无需聊天即可看到目标岗位、Top Gaps、本周目标和今天任务。

---

## 7. Product Principles

1. Evidence Before Advice
2. User in Control
3. Preference Before Static Skill
4. Constraint-Aware
5. Explainable Recommendations
6. No Fake Precision
7. Do Not Replan Excessively

---

## 8. Scope Change Rule

冻结后出现新想法时：

1. 不直接加入 PRD；
2. 先写入 `BACKLOG.md`；
3. 若认为必须进入 MVP，提交 Change Request；
4. 必须说明：为什么不做会导致 Critical Path 失败；
5. 经 Project Owner 明确批准后才能修改本文件。
