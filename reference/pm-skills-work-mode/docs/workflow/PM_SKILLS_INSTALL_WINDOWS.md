# PM Skills — Codex Setup on Windows

Project directory:

```powershell
cd G:\myself\ai-career-OS
```

## Recommended: native Codex plugin marketplace

```powershell
codex plugin marketplace add phuryn/pm-skills

codex plugin add pm-execution@pm-skills
codex plugin add pm-ai-shipping@pm-skills
codex plugin add pm-product-discovery@pm-skills
codex plugin add pm-product-strategy@pm-skills
```

Optional later:

```powershell
codex plugin add pm-market-research@pm-skills
```

## Important

Do **not** clone the whole `pm-skills` repository inside `AI-Career-OS/`.
That would pollute the application repository.

If you want the source locally for reading, clone it as a sibling:

```powershell
cd G:\myself
git clone https://github.com/phuryn/pm-skills.git
```

Then keep the product repo at:

```text
G:\myself\ai-career-OS
```

and the reference repo at:

```text
G:\myself\pm-skills
```

## How to ask Codex to use skills

Codex may not expose Claude-style slash commands. Ask in plain language, for example:

```text
Use the pm-execution strategy-red-team skill to review the frozen Career OS PRD.
Do not add features. Identify only load-bearing assumptions, cheapest tests,
and any contradiction with the current MVP scope.
```

or:

```text
Use the pm-ai-shipping intended-vs-implemented skill to compare TASK-001
intent against the changed code. Cite the relevant docs and code paths.
```
