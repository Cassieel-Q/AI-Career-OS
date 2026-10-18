# 事实安全专项用例（94 项，要求 ≥25）

分四个文件。下面列出全部用例名与它守住的那条线。

## A. `test_fact_trust.py`（25 项）— 三维互不推导 + 确定性闸门

| 用例 | 守的是什么 |
|---|---|
| `test_legacy_statuses_never_become_user_attested[CONFIRMED]` | 档案已确认 ≠ 事实已核对 |
| `…[ACCEPTED]` | 采纳改写 ≠ 事实已核对 |
| `…[READY]` | 状态就绪 ≠ 事实已核对 |
| `…[SUPPORTED]` | 模型说有依据 ≠ 用户核对过 |
| `…[DEFENDABLE]` | 主张可辩护 ≠ 事实已核对 |
| `…[NEEDS_CONFIRMATION]` | 待确认就是未核对 |
| `…[UNREVIEWED]` | 未核对不会被升级 |
| `…[UNKNOWN_STATUS]` | 未知状态一律按未核对处理（fail-closed） |
| `test_only_user_attested_counts_as_verified` | 只有 `USER_ATTESTED` 才算核对过 |
| `test_legacy_source_mapping_defaults_to_extracted` | 来源缺省为 `SOURCE_EXTRACTED`，不冒充 `USER_PROVIDED` |
| `test_extract_numeric_values_reads_chinese_numerals` | 中文数字（「十二」「百分之三十七」）也要被识别 |
| `test_screen_text_blocks_unsupported_numbers_and_terms` | 证据里没有的数字 / 高风险词一律拦 |
| `test_screen_text_allows_supported_statement` | 有依据的正常陈述不被误伤 |
| `test_screen_text_fails_closed_without_evidence` | 没有证据时一律降级，绝不默默放行 |
| `test_coverage_score_is_symmetric_zero_for_unrelated_text` | 覆盖率对无关文本为 0 |
| `test_analyze_aspects_flags_missing_result` | 缺「结果」这一维度会被标出来 |
| `test_facts_start_unreviewed_even_when_profile_is_confirmed` | **档案 CONFIRMED 时事实仍从 UNREVIEWED 起步** |
| `test_attest_records_user_confirmation` | 用户核对会留下时间与签名人 |
| `test_rejected_fact_is_not_treated_as_verified` | 被否认的事实不算核对过 |
| `test_attest_rejects_legacy_status_values` | 旧状态值不能写进来 |
| `test_attest_unknown_fact_key_returns_404` | 不存在的 fact_key 不静默创建 |
| `test_withdrawing_attestation_clears_verification` | 撤回核对会清空签名 |
| `test_edited_fact_only_writes_back_when_explicitly_requested` | 编辑事实默认不写回原始档案 |
| `test_missing_profile_returns_404` | 边界 |
| `test_fact_routes_list_and_attest` | 接口层串通 |

## B. `test_fact_safety_reference_answer.py`（27 项）— 参考答案不得编造

对抗样本（前 14 项参数化，逐条给出一类编造）：

| 编造类型 | 用例参数 |
|---|---|
| 编造访谈结论 | `invented_interview_conclusion` |
| 编造业务指标 | `invented_business_metric` |
| 参与 → 主导 | `participation_upgraded_to_ownership` |
| 原型 → 上线 | `prototype_upgraded_to_launch` |
| 想法 → 已实现 | `idea_upgraded_to_implemented` |
| 编造工具 | `invented_tooling` |
| 编造协作团队 | `invented_partner_team` |
| 编造时长与规模 | `invented_duration_and_scale` |
| 数字在但结论无依据 | `number_present_but_conclusion_unsupported` |
| 跨经历拼数字 | `numbers_spliced_across_experiences` |
| 中文数字编造 | `chinese_numeral_fabrication` |
| 主导动词不在证据里 | `ownership_verb_not_in_evidence` |
| 凭空的上线结果 | `shipped_result_from_thin_air` |
| 证据为空时编造 | `fabricated_when_evidence_is_empty` |

