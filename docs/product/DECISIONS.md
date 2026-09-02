# AI Career OS — DECISIONS

**用途：** 记录“为什么这样做”。  
这个文件对项目 owner 和以后面试非常重要。

推荐采用轻量 ADR（Architecture / Product Decision Record）格式。

---

## 写法模板

### DEC-XXX — 决策标题

**Date:** YYYY-MM-DD  
**Status:** ACCEPTED / SUPERSEDED / REJECTED  
**Context:** 当时遇到了什么问题？  
**Decision:** 最终决定是什么？  
**Alternatives:** 还考虑过哪些方案？  
**Why:** 为什么选择当前方案？  
**Trade-offs:** 为此牺牲了什么？  
**Revisit When:** 什么条件出现时需要重新评估？

---

## DEC-001 — MVP 聚焦 AI / 大模型职业，而不是所有职业

**Date:** 2026-09-02  
**Status:** ACCEPTED  
**Context:** 产品目标用户包括学生和转行职场人士，但如果第一版支持所有职业，岗位 Taxonomy、Evidence 和 Eval 会无限膨胀。  
**Decision:** 用户身份可以较宽，但第一版 Domain Boundary 聚焦 AI / 大模型相关岗位。  
**Alternatives:** 所有职业规划；仅 AI 产品经理。  
**Why:** 在“范围过宽”和“目标过窄”之间取得平衡。  
**Trade-offs:** MVP 不能覆盖传统金融、法律、机械等职业。  
**Revisit When:** AI 岗位闭环验证成功并需要扩大用户群。

## DEC-002 — 核心结果选择“接下来具体做什么”

**Status:** ACCEPTED  
**Context:** 岗位选择、Gap、行动计划都重要，但必须确定一个 Primary Outcome。  
**Decision:** Primary User Outcome 为明确下一步行动。  
**Why:** 用户真正卡点不是缺信息，而是不知道如何行动。  
**Trade-offs:** 产品不能只做职业测评或 JD 分析，必须走到 Task 层。

## DEC-003 — Evidence 以 JD 为岗位要求 Source of Truth

**Status:** ACCEPTED  
**Decision:** 判断岗位显性要求时以真实 JD 为主，社区经验为补充。  
**Why:** 社区经验“活人感”强，但个案不能覆盖市场显性要求。  
**Trade-offs:** JD 样本量有限，因此输出必须注明“基于用户提供的 N 个 JD”。

## DEC-004 — Resume-first 且强制确认

**Status:** ACCEPTED  
**Decision:** AI 先解析简历形成 Draft Profile，用户确认后才成为 Confirmed Profile。  
**Why:** 降低 Onboarding Friction，同时防止 Error Propagation。  
**Trade-offs:** 比无确认流程多一步操作。

## DEC-005 — 用户控制权高于 AI 排序

**Status:** ACCEPTED  
**Decision:** 用户可调整 Gap Priority，AI 只做 Soft Guardrail。  
**Why:** 职业规划是决策支持，不是让 AI 替用户决定人生。  
**Trade-offs:** 用户可能做出与 AI 推荐不同的选择，但系统应尊重。

## DEC-006 — 规划采用长期粗略 + 最近四周详细

**Status:** ACCEPTED  
**Decision:** 不一次生成未来半年全部任务。  
**Why:** 降低计划失真和认知负担，便于动态调整。  
**Trade-offs:** 长期计划精度较低。

## DEC-007 — 日微调、周重规划、用户主动触发优先

**Status:** ACCEPTED  
**Decision:** 普通任务偏差只调整近期任务；大 Roadmap 主要在 Weekly Review 或用户主动改变条件时调整。  
**Why:** 防止 AI 过度重规划造成焦虑和不稳定。  
**Trade-offs:** 系统不会每一次进度变化都重新求全局最优。

## DEC-008 — Dashboard-first，不做 Chatbot-first

**Status:** ACCEPTED  
**Decision:** 主体验使用 Dashboard，聊天作为辅助能力。  
**Why:** 避免产品退化成 ChatGPT Wrapper，并强化 State、Gap、Plan、Progress 的产品结构。  
**Trade-offs:** 前端需要设计更多结构化页面。

## DEC-009 — MVP 手动提供 JD

**Status:** ACCEPTED  
**Decision:** 用户手动粘贴 3–10 个 JD；不做招聘网站抓取。  
**Why:** 优先验证 Intelligence，而不是 Data Acquisition。  
**Trade-offs:** 初次使用摩擦更高。

## DEC-010 — 32 个 P0 压缩为 14 个 Capability

**Status:** ACCEPTED  
**Decision:** 按 Critical Path 冻结 14 个 P0 Capability。  
**Why:** 三周周期内需要先跑通、做聪明、再产品化。  
**Trade-offs:** 双岗位比较、不推荐解释、监督模式等延后到 P1。
