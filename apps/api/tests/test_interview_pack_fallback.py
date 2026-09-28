from app.mission_provider import OpenAIMissionProvider
from app.mission_schemas import (
    JobExtractionPayload,
    WhatMattersPayload,
    TargetResumePayload,
    RedTeamPayload,
)

extraction = JobExtractionPayload.model_validate(
    {
        "company": "Baidu",
        "role": "AI Product Manager",
        "role_family": "PRODUCT",
        "seniority": "MID",
        "capabilities": ["LLM evaluation"],
    }
)
what = WhatMattersPayload.model_validate(
    {
        "core_capabilities": [
            {"name": "LLM evaluation", "why": "Core for this role", "evidence_refs": ["jd-1"]}
        ],
        "high_importance_requirements": [],
        "evidence_expected": [],
        "likely_success_signals": [],
        "bonus_capabilities": [],
        "potential_interview_focus": [],
        "confidence": 0.7,
        "jd_evidence_refs": ["jd-1"],
    }
)
target = TargetResumePayload.model_validate(
    {
        "positioning_statement": "AI PM with evaluation workflow ownership",
        "recommended_experience_order": [],
        "bullets": [],
    }
)
red = RedTeamPayload.model_validate(
    {
        "findings": [
            {
                "claim": "Built an evaluation workflow",
                "jd_relevance": "Matches JD",
                "evidence_strength": "medium",
                "company_interview_trigger": "Baidu asks for eval depth",
                "attack_dimensions": ["evidence"],
                "likely_followups": ["How did you measure quality?"],
                "risk_level": "HIGH",
                "why": "Needs concrete metrics",
                "recommended_next_step": "Prepare dataset/rubric story",
                "evidence_refs": [],
            }
        ]
    }
)
pack = OpenAIMissionProvider._interview_pack_fallback(
    extraction=extraction,
    what_matters=what,
    interview_intel=[{"topic": "Search ads relevance", "why": "Baidu classic", "id": "intel-1"}],
    target_resume=target,
    red_team=red,
)
print("topics", len(pack.topics))
for t in pack.topics:
    print("-", t.priority, t.topic[:80])
assert pack.topics, "expected non-empty fallback"
print("OK")


def test_interview_pack_uses_skill_refs_and_questions_in_intel_body():
    result = OpenAIMissionProvider._interview_pack_fallback(
        extraction=extraction,
        what_matters=what,
        interview_intel=[{
            "skill_id": "CURATED_NIUKE_PRODUCT",
            "topic": "产品评测方案",
            "source_refs": ["niuke-article-1"],
            "body": "## Question patterns\n- 你如何设计评测方案？\n- 如何处理评测结果分歧？",
            "summary": "来自面经的评测追问（CURATED，非合成演示）",
        }],
        target_resume=target,
        red_team=red,
    )
    topic = next(row for row in result.topics if row.topic == "产品评测方案")
    assert "CURATED_NIUKE_PRODUCT" in topic.intel_refs
    assert "niuke-article-1" in topic.intel_refs
    assert any("你如何设计评测方案" in question for question in topic.question_patterns)
    assert "CURATED" not in topic.why
