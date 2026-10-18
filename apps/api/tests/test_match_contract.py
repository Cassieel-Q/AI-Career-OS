"""匹配一致性与版本过期（可信求职 v1.2 · Sprint B · 指令 2.1-2.5）。

九条验收：
1. 分数与建议一致（模型建议与分档冲突时丢弃模型建议）
2. 不满足硬性条件时正确提醒
3. 原简历修改后旧分析显示过期
4. JD 修改后旧分析显示过期
5. 仅调整界面样式（不改输入）不触发过期
6. 重新分析后生成新版本
7. 旧分析仍可查看（不后台替换）
8. 硬性缺口即使技能相关度高也展示
9. 不相关项目建议（软件岗不再被注入硬件草案）
"""

from __future__ import annotations

import pytest

from app import job_insight_provider as provider
from app import match_contract as contract
from app.job_insight_service import get_match_analysis
from app.mission_provider import hardware_jd_signals
from app.mission_schemas import JobExtractionPayload


# ---------------------------------------------------------------------------
# 1. 分档与建议同源
# ---------------------------------------------------------------------------


def test_grade_is_derived_from_score_only() -> None:
    assert contract.grade_for_score(78) == "strong"
    assert contract.grade_for_score(70) == "strong"
    assert contract.grade_for_score(69) == "maybe"
    assert contract.grade_for_score(40) == "maybe"
    assert contract.grade_for_score(39) == "weak"


@pytest.mark.parametrize(
    "score,conflicting_advice",
    [
        (78, "建议先换更匹配的岗位。"),
        (85, "当前不建议投递。"),
        (72, "暂不投递，先补强经历。"),
    ],
)
def test_contradicting_model_advice_is_dropped(score: int, conflicting_advice: str) -> None:
    """P02：78 分「值得投递」却配一句「建议先换岗位」——这种组合不允许出现。"""
    result = contract.build_match_result(
        score=score,
        reasons=["命中 SQL"],
        gaps=[],
        model_advice=conflicting_advice,
        source="LLM",
        resume_text="熟练 SQL 建模",
        jd_text="要求 SQL 建模",
        requirement_names=["SQL 建模"],
    )
    assert result["grade"] == "strong"
    assert result["grade_label"] == "值得投递"
    assert result["recommendation"] == contract.RECOMMENDATION_BY_GRADE["strong"]
    assert "换更匹配" not in result["recommendation"]
    assert result["model_advice_dropped"] is True


def test_consistent_model_advice_is_kept() -> None:
    advice = "匹配度不错，可以准备投递，并重点准备 SQL 口径问题。"
    result = contract.build_match_result(
        score=80,
        reasons=["命中 SQL"],
        gaps=[],
        model_advice=advice,
        source="LLM",
        resume_text="熟练 SQL",
        jd_text="要求 SQL",
        requirement_names=["SQL"],
    )
    assert result["recommendation"] == advice
    assert result["model_advice_dropped"] is False


def test_low_score_never_shows_go_ahead_advice() -> None:
    result = contract.build_match_result(
        score=30,
        reasons=[],
        gaps=["缺少用户增长经验"],
        model_advice="可以直接投递，问题不大。",
        source="LLM",
        resume_text="只会 Excel",
        jd_text="要求用户增长",
        requirement_names=["用户增长"],
    )
    assert result["grade"] == "weak"
    assert result["recommendation"] == contract.RECOMMENDATION_BY_GRADE["weak"]
    assert "可以直接投递" not in result["recommendation"]


def test_legacy_fields_mirror_the_single_contract() -> None:
    result = contract.build_match_result(
        score=55,
        reasons=["有原型经验"],
        gaps=["没有上线经验"],
        model_advice="补齐上线案例再投。",
        source="LLM",
        resume_text="完成 Figma 原型",
        jd_text="要求产品经验",
        requirement_names=["产品经验"],
    )
    assert result["verdict"] == result["grade"]
    assert result["verdict_label"] == result["grade_label"]
    assert result["advice"] == result["recommendation"]
    assert result["reasons"] == result["supporting_evidence"]


# ---------------------------------------------------------------------------
# 2. 硬性缺口
# ---------------------------------------------------------------------------


def test_blocking_gaps_cover_unmet_hard_requirements() -> None:
    parsed = {
        "requirements": [
            {"id": "r1", "text": "必须持有 CET-6 证书", "category": "MUST"},
            {"id": "r2", "text": "会用 Figma", "category": "NICE"},
        ]
    }
    gaps = contract.compute_blocking_gaps(resume_text="熟练使用 Figma 画原型", parsed_jd=parsed, what_matters=None)
    assert gaps == ["必须持有 CET-6 证书"]


