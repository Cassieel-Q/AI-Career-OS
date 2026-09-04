# AI Career OS — 面试作品集版 PRD

**文档类型：** 面试 / 作品集展示版 PRD  
**版本：** v1.0  
**日期：** 2026-09-03  
**状态：** Portfolio Presentation Version  
**重要说明：** 本文档仅用于作品集与面试展示，不替代工程开发使用的冻结版 PRD。工程实现仍以 `PRD_v1.0_FINAL_FROZEN.md` 为唯一 Source of Truth。

---

# 1. 产品概述

AI Career OS 是一款面向 AI / 大模型相关职业探索与求职准备人群的 **Evidence-driven Career Planning System（证据驱动型职业规划系统）**。

它解决的不是“用户缺少职业信息”这个问题，而是：

> **用户拥有大量信息，却无法判断什么值得相信、自己真正缺什么，以及下一步到底应该做什么。**

AI Career OS 将用户确认后的个人能力状态、多个真实岗位 JD 与可追溯 Evidence 结合起来，逐步回答三个问题：

1. 我更值得探索哪些 AI 岗位方向？
2. 我距离目标岗位真正差什么？
3. 我接下来最应该做什么？

产品最核心的用户结果是：

> **“我终于知道接下来具体应该做什么，而且知道为什么要先做这些。”**

核心产品闭环：

```text
用户状态 + 市场证据
→ Gap
→ Priority
→ Action Plan
→ Progress
→ Replan
```

---

# 2. 项目角色

| 角色 | 职责 |
|---|---|
| Product Owner | 产品方向、用户价值、Scope 与最终决策 |
| AI Product Mentor / Tech Lead | 产品推演、技术架构、质量评审 |
| Codex | 在明确 Task、Acceptance Criteria 与边界下完成工程实现 |

该项目采用 **Task-driven Development**：

> Product Owner 控制问题、范围和决策，Codex 负责在限定边界内实现。

---

# 3. 背景与问题定义

## 3.1 问题背景

准备 AI 相关岗位的人通常并不缺信息。

他们可以轻易接触到：

- 招聘网站 JD；
- 小红书经验帖；
- 知乎回答；
- 牛客面经；
- 在线课程；
- AI 助手；
- 学长学姐或同行建议。

但这些信息往往：

- 高度碎片化；
- 相互矛盾；
- 缺乏上下文；
- 很难长期维护；
- 难以转化成个人决策。

例如，同一个准备 AI 产品经理的用户可能同时看到：

- “AI PM 不需要写代码”；
- “现在不会 Python 根本进不了 AI 产品岗”；
- 某 JD 强调 RAG；
- 另一份 JD 更看重产品设计；
- 某课程建议学习模型训练；
- ChatGPT 又给出几十项学习清单。

用户获取了更多信息，却没有获得更多确定性。

---

## 3.2 核心用户问题

更深层的问题并不是：

> “我应该学什么？”

而是：

> **“对于我的目标，到底什么最重要？我应该相信什么？我现在先做什么？”**

主要痛点包括：

### 方向不确定
“我到底应该做 AI 产品经理、AI 应用开发，还是其他岗位？”

### 岗位要求不确定
“一个岗位真正稳定、重复出现的要求是什么？”

### 自我差距不确定
“哪些是我的关键 Gap，哪些只是 Nice-to-have？”

### 优先级过载
“Python、SQL、RAG、Agent、产品能力、项目……好像什么都要学。”

### 计划难执行
“我有一份 Roadmap，但今天到底应该做什么？”

### 计划快速失效
“可用时间变了、目标变了、任务没完成，原来的计划却没有更新。”

---

## 3.3 当前替代方案

### 方案一：直接使用 ChatGPT

**优势**
- 快；
- 灵活；
- 交互成本低。

**不足**
- 主要依赖对话上下文；
- 用户状态不够结构化；
- Evidence 容易丢失；
- 不同 Prompt 下优先级可能变化；
- 很难长期追踪 Progress；
- 多数规划是一次性的。

