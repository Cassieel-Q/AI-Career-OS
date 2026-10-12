"""岗位解析降级在「重新读取」时也必须可见。

背景：`create_mission` 软失败时会带 `analysis_error` 返回，但那个字段不落库；
页面刷新后重新 GET 就只剩一个空的 `what_matters`，用户看到半空结果却没有任何
「重新解析」入口（见链路测试报告 §5.5）。这里锁住读取时重新推导的行为。
"""

from sqlalchemy.orm import Session

from app import models, mission_service


def _mission_with_what_matters(db: Session, profile_id, what_matters: dict) -> models.JobMission:
    target_job = models.TargetJob(
        profile_id=profile_id,
        raw_text="Acme Labs 招聘 AI 产品实习生，要求熟悉 RAG 与评测体系。",
        content_hash=mission_service.content_hash("degradation-fixture"),
        status="CURRENT",
    )
    db.add(target_job)
    db.flush()
    mission = models.JobMission(
        profile_id=profile_id,
        target_job_id=target_job.id,
        display_name="Acme Labs — AI Product Manager Intern",
        company="Acme Labs",
        role="AI Product Manager Intern",
        status="DRAFT",
        what_matters=what_matters,
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def test_empty_what_matters_reads_back_as_degraded(db_session: Session, persisted_profile) -> None:
    mission = _mission_with_what_matters(db_session, persisted_profile.id, {})
    payload = mission_service._mission_read(mission)

    assert "jd_analysis_unavailable" in payload["warnings"]
    assert payload["analysis_error"] is not None
    assert payload["analysis_error"]["type"] == "partial_jd_analysis"


def test_soft_what_matters_shape_is_detected(db_session: Session, persisted_profile) -> None:
    soft = {
        "core_capabilities": [],
        "high_importance_requirements": [],
        "confidence": 0.0,
    }
    mission = _mission_with_what_matters(db_session, persisted_profile.id, soft)
    payload = mission_service._mission_read(mission)

    assert "jd_analysis_unavailable" in payload["warnings"]
    assert payload["analysis_error"] is not None


def test_analyzed_what_matters_is_not_flagged(db_session: Session, persisted_profile) -> None:
    mission = _mission_with_what_matters(
        db_session,
        persisted_profile.id,
        {"core_capabilities": ["需求分析", "RAG 评测"], "confidence": 0.7},
    )
    payload = mission_service._mission_read(mission)

    assert "jd_analysis_unavailable" not in payload["warnings"]
    assert payload["analysis_error"] is None
