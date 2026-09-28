from uuid import uuid4

from app.mission_intelligence import MissionIntelligenceService
from app.mission_schemas import (
    ExperienceSelectionPayload,
    JobExtractionPayload,
    WhatMattersPayload,
)


class StubMissionProvider:
    def parse_jd(self, raw_text):
        return JobExtractionPayload.model_validate({
            "company": "UNKNOWN",
            "role": "AI Product Manager",
            "role_family": "AI_PRODUCT",
            "seniority": "UNKNOWN",
            "location": None,
            "responsibilities": ["Design evaluation workflows"],
            "requirements": [{"id": "req-1", "text": "Evaluation", "category": "CAPABILITY", "evidence_text": "evaluation"}],
            "preferred_requirements": [],
            "capabilities": ["AI evaluation"],
            "keywords": ["evaluation"],
        })

    def build_what_matters(self, *, raw_text, extraction, interview_intel):
        return WhatMattersPayload.model_validate({
            "core_capabilities": [{"name": "AI evaluation", "why": "The JD states evaluation.", "evidence_refs": ["req-1"]}],
            "high_importance_requirements": [{"text": "Evaluation", "importance": "HIGH", "evidence_refs": ["req-1"]}],
            "evidence_expected": ["A reproducible evaluation artifact"],
            "likely_success_signals": ["Explains a rubric"],
            "bonus_capabilities": [],
            "potential_interview_focus": ["Evaluation tradeoffs"],
            "confidence": 0.8,
            "jd_evidence_refs": ["req-1"],
        })

    def select_experiences(self, **kwargs):
        return ExperienceSelectionPayload(selections=[])


def test_mission_service_combines_jd_analysis_with_ranked_intel():
    service = MissionIntelligenceService(provider=StubMissionProvider())

    extraction, what_matters, intel = service.analyze_jd("Evaluation JD")

    assert extraction.role == "AI Product Manager"
    assert what_matters.core_capabilities[0].evidence_refs == ["req-1"]
    assert isinstance(intel, list)