---

### 方案二：招聘网站

**优势**
- 能看到真实岗位需求。

**不足**
- 主要帮助“找工作”，不是“理解岗位”；
- 用户需要自己跨多个 JD 总结；
- 不会自动和用户当前能力进行 Gap Mapping。

---

### 方案三：小红书 / 知乎 / 牛客等社区

**优势**
- 有真实经验；
- 有面试细节；
- 有很多隐性岗位知识。

**不足**
- 信息碎片化；
- 经常互相冲突；
- 可能混有广告和引流；
- 收藏之后难以再次利用；
- 单篇帖子很容易造成认知偏差。

---

### 方案四：Notion / Excel / 手工整理

**优势**
- 用户可控；
- 可以长期保存。

**不足**
- 人工成本高；
- 无法自动进行语义 Gap 分析；
- 无法动态排序；
- 不具备 Evidence-driven Replanning。

---

## 3.4 为什么现在适合做

LLM 已经让以下能力变得可行：

- 从 Resume 中抽取结构化信息；
- 理解不同表达方式的 JD；
- 识别语义相近的能力要求；
- 辅助 Gap Reasoning；
- 自动生成个性化计划。

但单纯调用 LLM 仍然不等于一个稳定产品。

真正需要补齐的是：

- Persistent State；
- Evidence Trace；
- Structured Output；
- Deterministic Rules；
- User Override；
- Progress Tracking；
- Replanning。

因此，本项目的机会并不是：

> “再做一个 AI 聊天机器人。”

而是：

> **把 LLM 的推理能力变成一个可持续使用的职业决策系统。**

---

# 4. 产品目标

## 4.1 Product Objective

帮助用户基于真实证据做出更清晰的 AI 职业决策，并将决策转化为可以立即执行的行动计划。

---

## 4.2 Primary User Outcome

> **“我终于知道接下来具体应该做什么。”**

这个 Outcome 被刻意设计成“行动结果”，而不是“获得一份报告”。

---

## 4.3 Supporting Outcomes

为了达到 Primary Outcome，用户应该逐步获得：

1. 对候选岗位方向的基本判断；
2. 对目标岗位真实要求的理解；
3. 对个人能力 Gap 的判断；
4. 对 NOW / NEXT / NOT NOW 的优先级判断；
5. 对每个重要建议背后 Evidence 的理解。

---

## 4.4 MVP 成功标准

作品集版本至少需要完整展示：

- 从 Resume 到 Daily Task 的完整 Happy Path；
- Multi-JD Aggregation；
- Evidence-backed Gap Analysis；
- NOW 不超过 3 项；
- 用户可以 Override AI Priority；
- 未来四周详细 Roadmap；
- Progress 与 Replan；
- LLM Structured Output + Validation；
- Dashboard-first 的长期状态展示。

这些指标用于验证产品行为，而不是承诺求职成功率。

---

## 4.5 产品指标设计

### Activation

- Profile Confirmation 完成率；
- 添加至少 3 个 JD 的比例；
- 到达第一份 Gap Priority 结果的比例。

### Decision Usefulness

- “产品是否帮助我明确下一步行动”；
- 用户是否可以解释自己的 #1 Gap 为什么排第一。

### Plan Actionability

- 用户是否开始至少一个 Daily Task；
- Task Completed / Skipped 比例；
- 用户是否使用过 Replan。

### Trust

- Gap Evidence 展开率；
- 用户对“我知道这个建议为什么出现”的主观评分。

---

# 5. 目标用户与市场范围

## 5.1 Primary Segment

正在探索或准备进入 AI / 大模型相关岗位，但已经拥有大量信息、却缺乏明确职业决策框架的人群。

典型用户包括：

- 本科生；
- 研究生；
- 跨专业学生；
- 准备转入 AI 领域的职场人士；
- 已经开始学习 AI，但不确定学习内容是否匹配招聘需求的人。

---

## 5.2 初始岗位范围

MVP 首先覆盖六类岗位：

