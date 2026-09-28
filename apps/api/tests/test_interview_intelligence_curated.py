from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.company_aliases import canonical_company
from app.interview_intelligence import InterviewIntelRetriever
from app.mission_intelligence import bounded_intel_records
from app.knowledge_packs import load_default_registry


def test_canonical_company_aliases():
    assert canonical_company("百度") == "baidu"
    assert canonical_company("Baidu") == "baidu"
    assert canonical_company("字节跳动") == "bytedance"
    assert canonical_company("ByteDance") == "bytedance"


def test_registry_loads_curated_and_synthetic():
    reg = load_default_registry()
    interview = reg.by_kind("interview_skill")
    assert interview, "expected interview skills"
    provenances = {p.provenance for p in interview}
    assert any("CURATED" in (p or "") for p in provenances)
    assert any("SYNTHETIC" in (p or "").upper() for p in provenances)


def test_baidu_retrieval_prefers_same_company():
    items = InterviewIntelRetriever().retrieve(company="百度", role="AI Product Manager", role_family="AI_PRODUCT", limit=8)
    assert items
    assert items[0].company_relevance == "SAME_COMPANY"
    # curated baidu pack should appear
    ids = [i.skill_id for i in items]
    assert any("BAIDU" in i.upper() or "baidu" in i.lower() for i in ids)


def test_bytedance_retrieval():
    items = InterviewIntelRetriever().retrieve(company="ByteDance", role="AI Product Manager", role_family="AI_PRODUCT", limit=8)
    assert items
    assert items[0].company_relevance == "SAME_COMPANY"


def test_bounded_intel_records_exposes_curated_question_patterns_without_full_body():
    records = bounded_intel_records(
        [
            {
                "skill_id": "CURATED_BAIDU_AI_PRODUCT",
                "name": "Baidu curated AI_PRODUCT interview signals",
                "company_relevance": "SAME_COMPANY",
                "source_refs": ["https://example.test/niuke"],
                "provenance": "CURATED",
                "body": "## Interviewer intent / focus\n- 项目深挖\n\n## Question patterns\n- 你如何定义测试指标？ [项目]\n- 结果如何验证？ [结果]",
            }
        ]
    )

    assert records == [
        {
            "skill_id": "CURATED_BAIDU_AI_PRODUCT",
            "name": "Baidu curated AI_PRODUCT interview signals",
            "company_relevance": "SAME_COMPANY",
            "source_refs": ["https://example.test/niuke"],
            "provenance": "CURATED",
            "focus": ["项目深挖"],
            "question_patterns": ["你如何定义测试指标？", "结果如何验证？"],
        }
    ]
