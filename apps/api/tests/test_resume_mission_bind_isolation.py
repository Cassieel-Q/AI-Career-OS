"""Per-mission resume bind must not silently overwrite shared Master Profile."""
from __future__ import annotations

from sqlalchemy import select

from app import models
from app.mission_schemas import ConfirmResumeSource, MissionCreate, ResumeSourceMode
from app.mission_service import (
    bind_mission_resume_from_extraction,
    confirm_resume_source,
    create_mission,
    _effective_profile_for_mission,
)
from app.profile_service import create_draft_profile
from app.resume_schemas import ResumeExtractionResult


def _extraction(title: str) -> ResumeExtractionResult:
    return ResumeExtractionResult(
        education=[{"institution": "Example University", "degree": "MSc", "evidence_text": "Example University MSc"}],
        skills=[{"name": "Python", "evidence_text": "Python"}],
        experiences=[{"title": title, "organization": "Lab", "evidence_text": f"{title} Lab"}],
        certifications=[],
    )


def test_two_missions_upload_do_not_silently_overwrite_master(db_session, persisted_profile):
    master_id = persisted_profile.id
    before = [row.title for row in persisted_profile.experiences]

    m1 = create_mission(
        db_session,
        master_id,
        MissionCreate(raw_text="Baidu AI PM: own evaluation workflows and quality evaluation for mission one."),
    )
    m2 = create_mission(
        db_session,
        master_id,
        MissionCreate(raw_text="ByteDance AI PM: own evaluation workflows and quality evaluation for mission two."),
    )

    bind_mission_resume_from_extraction(
        db_session,
        m1["id"],
        _extraction("Mission-One-Local"),
        mode="upload",
        update_master=False,
        filename="one.pdf",
    )
    bind_mission_resume_from_extraction(
        db_session,
        m2["id"],
        _extraction("Mission-Two-Local"),
        mode="paste",
        update_master=False,
    )

    master = db_session.get(models.UserProfile, master_id)
    assert [row.title for row in master.experiences] == before

    row1 = db_session.get(models.JobMission, m1["id"])
    row2 = db_session.get(models.JobMission, m2["id"])
    assert row1.resume_source["isolation"] == "mission_local"
    assert row2.resume_source["isolation"] == "mission_local"
    assert row1.resume_source["bound_profile_id"] != row2.resume_source["bound_profile_id"]
    assert row1.profile_id == master_id
    assert row2.profile_id == master_id

    eff1 = _effective_profile_for_mission(db_session, row1)
    eff2 = _effective_profile_for_mission(db_session, row2)
    assert [row.title for row in eff1.experiences] == ["Mission-One-Local"]
    assert [row.title for row in eff2.experiences] == ["Mission-Two-Local"]


def test_explicit_update_master_overwrites_shared_profile(db_session, persisted_profile):
    master_id = persisted_profile.id
    m1 = create_mission(
        db_session,
        master_id,
        MissionCreate(raw_text="Baidu AI PM: own evaluation workflows and quality evaluation."),
    )
    bind_mission_resume_from_extraction(
        db_session,
        m1["id"],
        _extraction("Master-Overwrite"),
        mode="upload",
        update_master=True,
        filename="master.pdf",
    )
    master = db_session.get(models.UserProfile, master_id)
    assert [row.title for row in master.experiences] == ["Master-Overwrite"]
    row1 = db_session.get(models.JobMission, m1["id"])
    assert row1.resume_source.get("isolation") == "shared_master"
    assert row1.resume_source.get("updated_master") is True


def test_confirm_upload_without_prior_bind_rejects_silent_overwrite(db_session, persisted_profile):
    m1 = create_mission(
        db_session,
        persisted_profile.id,
        MissionCreate(raw_text="Baidu AI PM: own evaluation workflows and quality evaluation."),
    )
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        confirm_resume_source(
            db_session,
            m1["id"],
            ConfirmResumeSource(mode=ResumeSourceMode.upload, update_master=False),
        )
    assert exc.value.status_code == 409
    assert "Master" in str(exc.value.detail) or "绑定" in str(exc.value.detail)


