from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.mission_schemas import (
    ExperienceSelectionPayload,
    JobExtractionPayload,
    ResumeStrategyPayload,
    WhatMattersPayload,
)
from app.mission_service import (
    _ensure_strategy_grounded,
    _prune_resume_strategy,
)
from app.claim_provider import OpenAIClaimAnalysisProvider

class _Exp:
    def __init__(self, eid):
        self.id = eid


class _Profile:
    def __init__(self, eids):
        self.experiences = [_Exp(e) for e in eids]


def _wm():
    return WhatMattersPayload.model_validate({
        "core_capabilities": [{"name": "PM", "why": "needed for role", "evidence_refs": ["req-1"]}],
        "high_importance_requirements": [],
        "evidence_expected": [],
        "likely_success_signals": [],
        "bonus_capabilities": [],
        "potential_interview_focus": [],
        "confidence": 0.5,
        "jd_evidence_refs": ["req-1"],
    })


def _extraction():
    return JobExtractionPayload.model_validate({
        "company": "Baidu",
        "role": "AI PM",
        "role_family": "PM",
        "seniority": "ENTRY_LEVEL",
        "location": "Beijing",
        "requirements": [],
        "preferred_requirements": [],
        "capabilities": [],
        "keywords": [],
    })


def test_prune_drops_ghost_experience_ids():
    real = uuid4()
    ghost = uuid4()
    strategy = ResumeStrategyPayload.model_validate({
        "positioning_statement": "Lead with campus product work for this AI PM role.",
        "recommended_experience_order": [str(real), str(ghost)],
        "experience_guidance": [
            {
                "experience_id": str(real),
                "role_in_story": "Primary proof",
                "what_to_highlight": ["ownership"],
                "what_to_avoid": ["invent"],
                "target_capabilities": ["PM"],
                "evidence_refs": [],
                "interview_risk_notes": [],
            },
            {
                "experience_id": str(ghost),
                "role_in_story": "Ghost education id",
                "what_to_highlight": [],
                "what_to_avoid": [],
                "target_capabilities": [],
                "evidence_refs": [],
                "interview_risk_notes": [],
            },
        ],
    })
    pruned, dropped = _prune_resume_strategy(strategy, {real})
    assert str(ghost) in dropped
    assert pruned.recommended_experience_order == [real]
    assert len(pruned.experience_guidance) == 1
    assert pruned.experience_guidance[0].experience_id == real


def test_ensure_strategy_repairs_when_all_ghosts():
    real = uuid4()
    ghost = uuid4()
    strategy = ResumeStrategyPayload.model_validate({
        "positioning_statement": "Lead with confirmed experiences only.",
        "recommended_experience_order": [str(ghost)],
        "experience_guidance": [{
            "experience_id": str(ghost),
            "role_in_story": "Ghost",
            "what_to_highlight": [],
            "what_to_avoid": [],
            "target_capabilities": [],
            "evidence_refs": [],
            "interview_risk_notes": [],
        }],
    })
    selections = ExperienceSelectionPayload.model_validate({
        "selections": [{
            "experience_id": str(real),
            "decision": "KEEP_AND_HIGHLIGHT",
            "why": "Campus assistant proves PM sense",
            "related_capabilities": ["PM"],
            "supporting_evidence_refs": [],
            "confidence": 0.8,
        }]
    })
    out = _ensure_strategy_grounded(
        strategy,
        profile=_Profile([real]),
        selections=selections,
        extraction=_extraction(),
        what_matters=_wm(),
    )
    assert out.recommended_experience_order == [real]
    assert out.experience_guidance[0].experience_id == real


def test_ensure_strategy_422_when_no_keep_and_all_ghosts():
    ghost = uuid4()
    strategy = ResumeStrategyPayload.model_validate({
        "positioning_statement": "Lead with confirmed experiences only.",
        "recommended_experience_order": [str(ghost)],
        "experience_guidance": [],
    })
    selections = ExperienceSelectionPayload.model_validate({"selections": []})
    with pytest.raises(HTTPException) as caught:
        _ensure_strategy_grounded(
            strategy,
            profile=_Profile([]),
            selections=selections,
            extraction=_extraction(),
            what_matters=_wm(),
        )
    assert caught.value.status_code == 422
    assert "不存在" in str(caught.value.detail) or "经历" in str(caught.value.detail)


def test_select_top_claims_does_not_fallback_to_bare_unsupported():
    claims = [
        {
            "claim": "主导具身智能相机路线图",
            "current_text": None,
            "suggested_text": None,
            "reason": "JD gap",
            "jd_relevance": "JD",
            "matched_capabilities": [],
            "evidence_refs": [],
            "readiness_status": "UNSUPPORTED",
            "confidence": 0.9,
            "risk_reason": "no evidence",
            "attack_surface": [],
        }
    ]
    selected = OpenAIClaimAnalysisProvider._select_top_claims(claims, limit=3)
    assert selected == []
