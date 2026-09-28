# AI Career OS — Assumptions & Validation

**Purpose:** Track load-bearing assumptions separately from feature scope.

A load-bearing assumption is a belief that could make the product direction fail if false. This document follows a lightweight red-team approach: make each assumption falsifiable, define the cheapest evidence to get, and state when we would change course.

| Rank | Claim | Fails if | Evidence to get | Kill / change criterion | Cheapest test |
|---|---|---|---|---|---|
| 1 | Users primarily need prioritized next actions, not more career content | Users value reports/resources but do not act on plans | 5–8 target-user walkthroughs | Most users cannot name a decision/action the product improved | Prototype test: compare generic analysis vs NOW + 4-week plan |
| 2 | Multi-JD aggregation creates meaningful value beyond single-JD ChatGPT analysis | Users see no material difference in trust or usefulness | Compare 1-JD vs 5-JD outputs with target users | Multi-JD output does not improve perceived confidence/actionability | Use the same profile with one JD and five JDs |
| 3 | Manual input of 3–10 JDs is acceptable in MVP | Users abandon before Market Profile because input friction is too high | Observe onboarding completion | Repeated abandonment at JD step or strong refusal to paste 3 JDs | Test with 3-JD minimum before building auto acquisition |
| 4 | Evidence Trace improves trust and makes recommendations easier to challenge | Users ignore citations and still treat outputs as generic AI advice | Show Gap with/without expandable evidence | Evidence does not improve understanding/trust in user tests | Add evidence drawer to one Gap prototype |
| 5 | A four-week plan is actionable without integrated learning-resource search | Users know what to do but still cannot start because resources are missing | Ask users to execute 2–3 sample tasks | Most tasks require the product to find resources before users can act | Give a week plan without resource links and observe blockers |
| 6 | Built-in Role Profiles are sufficient for early exploration before real JDs | Early role recommendations feel arbitrary or misleading | Test with 3–5 profiles | Users cannot understand why roles were suggested or suggestions conflict strongly with later JD evidence | Compare exploratory role result with later JD-backed result |

## Validation rule

Do not add a P0 feature merely because an assumption feels risky.

First:
1. get the cheapest evidence;
2. update belief;
3. only submit a Change Request if the Critical Path genuinely fails.
