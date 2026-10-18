# 可信求职闭环 v1.2｜测试结果

分支 `feature/trusted-workflow-v12`，HEAD `1ea1c65`（`git status` 仅有 `.workbuddy/memory/*` 两条工作日志改动，无未提交代码）。

## 一、全量回归

| 套件 | 命令 | 通过 | 失败 | 跳过 | 说明 |
|---|---|---|---|---|---|
| 后端 | `apps/api> pytest -q` | **1118** | **7** | 5 | 7 项失败与主分支基线**完全一致** |
| 前端 | `apps/web> npm test` | **276** | 0 | 0 | node:test |
| 前端类型 | `apps/web> tsc --noEmit` | ✅ 无输出 | — | — | 退出码 0 |
| 浏览器 E2E | `docs/evaluation/trusted-workflow-v12/browser/e2e-trusted-workflow.cjs` | **35** | 0 | — | Playwright + Chromium，6 条主流程 |

## 二、基线 vs 本轮（关键：没有新增失败）

基线取 `main` 的 7 项**既有**失败。本轮同样是这 7 项，一项不多、一项不少：

| 文件 | 用例 | 状态 |
|---|---|---|
| `test_claim_provider.py` | `test_claim_provider_normalizes_partial_claim_schema` | 既有失败 |
| `test_gap_analysis.py` | `test_gap_analysis_uses_confirmed_profile_and_allowed_states` | 既有失败 |
| `test_market_profile.py` | `test_market_profile_exposes_grounded_capability_clusters_without_discarding_atomics` | 既有失败 |
| `test_priorities.py` | `test_priority_algorithm_is_stable_and_caps_now` | 既有失败 |
| `test_resume_reliability.py` | `test_repeated_education_merge_preserves_optional_fields_and_courses` | 既有失败 |
| `test_roadmap.py` | `test_four_week_roadmap_is_persisted_with_actionable_tasks` | 既有失败 |
| `test_target_jobs.py` | `test_claim_analysis_fingerprint_requires_regeneration_after_profile_change` | 既有失败 |

判定方法：`git stash push -u` 后在基线重跑对比，再 `git stash pop`。

## 三、专项测试（指令 6.2 要求的四组，全部超额）

| 组 | 要求 | 实到 | 主要文件 |
|---|---|---|---|
| 事实安全 | ≥25 | **94** | `test_fact_trust.py`(25)、`test_fact_safety_reference_answer.py`(27)、`test_fact_edit_reverification.py`(6)、`test_ghost_experience_and_claim_gate.py`(4)、`test_webform_safety.py`(23)、`test_assistant_write_proposals.py`(8)、`test_target_resume_grounding.py`(1) |
| 匹配一致性 | ≥10 | **34** | `test_match_contract.py`(21)、`test_evidence_match_admission.py`(13) |
| 版本一致性 | ≥10 | **26** | `test_multi_job_version_consistency.py`(13)、`test_application_binding.py`(8)、`test_resume_studio_document.py`(4)、`test_resume_studio_interview.py`(1) |
| 导出 / 恢复 | ≥10 | **34** | `test_export_gate.py`(15)、`test_export_privacy.py`(15)、`test_resume_studio_export.py`(8)、`test_backup_restore.py`(7)、`test_resume_studio_reimport.py`(4) |

明细见 `fact-safety-cases.md` 与 `version-consistency-cases.md`。

## 四、安全与隐私

`test_export_privacy.py`（新增，15 项）+ 既有 `test_security_boundaries.py`：

- 简历生成载荷不含网申敏感字段（身份证号 / 家庭情况 / 健康状态 / 档案所在地 / 紧急联系人 / 可入职时间），逐字段守卫；
- 网申填表是**唯一**能读到这些字段的入口（对照用例确认它没有误伤）；
- 导出文件名不含手机号、邮箱、密钥形状，不含路径分隔符（防目录穿越）；
- 草稿名与正式名永远可区分；
- `delivery_snapshots` 表不含密钥类字段；
- 既有：SSRF 拦截、bridge 跨源/缺 token 拒绝、备份篡改检测、zip-slip、解压炸弹、备份不含 `.env`。

**本轮在跑这组测试时发现了两个真问题并已修复**：`build_resume_filename` 原先只过滤 Windows 非法字符，手机号、`chenlinexamplecom`、`sk-live-…`、`Bearer …` 会原样进文件名（`1ea1c65`）。

## 五、离线基准（不调用真实模型）

RUN_ID `offline-all-20261018T165202Z`，git head `11131e8`，4 个套件全部 `COMPLETED`：

| 套件 | 样本 | 关键指标 |
|---|---|---|
| jd | 16 | company / role_title / location / years / education / must-have 均 1.0 |
| match | 17 | accuracy 1.0，critical_omit_error 0，四类 F1 均 1.0 |
| rewrite | 17 | critical_fact_error_rate **0.059**，unsupported_number_rate **0.059**，人工维度 `UNRATED` |
| interview | 15 | jd_grounded 0.733，resume_grounded 0.667，**reference_answer_fact_error_count 5** |

同时跑了 `evals/overnight-v1/scripts/validate.py`：jobs=30、resumes=10、pairs=30、rewrites=90、bad_cases=15，校验通过。

**这些都是合成样本，不代表真实用户数据上的质量。** interview 套件的 5 次参考答案事实错误尤其要说明：它们是在**没有开事实闸门**的对照路径上统计出来的，正是 Sprint A 要拦的那类输出；开了闸门后对应的对抗用例全部被拦（见 `fact-safety-cases.md`）。

## 六、模型调用与成本

| 项 | 值 |
|---|---|
| 真实模型调用 | **0 次** |
| 花费 | **¥0**（本轮未授权付费调用） |
| 浏览器 E2E 的模型 | 本地桩服务（`browser/stub-llm-server.py`），OpenAI 兼容、不联网、可复现 |
| 离线基准 | 合成样本，无模型调用 |
| 未执行项 | 真实模型线上评测 → 标记 `NOT_RUN` |

不做「未检出编造 ⇒ 系统不会编造」的推断：闸门是保守的，对未知表述一律降级，但覆盖率与真实分布都没有被证明。
