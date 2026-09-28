# -*- coding: utf-8 -*-
"""retry_company_intel must persist JSON-safe dicts, not InterviewIntelResult."""
from __future__ import annotations

from app.interview_intelligence import InterviewIntelResult
from app.mission_intelligence import intel_records
from app.mission_service import _serialize_interview_intel


def test_serialize_interview_intel_converts_dataclass_results():
    raw = [
        InterviewIntelResult(
            skill_id="CURATED_BAIDU_AI_PRODUCT",
            name="Baidu curated",
            company_relevance="SAME_COMPANY",
            role_relevance="SAME_ROLE_FAMILY",
            competency="ai",
            source_count=3,
            recency="2023-10-20",
            confidence=0.9,
            source_refs=["https://www.nowcoder.com/discuss/1"],
            body="signals",
            provenance="CURATED",
        ),
        {
            "skill_id": "ALREADY_DICT",
            "name": "dict row",
            "company_relevance": "GENERIC",
            "provenance": "GENERIC_FALLBACK",
            "source_refs": ["generic-report"],
        },
    ]
    out = _serialize_interview_intel(raw)
    assert len(out) == 2
    assert all(isinstance(row, dict) for row in out)
    assert out[0]["skill_id"] == "CURATED_BAIDU_AI_PRODUCT"
    assert out[0]["company_relevance"] == "SAME_COMPANY"
    assert out[0]["provenance"] == "CURATED"
    assert "observed_label" in out[0]
    assert out[1]["skill_id"] == "ALREADY_DICT"


def test_intel_records_roundtrip_matches_serializer():
    item = InterviewIntelResult(
        skill_id="X",
        name="n",
        company_relevance="SAME_COMPANY",
        role_relevance="RELATED_ROLE",
        competency="c",
        source_count=1,
        recency=None,
        confidence=0.5,
        source_refs=[],
        body="b",
        provenance="CURATED",
    )
    assert _serialize_interview_intel([item]) == intel_records([item])
