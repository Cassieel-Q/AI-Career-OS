# PM Skills Adoption Review

## What we actually need

**Use now**
- pm-execution
- pm-ai-shipping

**Install but use selectively**
- pm-product-discovery
- pm-product-strategy

**Later / optional**
- pm-market-research

## What changed in our repo

- PRD structure improved; 14 P0 scope unchanged.
- Assumptions now separated from requirements.
- P0 converted into testable user stories.
- Codex receives project-level operating instructions through `AGENTS.md`.
- Material code tasks now get an Intended-vs-Implemented review before merge.
- Old duplicate technical docs moved to archive.

## What we deliberately did not copy

We did not vendor all upstream `SKILL.md` files into this repository.
Codex supports installing the marketplace/plugins directly, so copying all skills would create maintenance noise and duplicate upstream source.

## Next action

Before TASK-001:
1. install the selected Codex plugins;
2. let Codex read `AGENTS.md`;
3. keep TASK-001 scope unchanged;
4. after TASK-001 finishes, run the Intended-vs-Implemented review.
