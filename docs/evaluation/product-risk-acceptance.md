# Product risk acceptance tasks — EVAL phase 2

Date: 2026-10-09 (PT / Guadalcanal UTC+11).  
Branch: `feature/eval-benchmark-v1`. Worktree: `aioscareer-combine`.  
These are **product** acceptance items (not eval scaffolding). Status = open until verified fixed.

Prior evidence sources: `docs/qa/combine/2026-10-08-integration-qa.md`, `docs/evaluation/implementation-audit.md` §7, lane reports on `interview_pack_intel` / `mission_provider` citation keys.

---

## RISK-ACC-001 — Reference-answer fact gate

| Field | Value |
|---|---|
| **ID** | RISK-ACC-001 |
| **Priority** | P0 |
| **Summary** | Block or warn when interview/rewrite reference answers invent candidate actions/metrics not in confirmed Studio facts (class: 「分析50篇内容」→「访问50位创作者」). |
| **Repro** | 1) Use a mission with confirmed Studio bullet containing only 「分析50篇内容」 (or synthetic fixture). 2) Generate interview pack / reference answer / rewrite that expands to interviews/creators. 3) Observe reference text claims unconfirmed actions. |
| **Expected** | Product fails closed: no invented agent/action/metric; or explicit 「证据不足/推断」 label that is not presented as candidate fact. |
| **Observed** | Integration QA 2026-10-08: AI reference answer expanded 50篇→50位创作者; confirmed PDF did **not** contain the invented interviews. The provider now applies a fail-closed reference-answer gate and `test_interview_provider.py` covers the invented action/number case. A fresh live model re-run is still pending. |
| **Acceptance criteria** | (a) Automated test: given confirmed facts F and model draft D with invented metric, gate rejects or strips invention. (b) Dogfood: same Acme/Studio mission cannot surface invented creators as candidate fact. (c) Eval suite flags still fail closed when product leaks invention. |
| **Owner lane hint** | CareerOS-面试包说明 + 简历优化 (reference answer / Studio facts). |
| **Cheap check pointer** | Offline: `evals/benchmark` rewrite/interview fixtures with intentional fact-error. Product unit: `apps/api/tests/test_interview_provider.py::test_interview_provider_gates_reference_answer_invented_actions_and_numbers`. |

---

## RISK-ACC-002 — Unify Studio vs archive preview source of truth

| Field | Value |
|---|---|
| **ID** | RISK-ACC-002 |
| **Priority** | P0 |
| **Summary** | Archive/master checklist must not contradict Studio delivery revision (false 「缺联系方式」 when Studio already has contacts). |
| **Repro** | 1) Mission with Studio revision that includes email/phone. 2) Open archive/master preview / final checklist that still reads source archive. 3) See missing-contact warning while Studio delivery is complete. |
| **Expected** | Single source-of-truth flag in UI + API: delivery preview reads Studio revision; archive checklist labeled as source-archive only, not as delivery blocker. |
| **Observed** | Integration QA 2026-10-08 inference: directional preview warned missing contacts from source archive while Studio revision had contacts. The directional preview now labels this as a source-archive content check and disables contact warnings; Studio remains the delivery source of truth. API-level source/studio provenance is still not unified. |
| **Acceptance criteria** | (a) API field or explicit `preview_source: studio|archive` on delivery endpoints. (b) UI never blocks export solely on archive contact gaps when Studio revision has contacts. (c) Regression test on profile contacts + Studio revision pair. |
| **Owner lane hint** | CareerOS-投递导出 + CareerOS-PDF识别 (contact fields) + Resume Studio. |
| **Cheap check pointer** | `apps/api/tests/test_profile_contacts.py`, `test_resume_studio_*`; `apps/web/scripts/export-resume-checks.test.mts` covers the opt-out used by the source preview. **Partial**. |

---

## RISK-ACC-003 — Interview intel citation keys (no demo as 真实面经)

| Field | Value |
|---|---|
| **ID** | RISK-ACC-003 |
| **Priority** | P0 |
| **Summary** | Enrichment must honor `skill_id` / `source_refs`; strip CURATED header lines from 「要点」; never present demo/generic packs as target-company 真实面经. |
| **Repro** | 1) Generate interview pack for Baidu (or FakeCo fixture) with curated pack present. 2) Inspect topic annotations / citations. 3) Legacy path only reading `id/source/ref` yields 0 refs; first body line shows 「…（CURATED，非合成演示）」 as tip. |
| **Expected** | `item_refs` prefers skill_id/source_refs; `clean_intel_hint` drops header; demo/synthetic excluded; honest 「暂无该公司真实面经」 when only cross-company. |
| **Observed** | `mission_provider._enrich_interview_topics` now calls `annotate_topics` after enrichment. The integration regression test confirms demo questions are excluded, and the focused intel suite passes. A full live company-pack re-run remains pending. |
| **Acceptance criteria** | (a) Pack generation integration test with curated Baidu/FakeCo pack shows non-zero real refs and no CURATED header tip. (b) Demo/generic never labeled 真实面经 for target company. (c) Frontend shows pack title not raw skill id. |
| **Owner lane hint** | CareerOS-面试包说明 (wire mission_provider); CareerOS-JD分析页 (optional company field on intel records). |
| **Cheap check pointer** | `apps/api/tests/test_interview_pack_intel.py` (module and provider integration tests pass). |