def test_no_hard_markers_means_no_blocking_gaps() -> None:
    """识别不出硬性要求时保守处理：不把普通要求当成硬门槛。"""
    parsed = {"requirements": [{"id": "r1", "text": "会用 Figma", "category": "SKILL"}]}
    assert contract.compute_blocking_gaps(resume_text="不会 Figma", parsed_jd=parsed, what_matters=None) == []


def test_hard_requirement_already_covered_is_not_a_gap() -> None:
    parsed = {"requirements": [{"id": "r1", "text": "必须具备 SQL 建模能力", "category": "MUST"}]}
    gaps = contract.compute_blocking_gaps(resume_text="熟练使用 SQL 建模", parsed_jd=parsed, what_matters=None)
    assert gaps == []


def test_blocking_gaps_survive_high_skill_relevance() -> None:
    """技能相关度高也不能豁免硬性缺口。"""
    result = contract.build_match_result(
        score=82,
        reasons=["产品经验丰富", "原型能力强"],
        gaps=[],
        model_advice=None,
        source="LLM",
        resume_text="产品经验丰富，原型能力强",
        jd_text="必须具备日语 N1；要求产品经验",
        requirement_names=["产品经验", "必须具备日语 N1"],
        parsed_jd={"requirements": [{"text": "必须具备日语 N1", "category": "MUST"}]},
    )
    assert result["grade"] == "strong"
    assert result["blocking_gaps"] == ["必须具备日语 N1"]


# ---------------------------------------------------------------------------
# 3-7. 版本绑定与过期
# ---------------------------------------------------------------------------


def test_fingerprint_changes_when_resume_changes() -> None:
    first = contract.build_input_fingerprint(resume_text="A", jd_text="J", requirement_names=["R"])
    second = contract.build_input_fingerprint(resume_text="A2", jd_text="J", requirement_names=["R"])
    assert first["resume_hash"] != second["resume_hash"]
    assert first["jd_hash"] == second["jd_hash"]


def test_style_only_changes_do_not_invalidate() -> None:
    """只改界面样式（不改简历/JD/要求）不触发过期。"""
    base = contract.build_input_fingerprint(resume_text="同一份简历", jd_text="同一份 JD", requirement_names=["R"])
    payload = {"inputs": base, "generated_at": "2026-10-18T00:00:00Z", "score": 70}
    status = contract.stale_status(payload, base)
    assert status["stale"] is False
    assert status["reasons"] == []


def test_resume_edit_marks_result_stale() -> None:
    before = contract.build_input_fingerprint(resume_text="旧简历", jd_text="JD", requirement_names=["R"])
    after = contract.build_input_fingerprint(resume_text="新简历：新增一段实习", jd_text="JD", requirement_names=["R"])
    status = contract.stale_status({"inputs": before, "score": 70}, after)
    assert status["stale"] is True
    assert any("简历原文已经修改" in reason for reason in status["reasons"])


def test_jd_edit_marks_result_stale() -> None:
    before = contract.build_input_fingerprint(resume_text="简历", jd_text="旧 JD", requirement_names=["R"])
    after = contract.build_input_fingerprint(resume_text="简历", jd_text="新 JD：新增硬性要求", requirement_names=["R"])
    status = contract.stale_status({"inputs": before, "score": 70}, after)
    assert status["stale"] is True
    assert any("岗位描述已经修改" in reason for reason in status["reasons"])


def test_legacy_cache_without_fingerprint_is_conservatively_stale() -> None:
    status = contract.stale_status({"score": 70, "generated_at": "2026-10-01T00:00:00Z"}, {})
    assert status["stale"] is True


def test_cached_result_is_returned_untouched_with_a_stale_flag(monkeypatch, db_session, mission_factory) -> None:
    """只标记不替换：改了简历后旧分析仍然返回，但带过期提示。"""
    mission_id, profile_id = mission_factory
    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {"score": 80, "verdict": "strong", "reasons": ["命中 SQL"], "gaps": [], "advice": "可以投递。"},
    )
    first = get_match_analysis(db_session, mission_id, refresh=True)
    assert first["stale"]["stale"] is False
    assert first["score"] == 80

    from app import models

    profile = db_session.get(models.UserProfile, profile_id)
    profile.resume_text = "我在原简历基础上新增了一段 AI 产品实习经历。"
    db_session.commit()

    second = get_match_analysis(db_session, mission_id)
    assert second["score"] == 80, "旧分析不得被后台偷偷替换"
    assert second["stale"]["stale"] is True
    assert any("简历原文已经修改" in reason for reason in second["stale"]["reasons"])

    third = get_match_analysis(db_session, mission_id, refresh=True)
    assert third["stale"]["stale"] is False
    assert third["inputs"]["resume_hash"] != first["inputs"]["resume_hash"]


