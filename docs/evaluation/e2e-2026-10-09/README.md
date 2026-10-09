# E2E evidence — 2026-10-09 (phase 2)

API-level mission happy-path against local ioscareer-combine services.
Interactive browser clicks left to parent computerUse.

## Services

- API: http://127.0.0.1:8000 (this worktree .venv uvicorn, DB .runtime/combine-e2e.db)
- Web: http://127.0.0.1:3000 (pps/web next dev)

## Artifacts

- step-log.json — machine-readable step table
- mission-create.json / mission-get.json / identity-patch.json — redacted mission fields
- empty-jd.json — 422 validation probe
- 
esume-gate.json — 409 missing-resume gate
- web-missions-meta.json — HTTP 200 shell for /missions

## Mission under test

- Profile / mission IDs in step-log.json
- Label: synthetic Acme Labs E2E EVAL — do not treat as production seed
- No protected missions deleted

## Browser E2E

See `BROWSER.md` and `browser/` screenshots from Playwright on the laptop loopback.
