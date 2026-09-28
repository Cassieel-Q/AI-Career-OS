# AI Career OS — PRD v1.0 FINAL FROZEN

**Status**：FINAL / PRODUCT GATE PASSED  
**Scope Status**：FROZEN — PM Skills review changed documentation structure, not MVP scope  
**Owner**：Project Owner

## 1. Summary

AI Career OS helps students and working professionals exploring AI / LLM careers decide what to do next. It converts a confirmed user profile and evidence from real job descriptions into prioritized career gaps, a four-week roadmap, and daily tasks.

The product is not a generic career chatbot. Its core loop is:

```text
User State + Market Evidence
→ Gap
→ Priority
→ Plan
→ Progress
→ Replan
```

## 2. Contacts

| Role | Responsibility |
|---|---|
| Project Owner | Product decisions, scope approval, acceptance |
| ChatGPT | Product mentor, technical lead, reviewer |
| Codex | Bounded implementation tasks, tests, Git reporting |

## 3. Background

### Problem

Users preparing for AI-related roles are surrounded by fragmented and conflicting information from job descriptions, community posts, courses, interview notes, and generic AI advice.

The core problem is not lack of information. It is lack of a reliable decision process:

- Which AI role should I explore?
- What does the target role actually require?
- What do I personally lack?
- What should I do now?
- What can I safely ignore for now?

### Why now

LLMs make personalized analysis and planning inexpensive enough to embed into a persistent product workflow, but one-shot chat still lacks structured state, evidence traceability, stable prioritization, and progress-aware replanning.

## 4. Objective

### Primary User Outcome

> 用户明确知道“我接下来具体应该做什么，以及为什么”。

### MVP success criteria

For the portfolio MVP, success means:

1. A user can complete the Happy Path from resume upload to daily tasks.
2. Core Gap conclusions can show their supporting User/JD Evidence.
3. The system produces a maximum of three NOW gaps rather than an unprioritized skill dump.
4. User Override changes the plan without destroying the system's original recommendation.
5. The same user state can be re-evaluated after progress or goal changes.
6. AI outputs used as system state pass schema validation.

These are product-quality criteria, not claims about employment success.

## 5. Market Segments

The MVP focuses on people exploring or preparing for AI / LLM-related careers:

- undergraduate / graduate students
- cross-major students
- working professionals changing direction
- learners already studying AI but unsure whether their learning matches hiring demand

Initial role domain:

1. AI Product Manager
2. AI Application Engineer
3. AI Solution Consultant / Engineer
4. LLM Algorithm Engineer
5. AI Data / Data Analysis
6. AI Operations / AI Product Operations

The market is defined by the shared job-to-be-done — making an evidence-backed career decision — rather than by age or demographic identity.

## 6. Value Proposition

### User job

When AI career information is fragmented and contradictory, users want to understand which gaps matter most so they can spend limited time on the actions most likely to move them toward a target role.

### What AI Career OS provides

- structured User Profile rather than chat memory
- multi-JD Market Profile rather than one-JD interpretation
- traceable Evidence rather than unsupported advice
- NOW / NEXT / NOT NOW prioritization rather than a giant learning list
- a four-week execution plan rather than a static career report
- progress-aware replanning rather than a one-shot answer

## 7. Solution

### 7.1 UX flow

```text
Resume
→ Draft Profile
→ Confirm + Skill Self-assessment
→ Career Preferences
→ Role Exploration
→ Target Role
→ 3–10 JDs
→ Market Profile
→ Gap Analysis
→ NOW / NEXT / NOT NOW
→ User Override
→ 4-Week Roadmap
→ Daily Tasks
→ Progress
→ Manual Replan
→ Dashboard
```

Dashboard is the primary interface. Chat is not the primary interface.

### 7.2 Frozen P0 — 14 Capabilities

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

### 7.3 Key rules

- Resume Parser extracts explicit facts; it does not infer skill mastery.
- Key skill levels require lightweight user confirmation.
- Initial Role Exploration uses Built-in Role Profiles and is labeled exploratory.
- After real JDs are provided, JD evidence is the main Source of Truth for explicit job requirements.
- JD sample: minimum 3, recommended 5–10, MVP maximum 10.
- Gaps are categorized and separated into ACTIONABLE vs STRUCTURAL.
- Gap effort uses LOW / MEDIUM / HIGH, not fake precise hours.
- Users may override AI priority; the system preserves both system and user priority.
- Roadmap = coarse long-term stages + detailed next four weeks.
- Task completion updates Progress; it does not automatically imply Skill Mastery.
- Learning-resource search is not an MVP responsibility.

### 7.4 Key assumptions

The MVP depends on several unproven beliefs. They are tracked in:

`docs/product/ASSUMPTIONS_AND_VALIDATION.md`

Important examples:
- users value prioritized next actions more than another information summary
- multi-JD aggregation creates enough extra value to justify manual JD input
- users will tolerate pasting at least 3 JDs in the MVP
- Evidence Trace increases trust and decision usefulness
- a plan can be actionable before full learning-resource recommendation exists

## 8. Release

### MVP

Frozen P0 capabilities only.

### Out of Scope

- automatic job-site scraping
- automatic community-platform scraping
- auto application
- interview simulation
- resume rewriting
- course platform
- full learning-resource search
- Skill Verification
- AI proof-of-mastery
- historical plan UI
- precise success probability
- complex Multi-Agent architecture
- microservices
- local LLM

### Release principle

Ship the Critical Path first, then add deeper Evidence RAG and quality improvements only after the structured core works.

## Acceptance Criteria — Core Summary

- Text-based PDF resume produces a Draft Profile with source evidence.
- Unconfirmed Profile cannot enter formal role recommendation.
- Role Exploration returns at least 2 exploratory directions.
- 3+ same-role JDs can form a Market Profile.
- JD aggregation exposes normalized skills, frequency, source JD IDs, and sample count.
- Gap output includes category/type/current/target/rationale/evidence.
- Priority produces NOW (max 3), NEXT, NOT NOW.
- User Override can replan without deleting the system recommendation.
- Roadmap includes long-term stages, four detailed weeks, current weekly target, and Daily Tasks.
- Daily Task includes title/objective/estimated_minutes/completion_criteria/linked_gap_id.
- Dashboard exposes Target Role, Top Gaps, This Week, Today, Progress, and Evidence without requiring chat.
