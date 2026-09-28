"""Interview pack cites only real 面经 (skill_id/source_refs); honest empty note; no internal tags.

Fixtures use obviously fake companies/URLs (FakeCo / OtherCo / example.invalid).
"""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.interview_pack_intel import (  # noqa: E402
    NO_REAL_INTEL_NOTE,
    annotate_topics,
    classify_intel,
    is_real_item,
    item_refs,
    source_company,
    topic_intel,
)

HEADER = "在已整理的 2 条相关面经中观察到以下信号（CURATED，非合成演示）。"


def _body(focus: list[str], questions: list[str]) -> str:
    return "\n".join(
        [
            HEADER,
            "",
            "## Interviewer intent / focus",
            *[f"- {f} （来源面经 9001）" for f in focus],
            "- 未提及 （来源面经 9002）",
            "",
            "## Question patterns",
            *[f"- {q} [FAKE_TAG]" for q in questions],
            "",
            "## Weak answer patterns to avoid",
            "- template line",
        ]
    )


FAKECO_REAL = {
    "skill_id": "CURATED_FAKECO_AI_PRODUCT",
    "name": "FakeCo curated AI_PRODUCT interview signals",
    "company_relevance": "SAME_COMPANY",
    "role_relevance": "SAME_ROLE_FAMILY",
    "competency": "RAG",
    "source_count": 2,
    "source_refs": ["https://example.invalid/fakeco/1", "https://example.invalid/fakeco/2"],
    "observed_label": "Observed in 2 curated company reports",
    "body": _body(["RAG 检索增强方案"], ["FAKE-Q1 讲讲你做的 RAG 召回怎么评估？", "FAKE-Q2 RAG 幻觉怎么兜底？", "FAKE-Q3 自我介绍"]),
    "provenance": "CURATED",
}
OTHERCO_ROLE_FAMILY = {
    "skill_id": "CURATED_OTHERCO_AI_PRODUCT",
    "name": "OtherCo curated AI_PRODUCT interview signals",
    "company_relevance": "ROLE_FAMILY",
    "role_relevance": "OTHER_COMPANY",
    "competency": "Agent",
    "source_count": 1,
    "source_refs": ["https://example.invalid/otherco/1"],
    "body": _body(["Agent 设计"], ["FAKE-Q9 Agent 和问答助手的区别？"]),
    "provenance": "CURATED",
}
DEMO_SAME_COMPANY = {
    "skill_id": "DEMO_FAKECO_AI_PM_METRICS",
    "name": "FakeCo AI PM metrics (demo)",
    "company_relevance": "SAME_COMPANY",
    "competency": "Agent",
    "source_refs": [],
    "body": _body(["Agent 指标"], ["FAKE-DEMO-Q Agent 成功率怎么定义？"]),
    "provenance": "SYNTHETIC_DEMO_ONLY",
}
GENERIC_SYNTHETIC = {
    "skill_id": "LLM_EVALUATION",
    "name": "LLM evaluation",
    "company_relevance": "GENERIC",
    "competency": "Agent",
    "source_refs": [],
    "body": _body(["Agent 评估"], ["FAKE-GEN-Q Agent 怎么评估？"]),
    "provenance": "SYNTHETIC_DEMO",
}
INTEL = [DEMO_SAME_COMPANY, GENERIC_SYNTHETIC, OTHERCO_ROLE_FAMILY, FAKECO_REAL]


def _user_text(topic: dict) -> str:
    parts = [str(topic.get("topic")), str(topic.get("why"))]
    parts += [str(x) for x in topic.get("evidence_expected") or []]
    parts += [str(x) for x in topic.get("question_patterns") or []]
    return "\n".join(parts)


def test_item_refs_use_skill_id_and_source_refs_then_legacy_keys():
    assert item_refs(FAKECO_REAL) == [
        "CURATED_FAKECO_AI_PRODUCT",
        "https://example.invalid/fakeco/1",
        "https://example.invalid/fakeco/2",
    ]
    assert item_refs({"id": "legacy-1", "source": "https://example.invalid/x", "ref": "legacy-1"}) == [
        "legacy-1",
        "https://example.invalid/x",
    ]


