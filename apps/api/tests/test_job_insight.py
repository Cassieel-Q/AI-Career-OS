"""岗位洞察：岗位关键词分析 + 简历×岗位匹配度 + 简历原文读写。

用户反馈驱动的三件事：
1. 「准备度」原来只是 workflow_state 的固定映射，与简历无关 → 改为简历×岗位匹配度（模型分析）；
2. 岗位表格看不到岗位特征 → 增加 2~3 个岗位关键词；
3. 简历中心要能直接编辑简历原始文字。

测试策略：模型调用一律被打桩（monkeypatch ``_call_json``），既能验证 LLM 路径，
也能验证降级路径；路由测试走真实 DB（内存 SQLite）。
"""
from __future__ import annotations

import pytest

from app import job_insight_provider as provider
from app.mission_provider import set_mission_provider
from app.mission_schemas import JobExtractionPayload, WhatMattersPayload


# ---------------------------------------------------------------------------
# 打桩 provider：既能建岗位，也能模拟岗位洞察返回值
# ---------------------------------------------------------------------------


class StubMissionProvider:
    def parse_jd(self, raw_text):
        return JobExtractionPayload.model_validate(
            {
                "company": "Acme",
                "role": "数据产品经理",
                "role_family": "PRODUCT",
                "seniority": "MID",
                "location": "上海",
                "responsibilities": ["负责数据看板"],
                "requirements": [
                    {"id": "req-1", "text": "SQL 建模", "category": "SKILL", "evidence_text": "熟练使用 SQL"},
                    {"id": "req-2", "text": "用户增长", "category": "CAPABILITY", "evidence_text": "有用户增长经验"},
                ],
                "preferred_requirements": [],
                "capabilities": ["数据看板"],
                "keywords": ["SQL"],
            }
        )

    def build_what_matters(self, **kwargs):
        return WhatMattersPayload.model_validate(
            {
                "core_capabilities": [{"name": "SQL 建模", "why": "JD 明确要求", "evidence_refs": ["req-1"]}],
                "high_importance_requirements": [{"text": "用户增长", "importance": "HIGH", "evidence_refs": ["req-2"]}],
                "evidence_expected": ["看板截图"],
                "likely_success_signals": ["讲清指标体系"],
                "bonus_capabilities": [],
                "potential_interview_focus": ["口径定义"],
                "confidence": 0.8,
                "jd_evidence_refs": ["req-1", "req-2"],
            }
        )


@pytest.fixture
def mission_id(client, persisted_profile):
    set_mission_provider(StubMissionProvider())
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/job-missions",
        json={"raw_text": "Acme 数据产品经理：熟练使用 SQL 建模，有用户增长经验。"},
    )
    assert created.status_code == 201, created.text
    set_mission_provider(None)
    return created.json()["id"], created.json()["profile_id"]


# ---------------------------------------------------------------------------
# 1. 纯逻辑：关键词
# ---------------------------------------------------------------------------


def test_local_keywords_prefer_requirement_names_and_cap_at_three():
    from app.job_insight_provider import local_job_keywords

    words = local_job_keywords(
        role="数据产品经理",
        requirement_names=["SQL 建模", "用户增长", "指标体系", "数据看板"],
        jd_text="",
    )

    assert words == ["SQL 建模", "用户增长", "指标体系"]


def test_local_keywords_dedupe_and_drop_chatter():
    from app.job_insight_provider import local_job_keywords

    words = local_job_keywords(
        role="运营",
        requirement_names=["用户增长", "用户增长", "负责", "  "],
        jd_text="",
    )

    assert words == ["用户增长"]


def test_keywords_fall_back_to_local_rule_when_model_fails(monkeypatch):
    def boom(*_args, **_kwargs):
        raise provider.JobInsightError("model down")

    monkeypatch.setattr(provider, "_call_json", boom)

    result = provider.analyze_job_keywords(role="数据产品经理", requirement_names=["SQL 建模", "用户增长"])

    assert result["source"] == "LOCAL_RULE"
    assert len(result["keywords"]) == 2


def test_keywords_use_model_when_available(monkeypatch):
    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {"keywords": ["SQL 建模", "用户增长", "指标体系", "多余的"], "summary": "负责数据看板与增长。"},
    )

    result = provider.analyze_job_keywords(role="数据产品经理", requirement_names=["SQL 建模"])

    assert result["source"] == "LLM"
    assert result["keywords"] == ["SQL 建模", "用户增长", "指标体系"]
    assert result["summary"] == "负责数据看板与增长。"