1. AI 产品经理
2. AI 应用开发工程师
3. AI 解决方案顾问 / 工程师
4. 大模型算法工程师
5. 数据分析 / AI 数据方向
6. AI 运营 / AI 产品运营

不一开始覆盖所有职业，是为了：

- 降低 Skill Normalization 难度；
- 提高 Gap Mapping 准确性；
- 让 Role Profile 更可控；
- 在有限范围内验证核心价值。

---

# 6. Value Proposition

## 6.1 Job To Be Done

> 当我准备进入 AI 行业，而不同渠道告诉我的东西互相冲突时，我希望知道哪些能力真的对我的目标岗位重要，从而把有限时间花在最值得做的事情上。

---

## 6.2 用户获得的价值

### Clarity
知道真正重要的是什么。

### Focus
不再试图“什么都学”。

### Traceability
知道系统为什么给出这个建议。

### Control
可以挑战和调整 AI 的优先级。

### Momentum
分析之后直接进入可执行任务。

### Adaptability
现实变化以后，计划也会变化。

---

## 6.3 核心差异化

| 普通 AI 职业对话 | AI Career OS |
|---|---|
| Chat History | Structured User Profile |
| 单次 Prompt / 单 JD | Multi-JD Market Profile |
| Free-form Advice | Structured Gap |
| 黑盒式理由 | Evidence Trace |
| 一长串技能清单 | NOW / NEXT / NOT NOW |
| AI 自由排序 | Rules Ranking + AI Explanation |
| Static Plan | Progress + Replan |
| Chat-first | Dashboard-first |

真正的差异化不是：

> “我们也用了 LLM。”

而是：

> **我们把 AI 推理变成了一个持续、可追溯、可调整的决策系统。**

---

# 7. 产品方案

## 7.1 Core User Journey

```text
Resume Upload
→ Draft Profile
→ User Confirmation
→ Career Preferences
→ Role Exploration
→ Target Role
→ Add 3–10 JDs
→ Market Profile
→ Gap Analysis
→ NOW / NEXT / NOT NOW
→ User Override
→ 4-Week Roadmap
→ Daily Tasks
→ Progress
→ Replan
→ Dashboard
```

---

## 7.2 Core Product Loop

```text
STATE
我现在是什么状态？

+
EVIDENCE
目标岗位到底需要什么？

↓
DECISION
我现在最重要的 Gap 是什么？

↓
ACTION
我接下来具体做什么？

↓
FEEDBACK
我做了什么 / 跳过了什么 / 条件发生了什么变化？

↓
REPLAN
计划接下来应该怎么变？
```

这个闭环比任何单个 Feature 更重要。

---

# 8. 核心功能设计

## F1. Resume Upload & Draft Profile

用户上传文本型 PDF Resume。

系统抽取：

- Education
- Skills
- Experiences
- Certifications

重要设计原则：

> **Resume Parser 只抽取事实，不推断 Skill Mastery。**

如果 Resume 里出现 Python，只能确认“出现过 Python Evidence”，不能直接认定用户“熟练 Python”。

---

## F2. Profile Confirmation

AI 的 Resume Extraction 只形成 Draft。

用户必须确认或修正后才能形成 Confirmed Profile。

关键技能采用轻量级自评：

- AWARE — 了解
- BASIC — 基础使用
- PROJECT_READY — 可以独立完成小项目
- PROFICIENT — 熟练应用

这一设计避免 AI 把“出现过”误认为“掌握了”。

---

## F3. Career Preferences

用户选择最重要的两个职业偏好维度，例如：

- 薪酬；
- Coding 偏好；
- 快速就业；
- 当前能力匹配；
- 长期发展。

偏好会影响 Recommendation，但不会掩盖现实 Preparation Cost。

---

## F4. Role Exploration

在没有真实 JD 时，系统使用 Built-in Role Profiles 推荐 2–3 个候选方向。

这一步明确标记为：

> Exploratory Recommendation

而不是：

