"""目标二 · 评测暴露问题的回归测试。

覆盖：经历四分类（服务类 OMIT / 关键经历不被误砍 / 无证据不硬高亮）、
must-have 与 nice-to-have 显式分类、面试包不泄漏 demo/CURATED 文案。
"""
from __future__ import annotations

from app.mission_provider import OpenAIMissionProvider
from app.mission_schemas import (
    JobExtractionPayload,
    RedTeamPayload,
    TargetResumePayload,
    WhatMattersPayload,
)


def _extraction(role: str, capabilities: list[str]) -> JobExtractionPayload:
    return JobExtractionPayload.model_validate(
        {
            "company": "示例公司",
            "role": role,
            "role_family": "GENERAL",
            "seniority": "INTERN",
            "requirements": [],
            "preferred_requirements": [],
            "capabilities": capabilities,
            "keywords": [],
        }
    )


def _matters(capabilities: list[str]) -> WhatMattersPayload:
    return WhatMattersPayload.model_validate(
        {
            "core_capabilities": [{"name": name, "why": "JD", "evidence_refs": []} for name in capabilities],
            "high_importance_requirements": [],
            "confidence": 0.7,
        }
    )


# ---------------------------------------------------------------------------
# 问题 1 · 不相关经历该砍却被高亮
# ---------------------------------------------------------------------------


def test_service_role_omitted_even_when_target_is_not_product() -> None:
    """收银/外卖等基础服务经历，即使目标岗位不是产品岗，也应 OMIT。"""
    decision, why, _, _ = OpenAIMissionProvider._heuristic_experience_decision(
        {"title": "外卖配送员", "organization": "某平台", "description": "负责取餐、配送与用户沟通"},
        extraction=_extraction("数据分析师", ["指标体系建设"]),
        what_matters=_matters(["指标体系建设"]),
    )
    assert decision == "OMIT"
    assert "建议保留" not in why and "重点展示" not in why


def test_service_role_omitted_for_product_target() -> None:
    decision, _, _, _ = OpenAIMissionProvider._heuristic_experience_decision(
        {"title": "咖啡师", "organization": "连锁咖啡", "description": "负责制作饮品与店内运营"},
        extraction=_extraction("AI产品经理", ["产品定义"]),
        what_matters=_matters(["产品定义"]),
    )
    assert decision == "OMIT"


# ---------------------------------------------------------------------------
# 问题 2 · 关键相关经历被误砍
# ---------------------------------------------------------------------------


def test_high_signal_experience_is_not_omitted() -> None:
    decision, _, _, confidence = OpenAIMissionProvider._heuristic_experience_decision(
        {
            "title": "内容创作 A/B 测试负责人",
            "description": "设计内容产品实验，负责创作者 A/B 测试与结果分析",
            "experience_type": "PROJECT",
        },
        extraction=_extraction("技术产品经理", ["实验设计"]),
        what_matters=_matters(["实验设计"]),
    )
    assert decision == "KEEP_AND_HIGHLIGHT"
    assert confidence >= 0.9


def test_neutral_experience_is_not_highlighted_by_default() -> None:
    """无强证据时不硬高亮（避免「整份简历全高亮」）。"""
    decision, _, _, _ = OpenAIMissionProvider._heuristic_experience_decision(
        {"title": "综合事务实习生", "organization": "某公司", "description": "协助团队完成日常工作"},
        extraction=_extraction("AI产品经理", ["产品定义"]),
        what_matters=_matters(["产品定义"]),
    )
    assert decision in {"DEEMPHASIZE", "OMIT"}


# ---------------------------------------------------------------------------
# 问题 4 · must-have / nice-to-have 显式分类
# ---------------------------------------------------------------------------


def test_requirement_category_marks_nice_to_have() -> None:
    row = OpenAIMissionProvider._normalize_jd_requirement(
        {"text": "熟悉 SQL 者优先", "evidence_text": "熟悉 SQL 者优先"}, idx=0
    )
    assert row is not None
    assert row["category"] == "nice_to_have"


def test_requirement_category_marks_must_have() -> None:
    row = OpenAIMissionProvider._normalize_jd_requirement("必须掌握 Python 数据处理", idx=0)
    assert row is not None
    assert row["category"] == "must_have"


def test_education_requirement_stays_must_have() -> None:
    row = OpenAIMissionProvider._normalize_jd_requirement(
        {"text": "本科及以上学历", "category": "education"}, idx=0
    )
    assert row is not None
    assert row["category"] == "must_have"


# ---------------------------------------------------------------------------
# 问题 5 · 面试包不得泄漏 demo / CURATED 文案
# ---------------------------------------------------------------------------


def test_interview_pack_fallback_scrubs_curated_headers_and_drops_synthetic() -> None:
    pack = OpenAIMissionProvider._interview_pack_fallback(
        extraction=_extraction("AI产品经理", ["产品定义"]),
        what_matters=_matters(["产品定义"]),
        interview_intel=[
            {
                "id": "SYNTHETIC_DEMO_1",
                "skill_id": "DEMO_PACK",
                "name": "Synthetic demo pack",
                "topic": "Synthetic demo topic",
                "provenance": "SYNTHETIC_DEMO",
            },
            {
                "id": "curated-1",
                "skill_id": "CURATED_EXAMPLE_FAMILY",
                "name": "示例面经",
                "topic": "用户增长（CURATED，非合成演示）",
                "why": "在已整理的 12 条相关面经中观察到以下信号（CURATED，非合成演示）。",
                "source_refs": ["CURATED_EXAMPLE_FAMILY"],
            },
        ],
        target_resume=TargetResumePayload.model_validate({"positioning_statement": "面向目标岗位"}),
        red_team=RedTeamPayload.model_validate({"findings": []}),
    )
    blob = " ".join(
        f"{topic.topic} {topic.why}" for topic in pack.topics
    )
    assert "CURATED" not in blob
    assert "SYNTHETIC" not in blob.upper()
    assert "合成演示" not in blob
    assert "观察到以下信号" not in blob