def test_refresh_keeps_previous_result_readable(monkeypatch, db_session, mission_factory) -> None:
    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {"score": 50, "verdict": "maybe", "reasons": ["部分命中"], "gaps": ["缺结果"], "advice": "补齐。"},
    )
    mission_id, _profile_id = mission_factory
    first = get_match_analysis(db_session, mission_id, refresh=True)
    second = get_match_analysis(db_session, mission_id, refresh=True)
    assert first["generated_at"] <= second["generated_at"]
    assert second["analysis_version"] == contract.MATCH_ANALYSIS_VERSION
    assert second["rule_version"] == contract.RULE_VERSION


# ---------------------------------------------------------------------------
# 9. 不相关项目建议（P04）
# ---------------------------------------------------------------------------


def _extraction(**overrides: object) -> JobExtractionPayload:
    base = {
        "company": "Acme",
        "role": "AI 产品经理",
        "role_family": "PRODUCT",
        "seniority": "INTERN",
        "responsibilities": ["负责需求分析与原型"],
        "requirements": [],
        "preferred_requirements": [],
        "capabilities": ["需求分析", "数据分析"],
        "keywords": ["product", "产品", "AI"],
    }
    base.update(overrides)
    return JobExtractionPayload.model_validate(base)


def test_software_product_role_has_no_hardware_signals() -> None:
    """「product / 产品」是通用词，不能当作硬件要求。"""
    assert hardware_jd_signals(_extraction()) == []


def test_hardware_role_is_detected_by_specific_signals() -> None:
    hits = hardware_jd_signals(
        _extraction(role="智能硬件产品经理", capabilities=["传感器选型", "端侧推理"], keywords=["硬件"])
    )
    assert hits, "真正的硬件岗必须被识别到"
    assert any("智能硬件" in hit for hit in hits)


def test_hardware_draft_reason_cites_real_jd_fragments() -> None:
    hits = hardware_jd_signals(_extraction(capabilities=["传感器选型", "嵌入式方案"]))
    result = contract.build_match_result(
        score=60,
        reasons=[],
        gaps=[],
        model_advice=None,
        source="LLM",
        resume_text="产品实习",
        jd_text="需要传感器选型与嵌入式方案经验",
        requirement_names=hits,
    )
    assert result["inputs"]["requirement_count"] == len(hits)


# ---------------------------------------------------------------------------
# fixture：一个可用的岗位
# ---------------------------------------------------------------------------


@pytest.fixture
def mission_factory(client, persisted_profile):
    return _create_mission(client, persisted_profile)


def _create_mission(client, persisted_profile):
    from app.mission_provider import set_mission_provider
    from app.mission_schemas import JobExtractionPayload as Payload, WhatMattersPayload

    class _Stub:
        def parse_jd(self, raw_text):
            return Payload.model_validate(
                {
                    "company": "Acme",
                    "role": "数据产品经理",
                    "role_family": "PRODUCT",
                    "seniority": "MID",
                    "responsibilities": ["负责数据看板"],
                    "requirements": [{"id": "req-1", "text": "SQL 建模", "category": "SKILL", "evidence_text": "熟练使用 SQL"}],
                    "preferred_requirements": [],
                    "capabilities": ["SQL 建模"],
                    "keywords": ["SQL"],
                }
            )

        def build_what_matters(self, **_kwargs):
            return WhatMattersPayload.model_validate(
                {
                    "core_capabilities": [{"name": "SQL 建模", "why": "JD 明确要求", "evidence_refs": ["req-1"]}],
                    "high_importance_requirements": [],
                    "evidence_expected": [],
                    "likely_success_signals": [],
                    "bonus_capabilities": [],
                    "potential_interview_focus": [],
                    "confidence": 0.8,
                    "jd_evidence_refs": ["req-1"],
                }
            )

    set_mission_provider(_Stub())
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/job-missions",
        json={"raw_text": "Acme 数据产品经理：熟练使用 SQL 建模。"},
    )
    assert created.status_code == 201, created.text
    from uuid import UUID

    return UUID(created.json()["id"]), UUID(created.json()["profile_id"])