> “AI 判断你最适合某岗位。”

---

## F5. Target Role Selection

用户选择目标岗位。

如果 AI 发现明显 mismatch，可以：

- 提示风险；
- 提供 Alternative；
- 提供 Transition Path；

但不能阻止用户选择。

---

## F6. Multi-JD Input

用户手动提供真实 JD：

- 最少 3 个；
- 推荐 5–10 个；
- MVP 最多 10 个。

产品所有 Market Conclusion 都必须写清楚：

> **“基于你提供的 N 个 JD……”**

而不是虚构成：

> “市场普遍要求……”

---

## F7. JD Parse + Normalize + Aggregate

系统抽取每个 JD 的要求，并进行 Skill Normalization。

例如：

```text
大模型应用开发
LLM Application Development
LLM Apps
→ LLM Application Development
```

系统进一步计算：

- Skill Frequency；
- Importance；
- Source JD；
- Sample Count。

---

## F8. Evidence Trace

系统保留三类 Evidence：

### User Evidence
来自用户 Confirmed Profile。

### Market Evidence
来自真实 JD。

### Community Evidence
来自面经、社区经验等非结构化资料。

Source of Truth 规则：

- 岗位显式要求 → JD；
- 用户自身能力 → Confirmed Profile；
- 社区内容 → Supplementary Evidence。

Community Evidence 不可以单篇覆盖多个 JD。

---

## F9. Gap Analysis

系统对比：

```text
Current User State
VS
Target Market Requirement
```

Gap 分类：

- Technical
- Product & Business
- Project Experience
- Internship / Work
- Education / Major
- English

同时区分：

### ACTIONABLE
可以通过未来行动明显改善。

### STRUCTURAL
短期无法通过普通学习任务解决。

例如：

> “某岗位要求 3 年正式工作经验”

不应该生成：

> “今天学习 60 分钟工作经验”。

---

## F10. Gap Prioritization

系统不提供几十项平铺 Gap。

而是：

### NOW
最多 3 项。

### NEXT
之后处理。

### NOT NOW
当前阶段暂时不投入时间。

内部 Ranking 考虑：

- Role Importance；
- Gap Severity；
- Deadline Urgency；
- Effort。

核心 Ranking 使用 Deterministic Rules。

LLM 主要解释：

> “为什么它排在这里？”

---

## F11. User Override

AI 不拥有最终决定权。

系统同时保留：

```text
system_priority
user_priority
```

用户可以主动调整：

> “我知道 RAG 很重要，但这两周我想先补 Python。”

系统可以提醒风险，但不能 Block。

---

## F12. Four-Week Roadmap

长周期职业目标保持粗粒度。

只有未来四周进入详细规划。

结构：

```text
Career Goal
→ Long-term Stage
→ 4-Week Roadmap
→ Weekly Goal
→ Milestone
→ Daily Task
```

Daily Task 通常：

- 30–90 分钟；
- 对应明确 Gap；
- 有 estimated time；
- 有 completion criteria。

MVP 重点是：

> 告诉用户学什么、做什么、做到什么程度。

而不是一开始成为课程推荐平台。

---

## F13. Progress & Replanning

Task 状态：

- TODO
- COMPLETED
- SKIPPED

一个关键原则：

> **Task Completion ≠ Skill Mastery**

完成：

> “学习 RAG 60 分钟”

并不能自动证明：

> “用户已经掌握 RAG”。

普通任务偏差只调整近期计划。

用户目标、时间或优先级发生重大变化时，再触发更大范围 Replan。

---

## F14. Dashboard

产品采用 Dashboard-first，而不是 Chat-first。

Dashboard 显示：

- Target Role；
- NOW Top 3 Gaps；
- This Week；
- Today Tasks；
- Roadmap Progress；
- Evidence Summary。

用户打开产品后应该立即知道：

> “我现在在哪里，我今天应该做什么。”

而不是每次重新和 AI 聊一遍。

---

# 9. AI / 技术设计

系统采用 Modular Monolith：

