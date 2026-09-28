import json

import pytest

from app.mission_provider import OpenAIMissionProvider, MissionProviderInvalidResponseError, _timeout_seconds


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Completion:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": _Message(content)})()]


class _Completions:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Completion(self.content)


class _Client:
    def __init__(self, content: str):
        self.chat = type("Chat", (), {"completions": _Completions(content)})()


def test_mission_provider_uses_json_object_transport_and_strict_parse():
    payload = {
        "company": "Baidu",
        "role": "AI Product Manager",
        "role_family": "AI_PRODUCT",
        "seniority": "MID",
        "location": "Beijing",
        "responsibilities": ["Design evaluation workflows"],
        "requirements": [{"id": "req-1", "text": "Evaluation", "category": "CAPABILITY", "evidence_text": "evaluation"}],
        "preferred_requirements": [],
        "capabilities": ["AI evaluation"],
        "keywords": ["evaluation"],
    }
    client = _Client(json.dumps(payload))
    provider = OpenAIMissionProvider(client=client)

    parsed = provider.parse_jd("Evaluation JD")

    assert parsed.company == "Baidu"
    request = client.chat.completions.calls[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["model"]
    assert isinstance(request["messages"][1]["content"], str)


def test_mission_provider_uses_faster_default_timeout_with_mission_override(monkeypatch):
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_MISSION_TIMEOUT_SECONDS", raising=False)
    assert _timeout_seconds() == 15.0
    monkeypatch.setenv("OPENAI_MISSION_TIMEOUT_SECONDS", "21")
    assert _timeout_seconds() == 21.0


@pytest.mark.parametrize("content,reason", [("not-json", "json_decode"), ('{"company":"Baidu"}', "schema_validation")])
def test_mission_provider_classifies_structured_output_failures(content: str, reason: str):
    provider = OpenAIMissionProvider(client=_Client(content))

    with pytest.raises(MissionProviderInvalidResponseError) as error:
        provider.parse_jd("Evaluation JD")

    assert error.value.reason == reason


def test_resume_strategy_does_not_emit_english_placeholder_guidance():
    normalized = OpenAIMissionProvider._normalize_resume_strategy({
        "experience_guidance": [{
            "experience_id": "exp-1",
            "role_in_story": "Support the target role narrative with confirmed evidence only.",
        }],
    })
    assert normalized["experience_guidance"][0]["role_in_story"] != "Support the target role narrative with confirmed evidence only."
    assert "exp-1" in normalized["experience_guidance"][0]["role_in_story"]


def test_target_resume_prompt_requires_concrete_jd_specific_project_drafts():
    prompt = OpenAIMissionProvider._prompt("draft a versioned target resume via Resume Optimization")
    assert "concrete JD-specific" in prompt
    assert "SYNTHETIC_PROJECT" in prompt
    assert "intelligent-hardware" in prompt


def test_target_resume_generation_deduplicates_same_experience_bullets():
    normalized = OpenAIMissionProvider._normalize_target_resume_generation({
        "experiences": [{
            "source_experience_id": "exp-1",
            "display_name": "研究项目",
            "bullets": [
                {"original_text": "负责评测", "suggested_text": "负责评测并整理结果"},
                {"original_text": "负责评测", "suggested_text": "负责评测并整理结果"},
            ],
        }],
    })
    assert len(normalized["experiences"][0]["bullets"]) == 1


def test_target_resume_marks_source_less_project_drafts():
    from app.mission_schemas import ResumeStrategyPayload, TargetResumeGenerationResult

    normalized = OpenAIMissionProvider._normalize_target_resume_generation({
        "experiences": [{
            "source_experience_id": None,
            "display_name": "项目草案：智能硬件评测闭环",
            "bullets": [{
                "original_text": "项目草案",
                "suggested_text": "设计智能硬件评测闭环并整理验证方案",
            }],
        }],
    })
    payload = OpenAIMissionProvider._generation_to_target_payload(
        TargetResumeGenerationResult.model_validate(normalized),
        strategy=ResumeStrategyPayload.model_validate({"positioning_statement": "面向目标岗位"}),
    )
    assert payload.bullets[0].source_experience_id is None
    assert "SYNTHETIC_PROJECT" in payload.bullets[0].risk_flags


def test_experience_fallback_does_not_keep_unrelated_campus_roles():
    from app.mission_schemas import JobExtractionPayload, WhatMattersPayload

    provider = OpenAIMissionProvider(client=_Client("not-json"))
    extraction = JobExtractionPayload.model_validate({
        "company": "百度",
        "role": "物理AI产品经理",
        "role_family": "AI_PRODUCT",
        "seniority": "INTERN",
        "responsibilities": ["智能硬件产品定义", "量产导入"],
        "requirements": [],
        "preferred_requirements": [],
        "capabilities": ["智能硬件产品全周期操盘", "软硬一体化产品定义与量产导入"],
        "keywords": ["产品定义", "数据分析"],
    })
    matters = WhatMattersPayload.model_validate({
        "core_capabilities": [{"name": "智能硬件产品全周期操盘", "why": "JD", "evidence_refs": []}],
        "high_importance_requirements": [],
        "confidence": 0.7,
    })
    result = provider.select_experiences(
        profile_facts=[
            {"id": "11111111-1111-4111-8111-111111111111", "kind": "experience", "title": "班级心理委员", "organization": "大连理工大学", "description": "负责班级心理沟通"},
            {"id": "22222222-2222-4222-8222-222222222222", "kind": "experience", "title": "全国海洋航行器设计与制作大赛", "description": "完成浮式风机模型组装、发电效率测试并获国家级一等奖", "experience_type": "PROJECT"},
        ],
        extraction=extraction,
        what_matters=matters,
    )
    decisions = {str(row.experience_id): str(row.decision.value if hasattr(row.decision, "value") else row.decision) for row in result.selections}
    assert decisions["11111111-1111-4111-8111-111111111111"] == "OMIT"
    assert decisions["22222222-2222-4222-8222-222222222222"] == "KEEP_AND_HIGHLIGHT"


def test_strategy_fallback_only_carries_non_omitted_experiences():
    from app.mission_schemas import ExperienceSelectionPayload, JobExtractionPayload, WhatMattersPayload

    provider = OpenAIMissionProvider(client=_Client("not-json"))
    extraction = JobExtractionPayload.model_validate({"company": "百度", "role": "AI产品经理", "role_family": "AI_PRODUCT", "seniority": "INTERN", "requirements": [], "preferred_requirements": [], "capabilities": ["产品定义"], "keywords": []})
    matters = WhatMattersPayload.model_validate({"core_capabilities": [{"name": "产品定义", "why": "JD", "evidence_refs": []}], "high_importance_requirements": [], "confidence": 0.7})
    selections = ExperienceSelectionPayload.model_validate({"selections": [
        {"experience_id": "22222222-2222-4222-8222-222222222222", "decision": "KEEP_AND_HIGHLIGHT", "why": "项目中完成模型组装和效率测试", "related_capabilities": ["产品定义"], "supporting_evidence_refs": [], "confidence": 0.9},
        {"experience_id": "11111111-1111-4111-8111-111111111111", "decision": "OMIT", "why": "与岗位无关", "related_capabilities": [], "supporting_evidence_refs": [], "confidence": 0.9},
    ]})
    strategy = provider.build_resume_strategy(
        profile_facts=[{"id": "22222222-2222-4222-8222-222222222222", "kind": "experience", "title": "海洋航行器项目", "description": "完成模型组装和效率测试"}],
        extraction=extraction,
        what_matters=matters,
        selections=selections,
    )
    assert [str(row.experience_id) for row in strategy.experience_guidance] == ["22222222-2222-4222-8222-222222222222"]
    assert any("模型组装" in item for item in strategy.experience_guidance[0].what_to_highlight)