---

## RISK-ACC-004 — Experience `decision` ↔ Chinese `why` consistency

| Field | Value |
|---|---|
| **ID** | RISK-ACC-004 |
| **Priority** | P1 |
| **Summary** | `OMIT` must not render 「建议保留」 copy (`_align_experience_why`). |
| **Repro** | 1) Experience selection returns decision=OMIT with why containing 建议保留. 2) UI shows contradictory guidance. |
| **Expected** | Aligner rewrites OMIT → 「暂不放入」 (or equivalent); KEEP paths may keep 建议保留; never OMIT+建议保留. |
| **Observed** | Aligner regression coverage remains green, and the new heuristic gates prevent service-role over-highlighting and recover a high-signal project omitted by a model response. Fresh resume and Studio route captures show the decision flow is reachable; a complete identity-edited browser run is still pending. |
| **Acceptance criteria** | (a) `test_experience_omit_why.py` green on this worktree. (b) API experience-selection payload never returns OMIT with 建议保留 after align. (c) UI renders decision chip consistent with why. |
| **Owner lane hint** | 简历优化 / mission_provider selection path. |
| **Cheap check pointer** | `python -m pytest tests/test_mission_provider.py tests/test_experience_omit_why.py -q` from the API worktree environment. |

---

## RISK-ACC-005 — Pin live EVAL-JD call chain + identity-edit propagation

| Field | Value |
|---|---|
| **ID** | RISK-ACC-005 |
| **Priority** | P1 |
| **Summary** | Document and test whether missions path uses only `MissionProvider.parse_jd` vs `jd_analysis_provider`; identity PATCH must flow into selection/rewrite. |
| **Repro** | 1) Create mission via `POST /api/v1/profiles/{id}/job-missions`. 2) `PATCH .../identity` with corrected company/role/seniority. 3) Re-run experience selection / target resume; confirm corrected identity used (not raw first-parse). |
| **Expected** | Single documented call chain for EVAL-JD (line-level). Identity edits visible in subsequent provider inputs and mission read model. |
| **Observed** | Audit: missions create/reanalyze → `MissionProvider.parse_jd` (`mission_provider.py`); separate `OpenAIJDAnalysisProvider` exists — call-site pin **需要扩大**. Soft extraction fallbacks in `mission_service` when provider unavailable. |
| **Acceptance criteria** | (a) Short call-graph note in eval audit or this file with file:line. (b) Integration test: identity patch then selection sees new company/role. (c) Live EVAL-JD runner imports the pinned function only. |
| **Owner lane hint** | CareerOS-JD分析页 + eval harness owner. |
| **Cheap check pointer** | `test_integrated_mission_api.py`, `test_jd_analysis_provider.py`, `test_mission_provider.py`. Grep create_mission → parse_jd. **Open** until line-level pin committed. |

---

## Status rollup

| ID | Fixed? | Notes |
|---|---|---|
| RISK-ACC-001 | Partial | Fail-closed provider gate + regression test; live model re-run pending |
| RISK-ACC-002 | Partial | Source preview no longer emits contact warnings; API Studio/archive provenance still separate |
| RISK-ACC-003 | Partial | Provider wire + integration test pass; live company-pack re-run pending |
| RISK-ACC-004 | Partial | Aligner and heuristic regression tests pass; full identity-edit browser path pending |
| RISK-ACC-005 | No | Needs call-graph pin + identity propagation test |

## Phase 3 verification — 2026-10-10

- Focused API regression: **30 passed, 1 pre-existing failure** (`test_mission_provider_classifies_structured_output_failures` still accepts a minimal object because normalization supplies defaults).
- Full API suite: **623 passed, 5 skipped, 3 pre-existing failures** (`test_claim_provider_normalizes_partial_claim_schema`, the same mission-provider schema-validation expectation, and `test_claim_analysis_fingerprint_requires_regeneration_after_profile_change`).
- Web export-check regression: **pass** (`export-resume-checks.test.mts`).
- API compile and `git diff --check`: **pass**.
- Fresh browser route evidence: **6/6 routes HTTP 200**, captured in `docs/evaluation/e2e-2026-10-10/` and linked from the README Project Tour.