```text
Browser
→ Next.js
→ FastAPI
   ├─ PostgreSQL
   ├─ OpenAI
   └─ pgvector
```

---

## 9.1 LLM 负责什么

LLM 适合：

- Resume Semantic Extraction；
- JD Semantic Extraction；
- Gap Reasoning；
- Explanation；
- Roadmap Generation；
- Replanning。

---

## 9.2 Deterministic Code 负责什么

代码规则负责：

- Schema Validation；
- State Transition；
- Frequency Count；
- Priority Ranking；
- Task Status；
- Permission；
- Persistence。

设计原则：

> **语言理解交给 LLM，确定性业务规则交给代码。**

---

## 9.3 AI Reliability

关键 AI 输出采用：

```text
Evidence
→ Structured Output
→ Pydantic Validation
→ Business Rules
→ Database
```

模型的自由文本不能直接成为系统状态。

---

## 9.4 RAG Boundary

Structured Facts：

```text
Profile
Task
Gap Priority
JD Frequency
```

保存在 PostgreSQL。

非结构化 Evidence：

```text
Community Notes
Interview Experience
Long JD Chunks
```

可以进入：

```text
Chunk
→ Embedding
→ pgvector
→ Retrieval
→ Grounded Answer
```

RAG 是 Evidence Retrieval 工具，不替代普通数据库。

---

# 10. 核心假设与验证计划

## Assumption A

### Claim
用户最需要的是 Prioritized Action，而不是另一份职业信息报告。

### Fails if
用户看完分析以后仍然不知道下一步做什么。

### Cheapest Test
比较：

- Generic Career Report
- NOW + 4-week Plan

看用户是否更容易做出行动决策。

---

## Assumption B

### Claim
Multi-JD Aggregation 比单 JD 分析提供明显额外价值。

### Fails if
用户认为一份 JD 和五份 JD 的结果差异不大。

### Cheapest Test
同一 Profile：

```text
1 JD Analysis
VS
5 JD Analysis
```

比较用户对结果的信任和 Actionability。

---

## Assumption C

### Claim
用户愿意在 MVP 中手动粘贴至少 3 个 JD。

### Fails if
用户频繁在 JD Input 阶段退出。

### Cheapest Test
在开发自动抓取前，先真实观察用户是否愿意提供三个 JD。

---

## Assumption D

### Claim
Evidence Trace 能增加信任。

### Fails if
用户完全忽略 Evidence，并认为结果仍是普通 AI Advice。

### Cheapest Test
同一 Gap：

```text
Without Evidence
VS
Expandable Evidence
```

观察理解度和信任变化。

---

## Assumption E

### Claim
在没有完整 Resource Recommendation 的情况下，Roadmap 仍然可以执行。

### Fails if
用户知道任务是什么，却因为找不到资料而无法开始。

### Cheapest Test
提供两三个无资源链接的 Daily Tasks，观察用户是否能独立执行。

---

# 11. MVP Scope

MVP 包含冻结的 14 个 P0：

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

---

# 12. Out of Scope

首版明确不做：

- 自动招聘网站抓取；
- 自动小红书抓取；
- 自动投递；
- Interview Simulation；
- Resume Polishing；
- 在线课程平台；
- Comprehensive Resource Discovery；
- Skill Verification；
- 精确求职成功率；
- Historical Career Plan UI；
- Complex Multi-Agent；
- Microservices；
- Local LLM。

Scope 的目的不是限制想象力，而是保护 Critical Path。

---

# 13. Release Strategy

## Stage 1 — Foundation

- Git / GitHub
- Next.js
- FastAPI
- Tests
- Environment

---

## Stage 2 — First Vertical Slice

```text
PDF Resume
→ Text Extraction
→ LLM Structured Output
→ Validation
→ Draft Profile
→ Frontend Display
```

目标：

> 用最小业务功能验证 Frontend + Backend + LLM + Validation 的整条数据链。

---

## Stage 3 — Structured Career Core

