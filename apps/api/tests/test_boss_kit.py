"""M3 · BOSS 投递准备包：原岗位链接、话术生成与保存、标记已投递、跟进提醒。

不触碰用户真实数据；岗位与档案都在内存测试库里现建。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import models


def _mission_with_source(db_session, *, source_url: str = "https://www.zhipin.com/job_detail/sample.html") -> models.JobMission:
    profile = models.UserProfile(status="DRAFT", full_name="示例同学")
    db_session.add(profile)
    db_session.flush()
    target_job = models.TargetJob(
        profile_id=profile.id,
        raw_text="公司：示例科技有限公司\n职位：AI产品经理实习\n地点：杭州\n\n岗位描述：负责 AI 产品需求调研。",
        source_url=source_url,
        content_hash="boss-kit-sample-hash",
        status="CURRENT",
    )
    db_session.add(target_job)
    db_session.flush()
    mission = models.JobMission(
        profile_id=profile.id,
        target_job_id=target_job.id,
        display_name="示例科技有限公司 · AI产品经理实习",
        company="示例科技有限公司",
        role="AI产品经理实习",
        location="杭州",
        status="DRAFT",
    )
    db_session.add(mission)
    db_session.commit()
    db_session.refresh(mission)
    return mission


def test_boss_kit_exposes_original_job_link(client: TestClient, db_session):
    mission = _mission_with_source(db_session)
    kit = client.get(f"/api/v1/missions/{mission.id}/boss-kit").json()
    assert kit["source_url"] == "https://www.zhipin.com/job_detail/sample.html"
    assert kit["can_open_original"] is True
    assert kit["application"] is None
    assert kit["resume"]["confirmed"] is False


def test_greeting_is_generated_from_real_fields_and_not_sent(client: TestClient, db_session):
    mission = _mission_with_source(db_session)
    created = client.post(f"/api/v1/missions/{mission.id}/boss-kit/greeting").json()
    assert created["short"].startswith("您好，我是示例同学")
    assert "示例科技有限公司" in created["long"]
    assert "AI产品经理实习" in created["short"]
    assert "不会自动发送" in created["note"]
    # 没有已确认经历时如实标注，不编造
    assert created["grounded_on"]["highlight_count"] == 0


def test_edited_greeting_can_be_saved(client: TestClient, db_session):
    mission = _mission_with_source(db_session)
    client.post(f"/api/v1/missions/{mission.id}/boss-kit/greeting")
    saved = client.patch(
        f"/api/v1/missions/{mission.id}/boss-kit/greeting",
        json={"short": "您好，我是示例同学，想应聘 AI 产品经理实习。", "long": "详细版由我自己改写。"},
    ).json()
    assert saved["short"] == "您好，我是示例同学，想应聘 AI 产品经理实习。"
    kit = client.get(f"/api/v1/missions/{mission.id}/boss-kit").json()
    assert kit["greeting"]["long"] == "详细版由我自己改写。"


def test_mark_applied_records_status_and_date(client: TestClient, db_session):
    mission = _mission_with_source(db_session)
    result = client.post(f"/api/v1/missions/{mission.id}/boss-kit/mark-applied", json={"channel": "BOSS 直聘"}).json()
    assert result["application"]["status"] == "APPLIED"
    assert result["application"]["applied_at"] is not None
    # 没有已确认简历 → 如实提示，但不阻断「已投递」这件事
    assert result["warning"]


def test_mark_applied_does_not_replace_existing_resume_binding(client: TestClient, db_session):
    """已经绑定过简历版本的记录，再次标记已投递不会换版本。"""
    mission = _mission_with_source(db_session)
    resume = models.TargetResume(mission_id=mission.id, status="CONFIRMED", version=1)
    db_session.add(resume)
    db_session.flush()

    application = models.JobApplication(
        profile_id=mission.profile_id,
        mission_id=mission.id,
        company=mission.company,
        role=mission.role,
        location=mission.location,
        channel="BOSS 直聘",
        status="PENDING",
        resume_version_id=resume.id,
    )
    db_session.add(application)
    db_session.commit()

    result = client.post(f"/api/v1/missions/{mission.id}/boss-kit/mark-applied", json={}).json()
    assert result["application"]["status"] == "APPLIED"
    assert result["application"]["resume_version_id"] == str(resume.id)


def test_reminder_defaults_to_company_follow_up(client: TestClient, db_session):
    mission = _mission_with_source(db_session)
    created = client.post(f"/api/v1/missions/{mission.id}/boss-kit/reminder", json={}).json()
    assert "示例科技有限公司" in created["title"]
    assert "AI产品经理实习" in created["title"]
    assert created["due_at"] is not None


def test_boss_kit_404_for_unknown_mission(client: TestClient):
    assert client.get(f"/api/v1/missions/{uuid4()}/boss-kit").status_code == 404


def test_candidate_import_carries_source_url_into_mission(client: TestClient, db_session):
    """导入正式岗位时原始链接不能丢，否则「打开 BOSS 岗位」没有地址。"""
    from app import candidate_job_service as svc

    profile = models.UserProfile(status="DRAFT")
    db_session.add(profile)
    db_session.flush()
    rows = svc.parse_candidates(
        db_session,
        profile.id,
        "公司：示例科技有限公司\n岗位：AI产品经理实习\n地点：杭州\n岗位描述：负责 AI 产品需求调研与方案设计，输出 PRD。",
        source_kind="PASTE",
    )
    row = rows[0]
    row.company = "示例科技有限公司"
    row.role = "AI产品经理实习"
    row.source_url = "https://www.zhipin.com/job_detail/keep-me.html"
    db_session.commit()

    imported = svc.import_candidate(db_session, row.id, profile.id)
    mission_id = imported["mission_id"]
    kit = client.get(f"/api/v1/missions/{mission_id}/boss-kit").json()
    assert kit["source_url"] == "https://www.zhipin.com/job_detail/keep-me.html"
