# Browser E2E — 2026-10-09

Interactive Chromium (Playwright) run on the **user Windows laptop** against local services from worktree `aioscareer-combine`.

- Web: http://127.0.0.1:3000
- API: http://127.0.0.1:8000
- Branch: `feature/eval-benchmark-v1`
- Runner: `browser/run-e2e.cjs` (Playwright headless Chromium)
- Fresh UI mission: `e3ebf3f0-2ea2-4e46-979f-969950d3a46e` (synthetic Acme / Baidu-style AI PM JD — not a real job)
- Prior API mission `bb71e19d-…` left untouched

## Results

| Step | Status | Evidence |
|------|--------|----------|
| Open `/missions` | PASS | `browser/01-missions-home.png` |
| Click 新建岗位 → `/missions/new` | PASS | `browser/02-missions-new.png` |
| Empty/short JD → Chinese gate | PASS | `browser/03a-empty-jd-disabled.png`, `browser/03b-short-jd-chinese-error.png` (CTA disabled when empty; short text → 「请粘贴完整一些的岗位描述。」) |
| Paste JD → role understood page | PASS | `browser/04a-jd-pasted.png`, `browser/04b-after-identify.png` (~24s identify) |
| Resume source UI (已有简历 / 上传 PDF / 粘贴文本) | PASS | `browser/05-resume-source-ui.png` |
| Missing resume action gate | PASS | `browser/05b-missing-resume-gate.png` (primary CTA disabled until mode selected) |
| Studio / interview entry visibility | PASS* | `browser/06-overview-nav.png` — 模拟面试 visible; Studio **not** visible yet (`ui_studio_vs_archive_preview` = NOT_RUN) |
| Composite interactive flow | PASS | replaces prior `ui_interactive_missions_flow` NOT_RUN |
| Interview pack browser | PASS | entry visible; pack generation not exercised (resume not bound) |
| Full PDF upload / Studio vs archive deep compare | NOT_RUN | no PDF fixture; Studio chrome absent pre-resume |

* Visibility only — interview pack generation and Studio archive-preview parity were not fully exercised.

## Screenshots

- `01-missions-home.png` (62239 bytes)
- `02-missions-new.png` (40421 bytes)
- `03a-empty-jd-disabled.png` (40421 bytes)
- `03b-short-jd-chinese-error.png` (43133 bytes)
- `04a-jd-pasted.png` (116086 bytes)
- `04b-after-identify.png` (177729 bytes)
- `05-resume-source-ui.png` (77491 bytes)
- `05b-missing-resume-gate.png` (77664 bytes)
- `06-overview-nav.png` (177729 bytes)

## How to re-run

```powershell
Set-Location G:\myself\ai-career\.worktrees\aioscareer-combine\apps\web
node ..\..\docs\evaluation\e2e-2026-10-09\browser\run-e2e.cjs
```

Requires :3000 and :8000 healthy. Uses synthetic JD only. Playwright resolves from `apps/web` via `createRequire`.

## Blockers / limits

- Studio entry not shown before resume bind — `ui_studio_vs_archive_preview` remains NOT_RUN (stage gating, not a crash).
- Did not upload a real PDF or complete Master-resume bind (allowed to stop at source UI).
- Playwright added as local `apps/web` devDependency on this eval branch; not pushed to GitHub.
