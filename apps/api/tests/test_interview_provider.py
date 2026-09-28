from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.interview_provider import InterviewProviderInvalidResponseError, OpenAIInterviewProvider
from app.interview_skills import INTERVIEW_SKILLS, skill_records


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def test_interview_provider_uses_claim_jd_evidence_and_skill_pack(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    completions = FakeCompletions(json.dumps({"question": "How did you evaluate it?", "skill_id": "LLM_EVALUATION", "followup_dimensions": ["dataset"], "evaluation": {"strong_points": [], "weak_points": []}}))

    result = OpenAIInterviewProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=completions))).ask(
        target_job={"raw_text": "Build evaluation workflows", "interview_intel": [{"question_patterns": ["你如何定义测试指标？"]}]},
        claim={"claim": "Designed an LLM evaluation workflow"},
        evidence=[{"id": "fact-1", "value": "LLM evaluation"}],
        skills=[{"id": "LLM_EVALUATION", "interviewer_intent": "test evaluation depth"}],
        turns=[],
        answer=None,
    )

    assert result.question == "How did you evaluate it?"
    assert completions.request["response_format"] == {"type": "json_object"}
    user_content = str(completions.request["messages"][1]["content"])
    assert "Designed an LLM evaluation workflow" in user_content
    assert "LLM_EVALUATION" in user_content
    assert "你如何定义测试指标？" in user_content
    assert "Simplified Chinese" in OpenAIInterviewProvider._system_prompt()


def test_interview_provider_rejects_non_object_response() -> None:
    provider = OpenAIInterviewProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions("[]"))))

    with pytest.raises(InterviewProviderInvalidResponseError) as caught:
        provider.ask(target_job={}, claim={}, evidence=[], skills=[], turns=[], answer=None)

    assert caught.value.reason == "response_shape"


def test_interview_provider_soft_normalizes_string_evaluation_opening() -> None:
    """LLM opening turn often returns evaluation='opening' (str); soft-normalize into InterviewEvaluation."""
    content = json.dumps(
        {
            "question": "请先用一分钟介绍与该主张最相关的项目？",
            "skill_id": "PROJECT_DEEP_DIVE",
            "followup_dimensions": "impact",
            "evaluation": "opening",
        },
        ensure_ascii=False,
    )
    result = OpenAIInterviewProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content)))).ask(
        target_job={},
        claim={},
        evidence=[],
        skills=[],
        turns=[],
        answer=None,
    )

    assert result.question.startswith("请先用一分钟")
    assert result.skill_id == "PROJECT_DEEP_DIVE"
    assert result.followup_dimensions == ["impact"]
    assert result.evaluation.gap_type is None
    assert result.evaluation.strong_points == []
    assert result.evaluation.weak_points == []
    assert "开场" in (result.evaluation.why or "")


def test_interview_provider_soft_normalizes_pass_label_and_list_coercions() -> None:
    fact_id = str(uuid4())
    content = json.dumps(
        {
            "question": "What metric moved?",
            "skill_id": "PRODUCT_METRICS",
            "followup_dimensions": ["baseline", "owner"],
            "evaluation": {
                "strong_points": "named a metric",
                "weak_points": "no baseline",
                "gap_type": "evidence",
                "evidence_refs": fact_id,
                "recommended_next_action": "补一份前后对比数据",
            },
        },
        ensure_ascii=False,
    )
    result = OpenAIInterviewProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content)))).ask(
        target_job={},
        claim={},
        evidence=[],
        skills=[],
        turns=[],
        answer="we improved retention",
    )

    assert result.evaluation.strong_points == ["named a metric"]
    assert result.evaluation.weak_points == ["no baseline"]
    assert result.evaluation.gap_type is not None
    assert result.evaluation.gap_type.value == "EVIDENCE_GAP"
    assert [str(x) for x in result.evaluation.evidence_refs] == [fact_id]


def test_interview_provider_keeps_a_simple_answer_score() -> None:
    content = json.dumps({
        "question": "为什么这样设计？",
        "skill_id": "PRODUCT_SENSE",
        "evaluation": {"score": 7, "strong_points": ["结构清晰"], "weak_points": ["缺少结果"], "reference_answer": "我先确认目标，再比较方案，最后用结果验证。"},
    }, ensure_ascii=False)
    result = OpenAIInterviewProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content)))).ask(
        target_job={}, claim={}, evidence=[], skills=[], turns=[], answer="我先分析用户需求，再确定方案。",
    )

    assert result.evaluation.score == 7
    assert result.evaluation.reference_answer.startswith("我先确认目标")


def test_ai_product_manager_skill_pack_has_ten_structured_skills() -> None:
    assert len(INTERVIEW_SKILLS) == 10
    records = skill_records()
    assert {record["id"] for record in records} == {
        "PRODUCT_SENSE", "PRODUCT_METRICS", "AI_PRODUCT_FUNDAMENTALS", "LLM_EVALUATION",
        "AGENT_WORKFLOW", "PROJECT_DEEP_DIVE", "TECHNICAL_FLUENCY", "BEHAVIORAL",
        "EXPERIMENTATION", "COMPETITIVE_REASONING",
    }
    assert all(record["followup_dimensions"] for record in records)