def test_synthetic_and_demo_items_are_never_real():
    assert is_real_item(FAKECO_REAL)
    assert not is_real_item(DEMO_SAME_COMPANY)
    assert not is_real_item(GENERIC_SYNTHETIC)
    assert not is_real_item({**FAKECO_REAL, "company_relevance": "SYNTHETIC_DEMO"})
    assert not is_real_item({"topic": "untraceable", "id": "x"})  # no source, no real provenance


def test_classify_same_company_vs_role_family_with_real_source_company():
    classified = classify_intel(INTEL, company="FakeCo")
    assert [i["skill_id"] for i in classified.same_company] == ["CURATED_FAKECO_AI_PRODUCT"]
    assert [i["skill_id"] for i in classified.role_family] == ["CURATED_OTHERCO_AI_PRODUCT"]
    assert source_company(OTHERCO_ROLE_FAMILY) == "OtherCo"
    assert source_company({"skill_id": "CURATED_OTHERCO_AI_PRODUCT", "role_family": "AI_PRODUCT"}) == "OTHERCO"
    # Mislabelled SAME_COMPANY from another company must not count as the target's write-up.
    wrong = {**OTHERCO_ROLE_FAMILY, "company_relevance": "SAME_COMPANY"}
    assert classify_intel([wrong], company="FakeCo").same_company == []
    # Unknown target company: nothing may be presented as 该公司真实面经.
    assert classify_intel(INTEL, company="UNKNOWN").same_company == []


def test_matching_topic_cites_real_refs_signals_and_questions():
    classified = classify_intel(INTEL, company="FakeCo")
    info = topic_intel("RAG 方案设计", classified=classified, company="FakeCo")
    assert info.intel_refs[0] == "CURATED_FAKECO_AI_PRODUCT"
    assert "https://example.invalid/fakeco/1" in info.intel_refs
    assert info.note.startswith("参考 FakeCo 真实面经（2 篇牛客面经）")
    assert "RAG 检索增强方案" in info.note
    assert "来源面经" not in info.note and "未提及" not in info.note
    assert info.questions == ["FAKE-Q1 讲讲你做的 RAG 召回怎么评估？", "FAKE-Q2 RAG 幻觉怎么兜底？"]
    assert "CURATED" not in info.note and "以下信号" not in info.note


def test_topic_without_same_company_intel_says_no_real_intel_and_labels_role_family_source():
    classified = classify_intel(INTEL, company="FakeCo")
    info = topic_intel("Agent 设计取舍", classified=classified, company="FakeCo")
    assert info.intel_refs == []
    assert info.note == NO_REAL_INTEL_NOTE
    assert info.questions == []  # never fill with synthetic / other-company questions as target intel
    assert info.reference_lines == ["同类岗位参考（来自 OtherCo 公司）：FAKE-Q9 Agent 和问答助手的区别？"]
    assert all("FakeCo" not in line for line in info.reference_lines)
    assert "CURATED_OTHERCO_AI_PRODUCT" in info.reference_refs
    joined = "\n".join([info.note, *info.reference_lines])
    assert "FAKE-DEMO-Q" not in joined and "FAKE-GEN-Q" not in joined