def test_profile_confirmation_for_mission_local_resume(db_session, persisted_profile):
    """Mission-local upload stays DRAFT until confirm; then claim analysis may proceed.

    Master must remain untouched (update_master=false / isolation=mission_local).
    """
    from uuid import UUID

    import pytest
    from fastapi import HTTPException

    import app.proof_service as proof_service
    from app.mission_service import generate_claims_for_mission
    from app.profile_service import confirm_profile, get_profile
    from app.proof_schemas import ClaimProposalPayload

    class _FakeClaims:
        def analyze(self, *, target_job, profile_facts):
            fact_id = profile_facts[0]["id"]
            return ClaimProposalPayload.model_validate(
                {
                    "claims": [
                        {
                            "claim": "Owns evaluation workflow for quality gates",
                            "current_text": "Mission-Local-Confirm Lab",
                            "suggested_text": None,
                            "reason": "Grounded in uploaded local experience",
                            "jd_relevance": "High",
                            "matched_capabilities": [
                                {
                                    "name": "LLM evaluation",
                                    "summary": "Evaluation design",
                                    "atomic_requirement_ids": [],
                                }
                            ],
                            "evidence_refs": [str(fact_id)],
                            "readiness_status": "WEAK_EVIDENCE",
                            "confidence": 0.55,
                            "risk_reason": "Needs sharper metrics",
                            "attack_surface": [
                                {
                                    "area": "AI",
                                    "risk": "Explain evaluation design",
                                    "evidence_refs": [str(fact_id)],
                                }
                            ],
                        }
                    ]
                }
            )

    master_id = persisted_profile.id
    master_before = [row.title for row in persisted_profile.experiences]

    m1 = create_mission(
        db_session,
        master_id,
        MissionCreate(
            raw_text="Baidu AI PM: own evaluation workflows and quality evaluation for local confirm."
        ),
    )
    bound = bind_mission_resume_from_extraction(
        db_session,
        m1["id"],
        _extraction("Mission-Local-Confirm"),
        mode="upload",
        update_master=False,
        filename="local.pdf",
    )
    assert bound["isolation"] == "mission_local"
    bound_id = bound["bound_profile_id"]
    assert bound_id != str(master_id)

    local = get_profile(db_session, UUID(str(bound_id)))
    assert local.status == "DRAFT"

    with pytest.raises(HTTPException) as blocked:
        generate_claims_for_mission(db_session, m1["id"])
    assert blocked.value.status_code == 409
    assert "确认" in str(blocked.value.detail)

    confirmed = confirm_profile(db_session, UUID(str(bound_id)))
    assert confirmed.status == "CONFIRMED"

    master = db_session.get(models.UserProfile, master_id)
    assert [row.title for row in master.experiences] == master_before
    row = db_session.get(models.JobMission, m1["id"])
    assert row.resume_source["isolation"] == "mission_local"
    assert row.resume_source["bound_profile_id"] == bound_id

    original = proof_service.get_claim_analysis_provider
    proof_service.get_claim_analysis_provider = lambda: _FakeClaims()
    try:
        via_mission = generate_claims_for_mission(db_session, m1["id"])
    finally:
        proof_service.get_claim_analysis_provider = original

    assert via_mission.claims
    assert {str(c.profile_id) for c in via_mission.claims} == {str(bound_id)}

    master = db_session.get(models.UserProfile, master_id)
    assert [row.title for row in master.experiences] == master_before
    assert get_profile(db_session, UUID(str(bound_id))).status == "CONFIRMED"


def test_mission_local_does_not_mutate_master(db_session, persisted_profile):
    """Alias / keep: update_master=false must not mutate Master experiences."""
    test_two_missions_upload_do_not_silently_overwrite_master(db_session, persisted_profile)


def test_master_bind_promotes_draft_profile(db_session, persisted_profile):
    """Selecting Master as resume source promotes DRAFT Master → CONFIRMED when facts exist."""
    from app.mission_schemas import ConfirmResumeSource, ResumeSourceMode
    from app.mission_service import confirm_resume_source
    from app.profile_service import get_profile

    persisted_profile.status = "DRAFT"
    db_session.commit()

    m1 = create_mission(
        db_session,
        persisted_profile.id,
        MissionCreate(raw_text="Baidu AI PM: evaluation workflows for master confirm gate."),
    )
    confirmed = confirm_resume_source(
        db_session,
        m1["id"],
        ConfirmResumeSource(mode=ResumeSourceMode.master),
    )
    assert confirmed["resume_source"]["mode"] == "master"
    assert confirmed["resume_source"]["isolation"] == "shared_master"
    assert not (confirmed.get("resume_source") or {}).get("bound_profile_id")

    master = get_profile(db_session, persisted_profile.id)
    assert master.status == "CONFIRMED"


def test_looks_like_placeholder_helper():
    from types import SimpleNamespace
    from app.mission_service import _looks_like_placeholder_profile

    fake = SimpleNamespace(
        experiences=[
            SimpleNamespace(
                title="文职助理 / 运营助理",
                organization="XX信息咨询有限公司",
                description="台账",
                evidence_text="可能由 AI 生成",
            )
        ],
        education=[],
    )
    assert _looks_like_placeholder_profile(fake) is True
    real = SimpleNamespace(
        experiences=[
            SimpleNamespace(
                title="大连理工大学港口海岸工程竞赛",
                organization="大连理工大学",
                description="海洋资源综合利用",
                evidence_text=None,
            )
        ],
        education=[SimpleNamespace(institution="大连理工大学", field_of_study="港口航道")],
    )
    assert _looks_like_placeholder_profile(real) is False


def test_master_bind_rejects_placeholder_template(db_session, persisted_profile):
    """Master bind must fail loudly when shared archive is XX/文职 placeholder."""
    import uuid
    import pytest
    from fastapi import HTTPException
    from app import models
    from app.mission_schemas import ConfirmResumeSource, MissionCreate, ResumeSourceMode
    from app.mission_service import confirm_resume_source

    master = persisted_profile
    for row in list(master.experiences or []):
        db_session.delete(row)
    db_session.commit()
    db_session.refresh(master)

    placeholder = models.Experience(
        id=uuid.uuid4(),
        profile_id=master.id,
        title="文职助理 / 运营助理",
        organization="XX信息咨询有限公司",
        dates="2024.07-2024.10",
        description="文件录入",
        evidence_text="XX信息咨询有限公司 岗位：文职助理 / 运营助理 （注：部分内容可能由 AI 生成）",
        experience_type="internship",
        source_type="USER_ENTERED",
    )
    db_session.add(placeholder)
    db_session.commit()
    db_session.refresh(master)

    created = create_mission(
        db_session,
        master.id,
        MissionCreate(raw_text="Baidu AI PM campus: placeholder master must not bind silently."),
    )
    with pytest.raises(HTTPException) as blocked:
        confirm_resume_source(
            db_session,
            created["id"],
            ConfirmResumeSource(mode=ResumeSourceMode.master),
        )
    assert blocked.value.status_code == 409
    detail = str(blocked.value.detail)
    assert ("占位" in detail) or ("文职" in detail)
