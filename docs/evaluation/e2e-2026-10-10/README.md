# E2E evidence — 2026-10-10

This is the browser evidence set captured on 2026-10-10 from the `feature/eval-benchmark-v1` worktree after the 2026-10-09 dogfood fixes. The 2026-10-11 Resume Studio visual alignment pass was verified against the same local route and is represented by the updated Studio screenshot in the tour.

## Services and data

- Web: `http://127.0.0.1:3001` (`apps/web` Next.js dev server)
- API: `http://127.0.0.1:8000` (current worktree API)
- Database: `.runtime/combine-e2e.db` in the worktree; synthetic test profile only
- Profile: `45995c1bdbe84c5991fa9782fff16cde`
- Mission: `48b6772e-17c7-42c4-a18f-a0dda61a1508` (Acme Labs / AI 产品经理实习生)

No private or consented-real resume was copied into the repository. The screenshots contain the existing isolated dogfood fixture and are not evidence of real hiring outcomes.

## Captured routes

| File | Route | Result |
|---|---|---|
| `01-missions.png` | `/missions?profile_id=...` | 200; profile and two missions visible |
| `02-role.png` | `/missions/{mission}/role` | 200; JD identity and focus visible |
| `03-resume-source.png` | `/missions/{mission}/resume` | 200; source/target resume gate visible |
| `04-resume-studio.png` | `/missions/{mission}/resume/studio` | 200; Studio preview, fact status, PDF action visible |
| `05-interview.png` | `/missions/{mission}/interview` | 200; JD-grounded question preview visible |
| `06-interview-records.png` | `/interview-records?profile_id=...` | 200; company-grouped record visible |

Machine-readable route evidence is in `../../screenshots/project-tour-2026-10-10/report.json`. The capture script is `browser/capture-tour.cjs`; it uses Playwright against the running local app and saves full-page PNGs. The Studio screenshot specifically verifies the unified mission-page visual system: green primary actions, warm off-white background, rounded cards, and the same reading width as the surrounding workflow. A video was not captured in this run, so the tour links to these fresh screenshots instead.

## Scope limits

This run verifies route rendering and the persisted dogfood state. It does not claim the 30-JD/10-resume benchmark target, consented-real usability, blind baseline A/B, or a production PostgreSQL migration gate.
