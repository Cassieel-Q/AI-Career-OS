from sqlalchemy import select

from app import models


def test_mission_versions_and_outcome_are_profile_scoped(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    target_a = models.TargetJob(
        profile_id=persisted_profile.id,
        raw_text="Synthetic Baidu AI PM JD",
        content_hash="a" * 64,
        requirements=[{"id": "req-a", "name": "evaluation", "evidence_text": "evaluation"}],
        capabilities=[{"name": "AI evaluation", "summary": "evaluation", "atomic_requirement_ids": ["req-a"]}],
    )
    target_b = models.TargetJob(
        profile_id=persisted_profile.id,
        raw_text="Synthetic Xiaohongshu AI PM JD",
        content_hash="b" * 64,
        requirements=[{"id": "req-b", "name": "experimentation", "evidence_text": "experimentation"}],
        capabilities=[],
    )
    db_session.add_all([target_a, target_b])
    db_session.flush()
    mission_a = models.JobMission(
        profile_id=persisted_profile.id,
        target_job_id=target_a.id,
        display_name="Baidu AI PM",
        company="Baidu",
        role="AI Product Manager",
        role_family="AI_PRODUCT",
        seniority="MID",
        status="RESUME_PREP",
        parsed_jd={"requirements": target_a.requirements},
        what_matters={"core_capabilities": ["AI evaluation"]},
    )
    mission_b = models.JobMission(
        profile_id=persisted_profile.id,
        target_job_id=target_b.id,
        display_name="Xiaohongshu AI PM",
        company="Xiaohongshu",
        role="AI Product Manager",
        role_family="AI_PRODUCT",
        seniority="MID",
        status="DRAFT",
    )
    db_session.add_all([mission_a, mission_b])
    db_session.flush()
    resume_v1 = models.TargetResume(
        mission_id=mission_a.id,
        version=1,
        status="DRAFT",
        positioning_statement="Evidence-led AI product operator",
        recommended_experience_order=[str(persisted_profile.experiences[0].id)],
    )
    db_session.add(resume_v1)
    db_session.flush()
    db_session.add(
        models.TargetResumeBullet(
            target_resume_id=resume_v1.id,
            source_experience_id=persisted_profile.experiences[0].id,
            original_text="Research Assistant",
            suggested_text="Mapped an evaluation workflow",
            reason="Directly addresses the JD capability",
            jd_refs=["req-a"],
            evidence_refs=[str(persisted_profile.experiences[0].id)],
            resume_skill_refs=["ACTION_METHOD_RESULT"],
            risk_flags=["needs_artifact"],
            status="SUGGESTED",
        )
    )
    db_session.add(
        models.InterviewOutcome(
            mission_id=mission_a.id,
            application_status="INTERVIEWING",
            interview_round="ONSITE",
            questions_asked=["How did you evaluate quality?"],
            where_struggled="Metric ownership",
            interviewer_feedback="Synthetic feedback",
            notes="Demo only",
        )
    )
    db_session.commit()

    loaded = db_session.scalar(select(models.JobMission).where(models.JobMission.id == mission_a.id))
    assert loaded is not None
    assert loaded.target_job.id == target_a.id
    assert loaded.target_resumes[0].version == 1
    assert loaded.target_resumes[0].bullets[0].jd_refs == ["req-a"]
    assert loaded.outcomes[0].interview_round == "ONSITE"
    assert mission_b.target_job_id != loaded.target_job_id

    # Explicit multi-mission isolation: Baidu artifacts must not appear on Xiaohongshu mission.
    other = db_session.scalar(select(models.JobMission).where(models.JobMission.id == mission_b.id))
    assert other is not None
    assert list(other.target_resumes) == []
    assert list(other.outcomes) == []
    assert all(resume.mission_id == mission_a.id for resume in loaded.target_resumes)

