# Annotation guidelines — AI Career OS evaluation

Version: 2026-10-09. Scope: human gold labels for EVAL-JD / MATCH / REWRITE / INTERVIEW.  
These rules define how raters label; they do **not** invent completed ratings.

## Global rules

1. Every label cites **source evidence** (JD span, resume fact id, or interview pack id). Speculation is tagged `inferred`, never written as raw fact.
2. Prefer **two independent raters**. If resources allow only one, mark `single_rater` and still keep a 20% overlap sample when a second rater becomes available; report actual overlap %, Cohen's κ or score MAE.
3. Keep `initial` / `disputed` / `adjudicated` versions. Adjudication notes are mandatory on disputes.
4. Never paste personal phone/email/address into git-tracked annotation files. Use redacted resume ids.
5. Synthetic fixtures may be labeled by engineers for harness tests; they are **not** human product grades.

## 1. JD annotation (EVAL-JD)

Record per `jd_id`:

| Field | Guidance |
|---|---|
| company / role_title / location / years / education | Exact string from JD when present; else `UNKNOWN` + evidence note |
| responsibilities | Atomic clauses; each keeps original span |
| must_have / preferred / non_technical | Separate lists |
| requirement_labels | Each requirement → `required` / `preferred` / `inferred` |

**Do not** promote inferred seniority or tools into `required`.  
Identity corrections made by the user in product UI are the mission identity for downstream tasks; annotate both raw parse and post-correction identity when evaluating the correction loop.

## 2. Experience selection (EVAL-MATCH)

Use the **product enums only**:

| Code | Chinese UI meaning |
|---|---|
| `KEEP_AND_HIGHLIGHT` | 重点展示 |
| `KEEP` | 保留 |
| `DEEMPHASIZE` | 弱化 |
| `OMIT` | 暂不放入 |

Per experience id (`resume-003-exp-004` style):

- `decision`
- `jd_requirement_refs` (ids/spans)
- `resume_evidence_refs`
- `rationale` (Chinese or English; must mention concrete facts)
- `priority` (high/medium/low)
- `rater_id`

**CRITICAL_SELECTION_ERROR**: a high-priority / must-keep project labeled `OMIT`. Track separately from ordinary mismatches.

Cross-JD check: the same resume against the **pre-fixed 3 representative JDs** must not collapse to identical rankings without rationale. Sorting changes must not break id alignment.

## 3. Rewrite review (EVAL-REWRITE)

Unit = **experience/project suggestion**, not each final PDF bullet.

Score 1–5 each:

1. Factuality (事实真实性)
2. JD fit (岗位匹配)
3. Completeness of important info (重要信息完整性)
4. Clarity (清晰度)
5. Adoptability (可直接采纳程度)

Also record:

- fabricated numbers / duties / tools (boolean + span)
- material fact change (boolean)
- important experience omission (boolean)
- human edit count + timed edit duration
- bullet_count after Studio split
- adoption state: `accepted` / `edited` / `rejected` (product state ≠ fact confirmation)

**Ordering rule**: judge facts first. Critical unconfirmed facts ⇒ cannot mark adoptability 5 / “直接可采纳”.  
`UNSUPPORTED` / `NEEDS_CONFIRMATION` items and unfinished portfolio suggestions must not be graded as final-PDF ready.

LLM-as-judge columns are auxiliary only.

## 4. Interview annotation (EVAL-INTERVIEW)

Per question:

- JD grounding evidence
- Confirmed-resume grounding evidence
- Interview pack id / source (`skill_id`, never display raw id in UI copy checks)
- duplicate_of question id (if any)
- scoring rubric notes
- reference-answer fact errors (standalone fail if invents candidate facts)

**Hard rules**

- Other-company intel cannot be presented as target-company真实面经.
- `SYNTHETIC_DEMO_ONLY` / `generic-*` packs are not real company intel.
- Follow-ups must be judged with full turn context; first-question relevance ≠ follow-up quality.
- Use **synthetic answers of varying quality** to probe adaptivity; never label them as real users.

## 5. Rater consistency

| Situation | Required reporting |
|---|---|
| Dual raters | Overlap ≥ 20% of units; κ for categorical; MAE/ICC for 1–5 scores |
| Single rater only | `single_rater=true`; no fabricated agreement stats |
| Adjudication | Keep both initials + final; note rule cited |

## 6. Status vocabulary for runs

| Status | Meaning |
|---|---|
| `PASSED` / `FAILED` | Compared against gold or deterministic offline actual |
| `NOT_RUN` | Missing model output, keys, or corpus |
| `UNRATED` | Output exists; human score missing |
| `NOT_EVALUABLE` | Metric denominator zero / undefined |
