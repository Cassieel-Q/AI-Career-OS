from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.derived_state import derived_state_fingerprint, invalidate_target_derived_state


def test_p0_models_persist_derived_chain(db_session, persisted_profile):
    exploration = models.RoleExploration(
        profile_id=persisted_profile.id,
        role_profile_version="v1",
        result={"role_profile_version": "v1", "items": []},
    )
    db_session.add(exploration)
    db_session.flush()
    target = models.TargetRole(
        profile_id=persisted_profile.id,
        role_code="AI_PRODUCT_MANAGER",
        role_profile_version="v1",
        role_exploration_id=exploration.id,
        selected_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(target)
    db_session.flush()
    profile = models.MarketProfile(
        target_role_id=target.id,
        sample_fingerprint=derived_state_fingerprint(target.id, []),
        sample_count=3,
        status="VALID",
    )
    db_session.add(profile)
    db_session.flush()
    requirement = models.MarketRequirement(
        market_profile_id=profile.id,
        name="Python",
        category="SKILL",
        occurrence_count=3,
        frequency_ratio=1.0,
        sort_order=1,
    )
    db_session.add(requirement)
    db_session.commit()

    loaded = db_session.scalar(select(models.MarketRequirement).where(models.MarketRequirement.name == "Python"))
    assert loaded is not None
    assert loaded.market_profile.status == "VALID"


def test_invalidation_marks_derived_state_without_changing_task_history(db_session):
    profile = models.UserProfile(status="CONFIRMED")
    db_session.add(profile)
    db_session.flush()
    exploration = models.RoleExploration(
        profile_id=profile.id,
        role_profile_version="v1",
        result={"role_profile_version": "v1", "items": []},
    )
    db_session.add(exploration)
    db_session.flush()
    target = models.TargetRole(
        profile_id=profile.id,
        role_code="AI_PRODUCT_MANAGER",
        role_profile_version="v1",
        role_exploration_id=exploration.id,
    )
    db_session.add(target)
    db_session.flush()
    market = models.MarketProfile(
        target_role_id=target.id,
        sample_fingerprint="old",
        sample_count=3,
        status="VALID",
    )
    db_session.add(market)
    db_session.flush()
    analysis = models.GapAnalysis(
        profile_id=profile.id,
        market_profile_id=market.id,
        profile_fingerprint="profile",
        status="VALID",
    )
    db_session.add(analysis)
    db_session.flush()
    roadmap = models.Roadmap(
        profile_id=profile.id,
        gap_analysis_id=analysis.id,
        revision=1,
        weekly_hours=5,
        priority_fingerprint="priority",
        status="VALID",
    )
    db_session.add(roadmap)
    db_session.flush()
    week = models.RoadmapWeek(roadmap_id=roadmap.id, week_number=1, objective="Learn", measurable_outcome="Ship")
    db_session.add(week)
    db_session.flush()
    task = models.RoadmapTask(
        roadmap_week_id=week.id,
        title="Build a small feature",
        objective="Build",
        estimated_minutes=60,
        completion_criteria="A demo exists",
        status="DONE",
        sort_order=1,
    )
    db_session.add(task)
    db_session.commit()

    invalidate_target_derived_state(db_session, target.id)
    db_session.commit()

    assert market.status == "INVALIDATED"
    assert analysis.status == "INVALIDATED"
    assert roadmap.status == "INVALIDATED"
    assert task.status == "DONE"