其余 13 项：

| 用例 | 守的是什么 |
|---|---|
| `test_reference_answer_blocks_when_model_self_review_says_ungrounded` | 模型自审说没依据，就信它并降级 |
| `test_reference_answer_blocks_unsupported_first_person_method_narrative_without_facts` | 无事实支撑的第一人称方法叙事要拦 |
| `test_reference_answer_degrades_when_model_omits_sample_wording` | 没给示范表达就降级，不自己脑补 |
| `test_reference_answer_blocks_legacy_payload_without_structured_detail` | 旧格式无结构化详情 → 拦，不走后门 |
| `test_rejected_fact_cannot_reappear_in_reference_answer` | 用户否认过的事实不得复活 |
| `test_ai_wording_adoption_is_not_fact_verification` | **采用 AI 表述 ≠ 核实事实**（核心） |
| `test_reference_answer_keeps_fully_supported_sample_wording` | 完全有依据的示范表达要放行（不误伤） |
| `test_reference_answer_uses_user_attested_facts` | 已核对事实可以进语料 |
| `test_reference_answer_allows_backward_compatible_payload_without_detail` | 旧格式兼容路径仍可用 |
| `test_degraded_reference_never_contains_first_person_narrative` | 降级输出绝不含第一人称成稿 |
| `test_degraded_reference_lists_missing_aspects_when_model_provides_none` | 降级也要给「还缺什么」，不能只说不行 |
| `test_evaluate_answer_blocks_facts_the_candidate_never_stated` | 候选人没说过的数字不能写进答案 |
| `test_evaluate_answer_keeps_answer_grounded_in_candidate_own_words` | 评分要贴着候选人自己的话 |

## C. `test_fact_edit_reverification.py`（6 项，本轮新增）

| 用例 | 守的是什么 |
|---|---|
| `test_editing_a_fact_revokes_its_attestation` | 事实文本一改，旧签名立刻退回 `UNREVIEWED` |
| `test_unchanged_facts_keep_their_attestation` | 只改 A，B 的签名不连坐 |
| `test_deleting_a_fact_revokes_its_attestation` | 事实删了，残留签名不能继续背书 |
| `test_invalidate_reports_changed_count` | 未改动时不撤销任何签名 |
| `test_confirmed_profile_put_still_rejected` | 对照项：直接 PUT 改已确认档案仍 409（既有规则未被动摇） |
| `test_confirmed_profile_fact_can_be_updated_by_attestation` | 已确认档案改事实的唯一入口是「核对 + 写回」同一次动作 |

## D. 其它文件里的对抗用例（36 项）

| 文件 | 项数 | 覆盖 |
|---|---|---|
| `test_webform_safety.py` | 23 | 网申填表不得越权读取、不得自动提交 |
| `test_assistant_write_proposals.py` | 8 | 助手只提议、不代写事实 |
| `test_ghost_experience_and_claim_gate.py` | 4 | 幽灵经历与主张闸门 |
| `test_target_resume_grounding.py` | 1 | 岗位简历改写的事实落地 |

## 五、这次专项真的抓到了什么

不是「跑通了所以安全」，而是**跑的时候抓出两个真问题并修掉**：

1. **文件名泄露手机号 / 邮箱 / 密钥形状**（`1ea1c65`）——见 `test_export_privacy.py`，属于事实与隐私边界。
2. **事实改了旧签名还在**（`41fef66`）——`invalidate_changed_attestations`。原先只要改了经历描述，之前那次「用户已确认」仍然挂在那儿，等于**用旧签名给新文本背书**；简历和参考回答都会把它当已核实事实放行。

## 六、不做的推断

这些用例通过，**不能**推出「系统不会编造」。闸门是保守的（不确定一律降级），但：

- 对抗样本集是人工构造的，未覆盖真实 JD / 真实简历的分布；
- 高风险词表与覆盖率阈值是经验值，可能出现漏网或误伤；
- 模型侧仍可能给出有依据但被错误拼接的表述，闸门查不出来。