def test_keywords_fall_back_when_model_returns_only_one(monkeypatch):
    monkeypatch.setattr(provider, "_call_json", lambda *_a, **_k: {"keywords": ["SQL 建模"]})

    result = provider.analyze_job_keywords(role="数据产品经理", requirement_names=["SQL 建模", "用户增长"])

    assert result["source"] == "LOCAL_RULE"
    assert result["keywords"] == ["SQL 建模", "用户增长"]


# ---------------------------------------------------------------------------
# 2. 纯逻辑：匹配度
# ---------------------------------------------------------------------------


def test_match_without_resume_is_weak_and_says_what_to_do():
    from app.job_insight_provider import local_job_match

    result = local_job_match(resume_text="", requirement_names=["SQL 建模"], has_resume=False)

    assert result["score"] == 0
    assert result["verdict"] == "weak"
    assert "简历" in result["advice"]


def test_match_scores_by_hit_ratio():
    from app.job_insight_provider import local_job_match

    result = local_job_match(
        resume_text="我在 Lab 用 SQL 建模 做过指标体系，带过用户增长项目。",
        requirement_names=["SQL 建模", "用户增长", "指标体系", "A/B 实验"],
    )

    assert result["verdict"] == "strong"
    assert 70 <= result["score"] <= 80
    assert any("A/B 实验" in gap for gap in result["gaps"])


def test_match_model_result_is_clamped_and_normalized(monkeypatch):
    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {"score": 180, "verdict": "NONSENSE", "reasons": ["命中 SQL"], "gaps": ["缺 A/B"], "advice": "补实验。"},
    )

    result = provider.analyze_job_match(
        role="数据产品经理",
        resume_text="我用 SQL 做过看板",
        requirement_names=["SQL 建模"],
    )

    assert result["source"] == "LLM"
    assert result["score"] == 100
    assert result["verdict"] == "strong"
    assert result["advice"] == "补实验。"


def test_verdict_is_derived_from_score_so_the_ui_cannot_contradict_itself(monkeypatch):
    """用户实测里出现过「72 分=值得投递」「75 分=先补齐再投」，展示上自相矛盾。

    现在 verdict 一律由 score 推导，模型只负责 reasons / gaps / advice。
    """
    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {"score": 75, "verdict": "weak", "reasons": ["命中"], "gaps": [], "advice": "可投。"},
    )

    result = provider.analyze_job_match(role="数据产品经理", resume_text="我用 SQL 做过看板", requirement_names=["SQL"])

    assert result["score"] == 75
    assert result["verdict"] == "strong"


def test_verdict_thresholds_are_stable():
    assert provider.verdict_for_score(70) == "strong"
    assert provider.verdict_for_score(69) == "maybe"
    assert provider.verdict_for_score(40) == "maybe"
    assert provider.verdict_for_score(39) == "weak"


def test_match_model_invalid_score_falls_back(monkeypatch):
    monkeypatch.setattr(provider, "_call_json", lambda *_a, **_k: {"score": "说不清", "verdict": "strong"})

    result = provider.analyze_job_match(
        role="数据产品经理",
        resume_text="我用 SQL 做过看板",
        requirement_names=["SQL 建模"],
    )

    assert result["source"] == "LOCAL_RULE"


# ---------------------------------------------------------------------------
# 3. 路由：岗位关键词
# ---------------------------------------------------------------------------


def test_job_analysis_route_caches_and_refreshes(client, mission_id, monkeypatch):
    calls: list[int] = []

    def fake_call(*_a, **_k):
        calls.append(1)
        return {"keywords": ["SQL 建模", "用户增长"], "summary": f"第 {len(calls)} 次"}

    monkeypatch.setattr(provider, "_call_json", fake_call)
    mid, _pid = mission_id

    first = client.get(f"/api/v1/job-missions/{mid}/job-analysis")
    assert first.status_code == 200, first.text
    assert first.json()["source"] == "LLM"
    assert first.json()["keywords"] == ["SQL 建模", "用户增长"]

    # 第二次读命中缓存，不再调模型
    second = client.get(f"/api/v1/job-missions/{mid}/job-analysis")
    assert second.json()["summary"] == "第 1 次"
    assert len(calls) == 1

    refreshed = client.post(f"/api/v1/job-missions/{mid}/job-analysis")
    assert refreshed.status_code == 200
    assert refreshed.json()["summary"] == "第 2 次"
    assert len(calls) == 2


def test_job_analysis_route_404_for_unknown_mission(client):
    response = client.get("/api/v1/job-missions/00000000-0000-0000-0000-0000000000ff/job-analysis")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4. 路由：匹配度
