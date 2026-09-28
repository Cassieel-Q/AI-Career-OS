# AI Career OS — MVP User Stories

These stories translate the Frozen P0 capabilities into user-centered, testable slices. They use the 3C idea: Card (short story), Conversation (intent/context), Confirmation (acceptance).

## US-01 — Create a trustworthy profile

**Card:** As a career explorer, I want the system to extract my resume into a draft profile so that I do not have to re-enter my background manually.

**Conversation:** AI extraction is a draft, not truth. The user must be able to verify important facts and skill levels.

**Confirmation:**
- text-based PDF is accepted
- education / skills / experiences / certifications are structured
- source evidence is retained
- no skill mastery is inferred
- invalid/no-text PDF produces a clear error

## US-02 — Confirm my career state

**Card:** As a user, I want to correct my profile and add preferences so that recommendations are based on facts I approve.

**Confirmation:**
- Draft cannot become formal recommendation input before confirmation
- key skill level is user-confirmed
- time and career preferences are saved

## US-03 — Explore a few plausible AI directions

**Card:** As an undecided user, I want 2–3 explainable role directions so that I can choose what to investigate further.

**Confirmation:**
- recommendations use Confirmed Profile + Built-in Role Profiles
- output is clearly marked exploratory
- each direction includes why it may fit and its main challenge

## US-04 — Build a market profile from real JDs

**Card:** As a user with a target direction, I want the system to aggregate several real JDs so that I can see recurring requirements rather than overreacting to one posting.

**Confirmation:**
- minimum 3 JDs
- raw JD text preserved
- skills normalized
- frequency and source JD IDs exposed
- conclusions state the sample size

## US-05 — See evidence-backed gaps

**Card:** As a user, I want to see the difference between my profile and target requirements so that I understand what actually blocks me.

**Confirmation:**
- gaps include current state, target state, rationale, evidence
- ACTIONABLE vs STRUCTURAL separated
- evidence can trace to user/JD source

## US-06 — Know what matters now

**Card:** As a user with many gaps, I want only the most important gaps prioritized so that I stop trying to learn everything at once.

**Confirmation:**
- NOW contains at most 3
- NEXT and NOT NOW exist
- system priority remains available after User Override
- no fake precision shown to the user

## US-07 — Get an executable four-week plan

**Card:** As a user, I want my top gaps converted into weekly goals and daily tasks so that I can start acting immediately.

**Confirmation:**
- long-term stages are coarse
- next 4 weeks are detailed
- every task links to a Gap
- task has estimated time and completion criteria

## US-08 — Update the plan when reality changes

**Card:** As a user, I want the system to respond to progress and changed constraints so that an old plan does not become stale.

**Confirmation:**
- task completion updates progress
- ordinary misses adjust near-term tasks
- major user-triggered changes may replan larger scope
- completion does not automatically equal skill mastery