- Profile Confirmation
- Role Exploration
- Multi-JD
- Gap
- Priority
- Roadmap

---

## Stage 4 — Evidence Layer

- Evidence Trace
- Document
- Chunk
- Embedding
- pgvector
- Grounded Retrieval

---

## Stage 5 — Feedback Loop

- Progress
- Replan
- Dashboard

---

## Stage 6 — Quality & Portfolio

- Golden Set
- AI Eval
- Regression
- Deployment
- Demo
- Architecture Diagram
- Resume Bullet
- Mock Interview

---

# 14. 关键产品决策与 Trade-offs

## 为什么 MVP 手工输入 JD，而不是自动抓取？

自动抓取意味着：

- Anti-bot；
- 网站结构变化；
- 合规与维护；
- 更多工程复杂度。

在核心价值还未验证时，这些投入没有必要。

所以先验证：

> Multi-JD Synthesis 本身是否有价值。

---

## 为什么 Dashboard-first？

因为 AI Career OS 的核心是：

> Persistent Career State

用户应该直接看到：

- 目标；
- Gap；
- Progress；
- Today Task。

而不是每次重新组织 Prompt。

---

## 为什么 Rules + LLM？

LLM 适合：

> 理解语义、判断上下文、生成解释。

Rules 适合：

> 稳定排序、状态控制、测试、Debug。

因此使用 Hybrid System：

```text
LLM Reasoning
→ Rule Ranking
→ LLM Explanation
```

---

## 为什么 Workflow First，而不是 Agent First？

MVP 的主路径已经很明确：

```text
Profile
→ JD
→ Gap
→ Priority
→ Roadmap
```

这里并不需要 AI 自主决定：

> “下一步应该调用什么 Tool？”

所以 Agent 会增加复杂度，却没有产生足够额外价值。

---

## 为什么 Task Completion 不等于 Skill Mastery？

因为：

> Activity ≠ Capability

完成一个任务只能证明：

> 用户完成了某个行动。

不能证明：

> 用户已经具备独立应用该 Skill 的能力。

因此 Skill Verification 被放到后续版本。

---

# 15. 核心产品原则

整个产品最终可以浓缩成三个原则：

## Evidence Before Advice
先有证据，再给建议。

## Priority Before Completeness
先告诉用户最重要的，不追求把所有知识都塞给用户。

## Action Before More Content
最终目标不是输出更多内容，而是让用户开始行动。

---

# 16. 面试一句话介绍

> 我设计了一套 Evidence-driven Career OS，它不是普通的 AI 职业聊天机器人，而是把用户确认后的能力状态与多个真实 JD 建立结构化映射，生成可追溯的 Gap 和优先级，再把 Top Gap 转化成未来四周可以执行的行动计划，并随着用户 Progress 动态 Replan。

---

# 17. Portfolio Story

这个产品最初来自一个很简单的观察：

> **我们并不缺信息，我们缺的是从信息走向决策。**

用户可能收藏了几十篇经验帖、看过很多 JD、问过 ChatGPT、报名过课程，但真正困难的仍然是：

> “这些东西跟我到底有什么关系？”

因此我没有把产品定义成“职业内容推荐器”，而是重新把问题定义为：

> **Career Decision Support**

这也进一步决定了产品设计：

- 用 Structured Profile 表示用户真实状态；
- 用 Multi-JD 建立 Market Evidence；
- 用 Evidence Trace 约束 AI 推理；
- 用 NOW / NEXT / NOT NOW 解决 Priority Overload；
- 用 4-week Roadmap 将分析转成 Action；
- 用 Progress + Replan 构成长期闭环。

技术架构同样服务于这个产品逻辑：

- LLM 负责语义；
- Rules 负责稳定业务逻辑；
- Structured Output 负责可靠性；
- PostgreSQL 保存真实状态；
- RAG 只处理需要语义检索的 Evidence。

最终目标不是做一个“回答职业问题的 AI”。

而是做一个：

> **从证据到决策，再从决策到行动的 Career Operating System。**
