# 匹配一致性与版本一致性专项用例（匹配 34 项、版本 26 项，各要求 ≥10）

## 一、匹配一致性（34 项）

### `test_match_contract.py`（21 项）

| 用例 | 守的是什么 |
|---|---|
| `test_grade_is_derived_from_score_only` | 等级只能由分数推导，不许三处各算各的 |
| `test_contradicting_model_advice_is_dropped[78-建议先换更匹配的岗位。]` | 78 分说「别投」→ 丢弃，不与分数打架 |
| `test_contradicting_model_advice_is_dropped[85-当前不建议投递。]` | 85 分说「别投」→ 丢弃 |
| `test_contradicting_model_advice_is_dropped[72-暂不投递，先补强经历。]` | 72 分说「别投」→ 丢弃 |
| `test_consistent_model_advice_is_kept` | 与分数一致的建议保留（不误伤） |
| `test_low_score_never_shows_go_ahead_advice` | 低分绝不出现「建议投递」 |
| `test_legacy_fields_mirror_the_single_contract` | 旧字段只是镜像，不是第二套口径 |
| `test_blocking_gaps_cover_unmet_hard_requirements` | 硬门槛没满足要进阻塞项 |
| `test_no_hard_markers_means_no_blocking_gaps` | 没有硬门槛就不该有阻塞项 |
| `test_hard_requirement_already_covered_is_not_a_gap` | 已满足的硬门槛不算缺口 |
| `test_blocking_gaps_survive_high_skill_relevance` | 技能再匹配也不能盖掉硬门槛 |
| `test_fingerprint_changes_when_resume_changes` | 简历变了 → 指纹变 → 结果过期 |
| `test_style_only_changes_do_not_invalidate` | 纯排版改动不该判过期 |
| `test_resume_edit_marks_result_stale` | 改简历 → 标 stale |
| `test_jd_edit_marks_result_stale` | 改 JD → 标 stale |
| `test_legacy_cache_without_fingerprint_is_conservatively_stale` | 老缓存没指纹 → 保守判过期 |
| `test_cached_result_is_returned_untouched_with_a_stale_flag` | **过期只加标记，绝不静默替换原结果** |
| `test_refresh_keeps_previous_result_readable` | 刷新后旧结果仍可读（历史不被抹掉） |
| `test_software_product_role_has_no_hardware_signals` | 软件岗不冒出硬件信号 |
| `test_hardware_role_is_detected_by_specific_signals` | 硬件岗能被具体信号识别 |
| `test_hardware_draft_reason_cites_real_jd_fragments` | 项目草案的依据必须引用 JD 原文片段 |

### `test_evidence_match_admission.py`（13 项）

证据准入与匹配口径一致性（同一批事实在不同入口得到同一结论，不因入口不同而漂移）。

## 二、版本一致性（26 项）

### `test_multi_job_version_consistency.py`（13 项，本轮新增）

| 用例 | 守的是什么 |
|---|---|
| `test_each_mission_keeps_its_own_studio_document` | 每个岗位有自己的工作台文档，不共用 |
| `test_edit_order_in_one_mission_does_not_touch_others` | **改 A 岗位不会动到 B 岗位** |
| `test_fact_impact_reports_affected_missions_without_changing_anything` | 影响面只报告，不改任何东西 |
| `test_selective_sync_updates_only_the_chosen_mission` | 同步只改被选中的那一份 |
| `test_sync_marks_node_unconfirmed_and_invalidates_delivery_confirmation` | 同步后节点回 `NEEDS_CONFIRMATION`，已确认的投递版失效 |
| `test_sync_never_rewrites_ai_bullets` | **AI 改写要点永不被自动改写** |
| `test_impact_flags_already_delivered_missions` | 已投递的岗位会被单独标出来 |
| `test_impact_endpoint_and_sync_endpoint` | 接口层串通 |
| `test_interview_resume_says_no_delivery_when_not_applied` | 没投递时明说「尚无正式投递版本」 |
| `test_confirming_final_version_records_an_immutable_snapshot` | 确认即落不可变快照 |
| `test_interview_reads_delivered_version_not_latest_studio` | **面试读的是投出去的那版，不是最新的** |
| `test_multiple_deliveries_can_be_selected_explicitly` | 多次投递可选 |
| `test_proof_service_interview_context_prefers_delivered_snapshot` | 证据侧同样优先投递快照 |

### `test_application_binding.py`（8 项）

投递记录与简历版本的绑定、状态推进与退回、未确认不得绑定。

### `test_resume_studio_document.py`（4 项）

Studio 文档的修订号语义、节点寻址、操作回放。

### `test_resume_studio_interview.py`（1 项）

面试侧读取 Studio 版本的口径一致。

## 三、导出与恢复（34 项，与版本强相关）

### `test_export_gate.py`（15 项）

| 用例 | 守的是什么 |
|---|---|
| `test_clean_document_passes_both_modes` | 干净文档草稿/正式都放行 |
| `test_missing_name_warns_for_draft_but_blocks_final` | 缺姓名：草稿只提示，正式版**阻塞** |
| `test_missing_contact_blocks_only_final` | 缺联系方式只在正式版阻塞 |
| `test_high_risk_unconfirmed_fact_blocks_final_export` | 高风险未核对事实阻塞正式版 |
| `test_placeholder_residue_blocks_every_mode` | 占位符残留两种模式都堵 |
| `test_empty_resume_blocks_every_mode` | 空简历两种模式都堵 |
| `test_info_level_does_not_block_anything` | info 级不阻塞（只有建议作用） |
| `test_final_filename_follows_the_agreed_pattern` | `姓名_公司_岗位_vN.pdf` |
| `test_draft_filename_is_clearly_marked` | 草稿带 `_DRAFT` |
| `test_filename_strips_windows_illegal_characters` | Windows 非法字符 |
| `test_filename_never_repeats_revision_in_draft_and_final` | 版本不重复计数 |
| `test_final_pdf_requires_confirmation_while_draft_is_always_available` | **草稿永远可导，正式版必须先确认** |
| `test_final_pdf_blocks_when_the_final_checks_fail` | 门禁不过就出不了正式版 |
| `test_preview_returns_both_draft_and_final_checks` | 预览同时给两套口径 |
| `test_download_headers_are_exposed_to_the_browser` | 下载头要暴露给浏览器（否则前端拿不到文件名） |

### `test_export_privacy.py`（15 项，本轮新增）

见 `fact-safety-cases.md` 第五节；覆盖敏感字段边界、文件名隐私、快照表结构。

### `test_resume_studio_export.py`（8 项）/ `test_backup_restore.py`（7 项）/ `test_resume_studio_reimport.py`（4 项）

导出文本口径、备份恢复只生成新数据集绝不覆盖当前库、重新导入源事实的版本行为。

## 四、这轮发现的版本一致性真问题

1. **SQLAlchemy JSON 原地修改不落库**：`sync_mission` 早期版本把同一个 dict 赋回 `document_json`，SQLAlchemy 判定「未变更」，结果**修订号涨了、内容没变**。修法：`deepcopy` + `flag_modified`。
2. **投递前已有快照时被误判来源**：`resolve_interview_resume` 在有快照的情况下仍返回 `delivered_application`。修法：按 `studio_revision` 匹配快照的兜底分支。
3. **改事实不撤销旧签名**：见 `fact-safety-cases.md`。
