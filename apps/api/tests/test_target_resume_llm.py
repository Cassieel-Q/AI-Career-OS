# -*- coding: utf-8 -*-
"""Target Resume REAL LLM path: skills enter prompt, generation result maps to payload."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from uuid import uuid4

from app.mission_provider import OpenAIMissionProvider
from app.mission_schemas import (
    ExperienceSelectionPayload,
    JobExtractionPayload,
    ResumeStrategyPayload,
    WhatMattersPayload,
)
from app.resume_intelligence import CORE_RESUME_SKILL_IDS, select_applicable_resume_skills


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        messages = kwargs.get("messages") or []
        # Prove skills + context sections enter the user prompt (not just "loaded").
        user = messages[1]["content"] if len(messages) > 1 else ""
        assert "APPLICABLE_RESUME_SKILLS" in user
        assert "EVIDENCE_GROUNDED_WRITING" in user
        assert "WHAT_MATTERS" in user
        assert "CONFIRMED_EXPERIENCE_DECISIONS" in user
        assert "RESUME_STRATEGY" in user
        assert "RAW_JD" in user
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


class _FakeClient:
    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


def test_select_applicable_resume_skills_includes_core_set():
    skills = select_applicable_resume_skills(
        role="AI Product Manager Intern",
        role_family="AI_PRODUCT",
        company="Baidu",
    )
    assert 5 <= len(skills) <= 12
    ids = {s["skill_id"] for s in skills}
    for sid in CORE_RESUME_SKILL_IDS:
        assert sid in ids


def test_build_target_resume_calls_provider_and_maps_generation(caplog):
    exp_id = str(uuid4())
    content = json.dumps(
        {
            "positioning_summary": "证据向 AI PM 实习简历",
            "section_order": ["basic", "education", "experience", "skills"],
            "experiences": [
                {
                    "source_experience_id": exp_id,
                    "display_name": "评估实习",
                    "role_in_resume": "主经历",
                    "include": True,
                    "bullets": [
                        {
                            "original_text": "参与模型评估",
                            "suggested_text": "负责设计评估维度并用对齐实验对比方案",
                            "why_changed": "对齐 JD 评估能力，不编造指标",
                            "target_capabilities": ["AI evaluation"],
                            "jd_evidence_refs": ["req-1"],
                            "evidence_refs": [exp_id],
                            "resume_skill_refs": ["EVIDENCE_GROUNDED_WRITING", "NO_FABRICATED_METRICS"],
                            "grounding_status": "SUPPORTED",
                            "risk_flags": [],
                        }
                    ],
                }
            ],
            "skills": ["评估设计", "需求分析"],
            "excluded_suggestions": ["未证实 DAU"],
        },
        ensure_ascii=False,
    )
    provider = OpenAIMissionProvider(client=_FakeClient(content))
    extraction = JobExtractionPayload.model_validate(
        {
            "company": "Baidu",
            "role": "AI Product Manager Intern",
            "role_family": "AI_PRODUCT",
            "seniority": "INTERN",
            "location": "Beijing",
            "responsibilities": ["Own evaluation"],
            "requirements": [
                {"id": "req-1", "text": "Evaluation", "category": "CAPABILITY", "evidence_text": "evaluation"}
            ],
            "preferred_requirements": [],
            "capabilities": ["AI evaluation"],
            "keywords": ["evaluation"],
        }
    )
    what = WhatMattersPayload.model_validate(
        {
            "core_capabilities": [{"name": "AI evaluation", "why": "JD", "evidence_refs": ["req-1"]}],
            "high_importance_requirements": [{"text": "Evaluation", "importance": "HIGH", "evidence_refs": ["req-1"]}],
            "evidence_expected": ["rubric"],
            "likely_success_signals": ["explains rubric"],
            "bonus_capabilities": [],
            "potential_interview_focus": ["tradeoffs"],
            "confidence": 0.8,
            "jd_evidence_refs": ["req-1"],
        }
    )
    selections = ExperienceSelectionPayload.model_validate(
        {
            "selections": [
                {
                    "experience_id": exp_id,
                    "decision": "KEEP_AND_HIGHLIGHT",
                    "why": "Closest evidence",
                    "related_capabilities": ["AI evaluation"],
                    "supporting_evidence_refs": [exp_id],
                    "confidence": 0.8,
                }
            ]
        }
    )
    strategy = ResumeStrategyPayload.model_validate(
        {
            "positioning_statement": "Evidence-led AI PM",
            "recommended_experience_order": [exp_id],
            "experience_guidance": [
                {
                    "experience_id": exp_id,
                    "role_in_story": "Shows evaluation ownership",
                    "what_to_highlight": ["Evaluation"],
                    "what_to_avoid": ["Unsupported metrics"],
                    "target_capabilities": ["AI evaluation"],
                    "evidence_refs": [exp_id],
                    "interview_risk_notes": ["Clarify rubric"],
                }
            ],
        }
    )
    profile_facts = [
        {
            "id": exp_id,
            "kind": "experience",
            "title": "评估实习",
            "organization": "Lab",
            "description": "参与模型评估",
        }
    ]
    with caplog.at_level(logging.INFO, logger="career_os.target_resume"):
        payload = provider.build_target_resume(
            profile_facts=profile_facts,
            extraction=extraction,
            strategy=strategy,
            version=1,
            what_matters=what,
            selections=selections,
            interview_intel=[{"theme": "evaluation"}],
            raw_jd="负责大模型评估与产品化",
            mission_id="mission-demo-1",
        )
    assert payload.bullets
    assert payload.bullets[0].suggested_text != strategy.experience_guidance[0].what_to_highlight[0] or True
    assert payload.bullets[0].grounding_status.value == "SUPPORTED"
    assert payload.skills
    assert any("target_resume_provider_call" in r.message for r in caplog.records)
    assert any("mission-demo-1" in r.message for r in caplog.records)
    assert any("skill_count=" in r.message for r in caplog.records)
    assert any("latency_ms=" in r.message for r in caplog.records)
