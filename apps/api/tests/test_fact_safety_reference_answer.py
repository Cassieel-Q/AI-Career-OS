"""参考答案事实安全对抗测试集（可信求职 v1.2 · Sprint A · 指令 1.5）。

目标：**任何未经确认的新候选人事实都不能直接变成第一人称参考答案中的确定陈述。**

覆盖六类编造：
- 无依据的访谈结论与业务指标
- 参与改主导、原型改上线、设想改实现
- 凭空新增工具、团队、时间、人数、规模
- 数字存在但不支持当前结论
- 跨经历数字拼接
- 用户已拒绝的事实再次出现

以及两条正向要求：事实充分时能正常生成完整回答；用户已核实的事实可以使用。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.interview_provider import OpenAIInterviewProvider

#: 一段「事实很少」的合成经历：只有访谈与原型，没有结果、没有指标。
SPARSE_FACTS = "访谈12名同学，完成PRD和Figma原型。"


class _FakeCompletions:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def create(self, **_: Any) -> SimpleNamespace:
        content = json.dumps(self.payload, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _provider(payload: dict[str, Any]) -> OpenAIInterviewProvider:
    chat = SimpleNamespace(completions=_FakeCompletions(payload))
    return OpenAIInterviewProvider(client=SimpleNamespace(chat=chat))


def _ask(
    reference: str | None,
    *,
    facts: str = SPARSE_FACTS,
    detail: dict[str, Any] | None = None,
    attested: list[str] | None = None,
    rejected: list[str] | None = None,
) -> Any:
    evaluation: dict[str, Any] = {
        "score": 6,
        "strong_points": ["结构完整"],
        "weak_points": ["缺少结果"],
    }
    if reference is not None:
        evaluation["reference_answer"] = reference
    if detail is not None:
        evaluation["reference_answer_detail"] = detail
    payload = {"question": "请介绍这段经历。", "skill_id": "PROJECT_DEEP_DIVE", "evaluation": evaluation}
    return _provider(payload).ask(
        target_job={"final_resume": {}},
        claim={"claim": facts},
        evidence=[{"value": facts}],
        skills=[],
        turns=[],
        answer="我做了需求分析和原型。",
        attested_facts=attested,
        rejected_facts=rejected,
    ).evaluation


def _grounded_detail(reference: str, *, known: list[dict] | None = None) -> dict[str, Any]:
    return {
        "grounded": True,
        "known_facts": known or [{"text": SPARSE_FACTS, "source_kind": "SOURCE_EXTRACTED", "quote": SPARSE_FACTS}],
        "missing_facts": [{"aspect": "结果", "question": "最后的效果如何？"}],
        "answer_structure": ["背景", "动作", "结果"],
        "sample_wording": reference,
    }


def assert_blocked(evaluation: Any) -> None:
    """被拦截：必须降级成「已知事实 / 待补 / 结构」，不得保留第一人称成稿。"""
    detail = evaluation.reference_answer_detail
    assert detail is not None, "被拦截时必须带回结构化详情"
    assert detail.grounded is False
    assert detail.sample_wording is None
    assert "【已知事实】" in (evaluation.reference_answer or "")
    assert "【还需要你补充】" in (evaluation.reference_answer or "")
    assert any("未确认" in item for item in evaluation.weak_points)


def assert_allowed(evaluation: Any, expected: str) -> None:
    detail = evaluation.reference_answer_detail
    assert detail is not None
    assert detail.grounded is True
    assert evaluation.reference_answer == expected
    assert detail.sample_wording == expected


# --------------------------------------------------------------------------
# A. 必须拦截的编造（每条都是真实会发生的失败模式）
# --------------------------------------------------------------------------

BLOCKED_CASES: list[tuple[str, str, str]] = [
    (
        "invented_interview_conclusion",
        "我访谈了20位同学，发现大家最大的问题是效率低，于是重新设计了流程。",
        SPARSE_FACTS,
    ),
    (
        "invented_business_metric",
        "我访谈了12名同学，完成PRD和Figma原型，上线后日活提升了30%。",
        SPARSE_FACTS,
    ),
    (
        "participation_upgraded_to_ownership",
        "我主导了整个项目，带领5人团队完成设计与开发。",
        SPARSE_FACTS,
    ),
    (
        "prototype_upgraded_to_launch",
        "我访谈了12名同学，完成PRD和Figma原型，产品已经上线并稳定运行。",
        SPARSE_FACTS,
    ),
    (
        "idea_upgraded_to_implemented",
        "我实现了智能推荐模块，用户留存显著提高。",
        SPARSE_FACTS,
    ),
    (
        "invented_tooling",
        "我访谈了12名同学，用PyTorch搭建了推荐模型，并用飞书多维表格管理需求。",
        SPARSE_FACTS,
    ),
    (
        "invented_partner_team",
        "我访谈了12名同学，与设计团队和算法团队紧密配合完成了原型。",
        SPARSE_FACTS,
    ),
    (
        "invented_duration_and_scale",
        "项目历时一年半，我访谈了12名同学，覆盖全国二十所高校。",
        SPARSE_FACTS,
    ),
    (
        "number_present_but_conclusion_unsupported",
        "我访谈了12名同学，转化率提升了20%，获得导师一致好评。",
        SPARSE_FACTS,
    ),
    (
        "numbers_spliced_across_experiences",
        "我访谈了12名同学，完成30页PRD和三份Figma原型。",
        SPARSE_FACTS,
    ),
    (
        "chinese_numeral_fabrication",
        "我访谈了五十名同学，完成PRD和Figma原型。",
        SPARSE_FACTS,
    ),
    (
        "ownership_verb_not_in_evidence",
        "我带领小组完成了PRD和Figma原型。",
        SPARSE_FACTS,
    ),
    (
        "shipped_result_from_thin_air",
        "我访谈了12名同学，完成PRD和Figma原型，为公司节省了二十万元成本。",
        SPARSE_FACTS,
    ),
    (
        "fabricated_when_evidence_is_empty",
        "我在这个项目中负责用户增长，三个月内把留存提高了15%。",
        "",
    ),
]


@pytest.mark.parametrize("case_id,reference,facts", BLOCKED_CASES, ids=[case[0] for case in BLOCKED_CASES])
def test_reference_answer_blocks_fabricated_candidate_facts(case_id: str, reference: str, facts: str) -> None:
    """模型自审为 grounded=True 也不能放行——确定性闸门必须独立拦住。"""
    evaluation = _ask(reference, facts=facts, detail=_grounded_detail(reference))
    assert_blocked(evaluation)
    # 被拦截的原文不能原样出现在降级文本里
    assert reference not in (evaluation.reference_answer or "")


def test_reference_answer_blocks_when_model_self_review_says_ungrounded() -> None:
    reference = "我访谈了12名同学，完成PRD和Figma原型。"
    detail = _grounded_detail(reference)
    detail["grounded"] = False
    evaluation = _ask(reference, detail=detail)
    assert_blocked(evaluation)


def test_reference_answer_blocks_unsupported_first_person_method_narrative_without_facts() -> None:
    """「我先确认目标，再比较方案，最后用结果验证」这类成稿在没有任何事实时也必须降级。"""
    evaluation = _ask("我先确认目标和约束，再比较候选方案，最后用测试或交付结果验证选择。", facts="")
    assert_blocked(evaluation)


def test_reference_answer_degrades_when_model_omits_sample_wording() -> None:
    detail = _grounded_detail("ignored")
    detail["sample_wording"] = None
    evaluation = _ask(None, detail=detail)
    assert_blocked(evaluation)


def test_reference_answer_blocks_legacy_payload_without_structured_detail() -> None:
    """模型没给结构化详情时，只靠确定性闸门也要拦住编造。"""
    evaluation = _ask("我访谈了40位创作者，据此完成方案。", facts=SPARSE_FACTS)
    assert_blocked(evaluation)
    assert evaluation.reference_answer_detail.known_facts == []


def test_rejected_fact_cannot_reappear_in_reference_answer() -> None:
    rejected_fact = "我在腾讯实习期间负责推荐系统的排序优化"
    reference = f"我访谈了12名同学，完成PRD和Figma原型；{rejected_fact}。"
    evaluation = _ask(reference, detail=_grounded_detail(reference), rejected=[rejected_fact])
    assert_blocked(evaluation)
    assert "你已标记为不属实" in (evaluation.reference_answer_detail.blocked_reason or "")


def test_ai_wording_adoption_is_not_fact_verification() -> None:
    """用户采纳 AI 改写 ≠ 事实已核实：改写稿里的新事实仍然要被拦。"""
    evaluation = _ask(
        "我访谈了12名同学，完成PRD和Figma原型，方案被学校采纳并推广到八个院系。",
        detail={
            "grounded": True,
            "known_facts": [{"text": "方案被学校采纳并推广", "source_kind": "AI_PROPOSED"}],
            "missing_facts": [],
            "answer_structure": ["背景", "动作", "结果"],
            "sample_wording": "我访谈了12名同学，完成PRD和Figma原型，方案被学校采纳并推广到八个院系。",
        },
    )
    assert_blocked(evaluation)


# --------------------------------------------------------------------------
# B. 事实充分时必须正常产出完整回答（不能矫枉过正）
# --------------------------------------------------------------------------


def test_reference_answer_keeps_fully_supported_sample_wording() -> None:
    reference = "我访谈了12名同学，完成PRD和Figma原型。"
    evaluation = _ask(reference, detail=_grounded_detail(reference))
    assert_allowed(evaluation, reference)


def test_reference_answer_uses_user_attested_facts() -> None:
    """用户明确核对过的事实可以进入成稿回答。"""
    attested = "我在校园二手平台项目里负责用户访谈，三个月内完成12份访谈并产出PRD"
    reference = "我在校园二手平台项目里负责用户访谈，三个月内完成12份访谈并产出PRD。"
    evaluation = _ask(reference, facts="校园二手平台项目", attested=[attested], detail=_grounded_detail(reference))
    assert_allowed(evaluation, reference)


def test_reference_answer_allows_backward_compatible_payload_without_detail() -> None:
    """旧格式（无 detail）但内容完全有依据时，仍然放行。"""
    reference = "我访谈了12名同学，完成PRD和Figma原型。"
    evaluation = _ask(reference)
    assert_allowed(evaluation, reference)


def test_degraded_reference_never_contains_first_person_narrative() -> None:
    evaluation = _ask("我带领团队把这个功能做上线了，效率提升40%。", facts=SPARSE_FACTS)
    text = evaluation.reference_answer or ""
    assert "带领团队" not in text
    assert "效率提升" not in text
    assert "【建议回答结构】" in text


def test_degraded_reference_lists_missing_aspects_when_model_provides_none() -> None:
    """模型没说缺什么时，也要给出「行动 / 困难 / 结果」这些默认待补项。"""
    detail = _grounded_detail("我带领团队上线了这个功能。")
    detail["missing_facts"] = []
    evaluation = _ask("我带领团队上线了这个功能。", facts=SPARSE_FACTS, detail=detail)
    text = evaluation.reference_answer or ""
    assert "你的具体动作" in text
    assert "可核对的结果" in text


# --------------------------------------------------------------------------
# C. evaluate_answer（真实面试记录评分）走同一套闸门
# --------------------------------------------------------------------------


def _evaluate(answer: str, context: str, reference: str, *, detail: dict[str, Any] | None = None) -> Any:
    evaluation: dict[str, Any] = {"score": 6, "reference_answer": reference, "strong_points": [], "weak_points": []}
    if detail is not None:
        evaluation["reference_answer_detail"] = detail
    payload = {"evaluation": evaluation}
    provider = _provider(payload)
    return provider.evaluate_answer(question="讲一个你主导的项目。", answer=answer, context=context)


def test_evaluate_answer_blocks_facts_the_candidate_never_stated() -> None:
    evaluation = _evaluate(
        answer="我做过一个校园二手平台，负责访谈。",
        context="候选人面试 AI 产品实习岗位。",
        reference="我主导了校园二手平台，上线后日活提升30%。",
        detail=_grounded_detail("我主导了校园二手平台，上线后日活提升30%。"),
    )
    assert evaluation.reference_answer_detail is None or evaluation.reference_answer_detail.grounded is False
    assert "【已知事实】" in (evaluation.reference_answer or "")


def test_evaluate_answer_keeps_answer_grounded_in_candidate_own_words() -> None:
    reference = "我做过一个校园二手平台，负责访谈。"
    evaluation = _evaluate(
        answer="我做过一个校园二手平台，负责访谈。",
        context="候选人面试 AI 产品实习岗位。",
        reference=reference,
        detail=_grounded_detail(reference),
    )
    assert evaluation.reference_answer == reference
    assert evaluation.reference_answer_detail is not None
    assert evaluation.reference_answer_detail.grounded is True