# ---------------------------------------------------------------------------


def test_match_analysis_route_uses_profile_resume_text(client, mission_id, monkeypatch, db_session):
    from app import models

    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {
            "score": 62,
            "verdict": "maybe",
            "reasons": ["简历里有 SQL 建模经历"],
            "gaps": ["缺少用户增长的结果数据"],
            "advice": "补一个增长数据再投。",
        },
    )
    mid, pid = mission_id
    profile = db_session.get(models.UserProfile, __import__("uuid").UUID(pid))
    profile.resume_text = "3 年数据产品经验，负责 SQL 建模与指标体系搭建。"
    db_session.commit()

    response = client.get(f"/api/v1/job-missions/{mid}/match-analysis")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score"] == 62
    assert body["verdict"] == "maybe"
    assert body["verdict_label"] == "先补齐再投"
    assert body["resume_source"] == "EDITED_TEXT"
    assert body["reasons"] and body["gaps"]


def test_match_analysis_degrades_without_resume(client, mission_id, monkeypatch):
    def boom(*_args, **_kwargs):
        raise provider.JobInsightError("no model")

    monkeypatch.setattr(provider, "_call_json", boom)
    mid, _pid = mission_id

    body = client.get(f"/api/v1/job-missions/{mid}/match-analysis").json()

    assert body["source"] == "LOCAL_RULE"
    assert body["verdict"] in {"strong", "maybe", "weak"}
    assert body["resume_source"] in {"PROFILE_FACTS", "MISSING"}


# ---------------------------------------------------------------------------
# 5. 路由：简历原文读写
# ---------------------------------------------------------------------------


def test_resume_text_roundtrip(client, persisted_profile, db_session):
    pid = str(persisted_profile.id)

    initial = client.get(f"/api/v1/profiles/{pid}/resume-text")
    assert initial.status_code == 200, initial.text
    # 老档案没有原文时用已确认事实拼一段，不让工作台空白
    assert initial.json()["source"] == "PROFILE_FACTS"
    assert "Python" in initial.json()["raw_text"]

    saved = client.put(
        f"/api/v1/profiles/{pid}/resume-text",
        json={"raw_text": "我自己改过的简历原文：负责数据看板。"},
    )
    assert saved.status_code == 200
    assert saved.json()["source"] == "EDITED_TEXT"

    read_back = client.get(f"/api/v1/profiles/{pid}/resume-text")
    assert read_back.json()["raw_text"] == "我自己改过的简历原文：负责数据看板。"


def test_resume_text_put_empty_falls_back_to_facts(client, persisted_profile):
    pid = str(persisted_profile.id)
    client.put(f"/api/v1/profiles/{pid}/resume-text", json={"raw_text": "临时内容"})

    cleared = client.put(f"/api/v1/profiles/{pid}/resume-text", json={"raw_text": "   "})

    assert cleared.status_code == 200
    assert cleared.json()["source"] == "PROFILE_FACTS"


def test_resume_text_404_for_unknown_profile(client):
    response = client.get("/api/v1/profiles/00000000-0000-0000-0000-0000000000ee/resume-text")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 6. 岗位广场投影
# ---------------------------------------------------------------------------


def test_plaza_exposes_keywords_and_match_score(client, mission_id, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_call_json",
        lambda *_a, **_k: {"keywords": ["SQL 建模", "用户增长"], "summary": "做数据看板", "score": 75, "verdict": "strong", "reasons": ["命中"], "gaps": [], "advice": "可投。"},
    )
    mid, _pid = mission_id
    client.get(f"/api/v1/job-missions/{mid}/job-analysis")
    client.get(f"/api/v1/job-missions/{mid}/match-analysis")

    plaza = client.get("/api/v1/plaza")

    assert plaza.status_code == 200, plaza.text
    item = next(row for row in plaza.json()["items"] if row["mission_id"] == mid)
    assert item["keywords"] == ["SQL 建模", "用户增长"]
    # 75 分：结论由分数推导（≥70 → 值得投递），模型给的结论不参与展示口径
    assert item["match_score"] == 75
    assert item["match_verdict"] == "strong"
    assert item["match_verdict_label"] == "值得投递"


def test_plaza_without_analysis_is_empty_not_missing(client, mission_id):
    mid, _pid = mission_id

    plaza = client.get("/api/v1/plaza").json()

    item = next(row for row in plaza["items"] if row["mission_id"] == mid)
    assert item["keywords"] == []
    assert item["match_score"] is None
    assert item["match_source"] == "NONE"