def test_annotate_topics_end_to_end_is_honest_and_tag_free():
    topics = [
        {
            "priority": "HIGH",
            "topic": "RAG 方案设计",
            "why": "来自面经（CURATED）",
            "capabilities": ["RAG"],
            "intel_refs": ["DEMO_FAKECO_AI_PM_METRICS", "LLM_EVALUATION"],
            "question_patterns": ["JD 推断问题 A"],
            "evidence_expected": [f"面经要点：{HEADER}", "高频问法：围绕 RAG 的场景题"],
        },
        {
            "priority": "MEDIUM",
            "topic": "Agent 设计取舍",
            "why": "JD 要求",
            "intel_refs": ["DEMO_FAKECO_AI_PM_METRICS"],
            "question_patterns": ["JD 推断问题 B"],
            "evidence_expected": [f"面经要点：{HEADER}"],
        },
        {"priority": "MEDIUM", "topic": "开场定位", "why": "通用", "question_patterns": [], "evidence_expected": []},
    ]
    out = annotate_topics(topics, INTEL, company="FakeCo")
    rag, agent, opening = out
    assert rag["intel_refs"][0] == "CURATED_FAKECO_AI_PRODUCT"
    assert not any(r.startswith(("DEMO_", "LLM_EVALUATION")) for t in out for r in t["intel_refs"])
    assert rag["question_patterns"][:2] == ["FAKE-Q1 讲讲你做的 RAG 召回怎么评估？", "FAKE-Q2 RAG 幻觉怎么兜底？"]
    assert "JD 推断问题 A" in rag["question_patterns"]
    assert agent["intel_refs"] == []
    assert agent["evidence_expected"][0] == NO_REAL_INTEL_NOTE
    assert agent["evidence_expected"][1].startswith("同类岗位参考（来自 OtherCo 公司）")
    assert agent["question_patterns"] == ["JD 推断问题 B"]
    assert opening["intel_refs"] == [] and opening["evidence_expected"] == [NO_REAL_INTEL_NOTE]
    for topic in out:
        text = _user_text(topic)
        assert "CURATED" not in text
        assert "以下信号" not in text
        assert "FAKE-DEMO-Q" not in text and "FAKE-GEN-Q" not in text
    # Idempotent: re-annotating does not stack notes.
    again = annotate_topics(out, INTEL, company="FakeCo")
    assert again == out


def test_other_company_and_synthetic_questions_are_stripped_from_topic_questions():
    topics = [
        {
            "priority": "HIGH",
            "topic": "开场定位",
            "why": "JD",
            "question_patterns": [
                "FAKE-Q9 Agent 和问答助手的区别？",
                "FAKE-DEMO-Q Agent 成功率怎么定义？",
                "JD 推断问题 C",
            ],
        }
    ]
    out = annotate_topics(topics, INTEL, company="FakeCo")
    assert out[0]["question_patterns"] == ["JD 推断问题 C"]
    assert out[0]["evidence_expected"][0] == NO_REAL_INTEL_NOTE


def test_no_intel_at_all_every_topic_gets_honest_note():
    out = annotate_topics([{"priority": "HIGH", "topic": "RAG", "why": "x"}], [DEMO_SAME_COMPANY], company="FakeCo")
    assert out[0]["intel_refs"] == []
    assert out[0]["evidence_expected"] == [NO_REAL_INTEL_NOTE]


def test_real_knowledge_packs_baidu_role_family_items_keep_their_own_company():
    """Uses the repo's real curated registry: Baidu items are same-company; fillers keep their source company."""
    from app.interview_intelligence import InterviewIntelRetriever

    results = InterviewIntelRetriever().retrieve(company="百度", role="AI产品经理", role_family="AI_PRODUCT")
    records = [
        {
            "skill_id": r.skill_id,
            "name": r.name,
            "company_relevance": r.company_relevance,
            "competency": r.competency,
            "source_refs": r.source_refs,
            "body": r.body,
            "provenance": r.provenance,
        }
        for r in results
    ]
    classified = classify_intel(records, company="百度")
    assert [i["skill_id"] for i in classified.same_company] == ["CURATED_BAIDU_AI_PRODUCT"]
    for item in classified.role_family:
        company = source_company(item)
        assert company and company.casefold() not in {"baidu", "百度"}
    out = annotate_topics([{"priority": "HIGH", "topic": "RAG 与 Agent", "why": "JD"}], records, company="百度")
    assert "CURATED_BAIDU_AI_PRODUCT" in out[0]["intel_refs"]
    assert any(ref.startswith("https://www.nowcoder.com/") for ref in out[0]["intel_refs"])
    assert "CURATED" not in _user_text(out[0])
    # Generic words alone (用户/设计) must not claim a Baidu write-up; long CJK topics need >=2 bigram hits.
    noisy = annotate_topics([{"priority": "MEDIUM", "topic": "开场定位与代表作经历", "why": "JD"}], records, company="百度")
    assert noisy[0]["intel_refs"] == []
    assert noisy[0]["evidence_expected"][0] == NO_REAL_INTEL_NOTE
    assert all("百度" not in line for line in noisy[0]["evidence_expected"][1:])
