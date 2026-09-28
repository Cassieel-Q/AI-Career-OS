# PM Skills Work Mode — AI Career OS

## Why adopt it

The upstream PM Skills repository is useful because it turns generic AI prompting into explicit PM workflows: PRD structure, assumption testing, user stories, test scenarios, red-teaming, and AI-built-code shipping review.

We will **not** use all skills. The goal is rigor without slowing the project down.

## Selected plugins

### 1. `pm-execution` — install now
Use for:
- `create-prd`
- `strategy-red-team`
- `user-stories`
- `wwas`
- `pre-mortem`
- `test-scenarios`
- later sprint/retro

This is the most important plugin for the current project.

### 2. `pm-ai-shipping` — install now
Use for:
- `intended-vs-implemented`
- `shipping-artifacts`
- derive tests
- pre-ship security/performance review

This is especially relevant because Codex is writing code and we need a durable record of intent vs actual implementation.

### 3. `pm-product-discovery` — install, use selectively
Useful if new evidence challenges the frozen product direction:
- assumptions
- experiments
- customer interviews
- opportunity mapping

Do not reopen discovery on every implementation decision.

### 4. `pm-product-strategy` — install, low-frequency use
Useful for:
- value proposition
- product strategy
- positioning / differentiation

Our strategy is mostly defined, so this is a reference plugin rather than a daily workflow.

### Optional later: `pm-market-research`
Useful when we need structured competitive analysis or user research. It is not required for TASK-001.

## Stage-based workflow

```text
New product/major scope change
→ create-prd
→ strategy-red-team
→ assumption test
→ approval / scope freeze

Feature implementation
→ user story / WWA
→ test scenarios
→ bounded Codex task
→ code + tests
→ intended-vs-implemented review

Pre-release
→ shipping artifacts
→ derive tests
→ static security/performance review
→ ship decision
```

## Speed rule

Do not run a full PM workflow for routine engineering details.

Use PM skills only when:
- the decision changes user value or scope
- the assumption can kill the product direction
- the feature needs acceptance criteria
- implementation must be checked against intent
- the app is approaching release
