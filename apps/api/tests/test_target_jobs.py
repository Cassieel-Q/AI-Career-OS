from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException

from app import models
from app.proof_schemas import ClaimProposalPayload, TargetJobCreate
from app.proof_service import create_target_job, generate_claim_analysis, get_claim_analysis


class FakeClaimProvider:
    def __init__(self, payload: ClaimProposalPayload) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def analyze(self, *, target_job: dict[str, object], profile_facts: list[dict[str, object]]) -> ClaimProposalPayload:
        self.calls.append({"target_job": target_job, "profile_facts": profile_facts})
        return self.payload


def confirmed_profile(persisted_profile):
    persisted_profile.status = "CONFIRMED"
    return persisted_profile


def claim_payload(evidence_ref: UUID) -> ClaimProposalPayload:
    return ClaimProposalPayload.model_validate({
        "claims": [{
            "claim": "Designed an LLM evaluation workflow",
            "current_text": "Worked on LLM evaluation",
            "suggested_text": "Designed an LLM evaluation workflow",
            "reason": "The experience is present but under-explained.",
            "jd_relevance": "Matches the evaluation responsibility.",
            "matched_capabilities": [{"name": "LLM evaluation", "summary": "Evaluation design", "atomic_requirement_ids": []}],
            "evidence_refs": [str(evidence_ref)],
            "readiness_status": "WEAK_EVIDENCE",
            "confidence": 0.7,
            "risk_reason": "No evaluation artifact is recorded.",
            "attack_surface": [{"area": "AI", "risk": "Explain evaluation design", "evidence_refs": [str(evidence_ref)]}],
        }]
    })


def test_one_target_job_does_not_require_role_preferences_or_three_jds(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()

    result = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product."))

    assert result.profile_id == persisted_profile.id
    assert result.raw_text == "Build an AI product."
    assert db_session.query(models.TargetRole).count() == 0


def test_duplicate_target_job_hash_is_rejected_without_deleting_previous_row(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product."))

    with pytest.raises(HTTPException) as caught:
        create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product."))

    assert caught.value.status_code == 409
    assert db_session.query(models.TargetJob).count() == 1


def test_claim_analysis_binds_only_confirmed_profile_evidence_and_persists_suggestions(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    target_job = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product evaluation workflow."))
    provider = FakeClaimProvider(claim_payload(persisted_profile.skills[0].id))

    result = generate_claim_analysis(db_session, target_job.id, provider=provider)

    assert len(result.claims) == 1
    assert result.claims[0].evidence_refs == [persisted_profile.skills[0].id]
    assert result.claims[0].suggested_text != result.claims[0].current_text
    assert provider.calls[0]["profile_facts"]
    assert db_session.query(models.ResumeClaim).count() == 1


def test_claim_analysis_rejects_unknown_profile_evidence_reference(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    target_job = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product."))
    provider = FakeClaimProvider(claim_payload(UUID("99999999-9999-4999-8999-999999999999")))

    with pytest.raises(HTTPException) as caught:
        generate_claim_analysis(db_session, target_job.id, provider=provider)

    assert caught.value.status_code == 422
    assert db_session.query(models.ResumeClaim).count() == 0


def test_claim_analysis_is_marked_stale_after_profile_change(db_session, persisted_profile):
    """改了事实 → 旧主张分析必须被**标记**为过期（只标记不替换）。

    2026-10-19：此前这条断言「必须 409 拒绝读取」，而实现走的是 soft-heal——
    发现指纹不一致后**刷新指纹**再照常返回，等于把旧分析伪装成新鲜结果，
    与本版本「只标记不替换」的约定冲突。现在改为：不静默刷新，返回
    ``stale=True`` 与原因，由用户决定「重新分析 / 继续查看历史结果」。
    """
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    target_job = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product."))
    generate_claim_analysis(db_session, target_job.id, provider=FakeClaimProvider(claim_payload(persisted_profile.skills[0].id)))
    original_fingerprint = db_session.query(models.ResumeClaim).first().fingerprint

    persisted_profile.skills[0].name = "Changed skill"
    db_session.commit()

    read = get_claim_analysis(db_session, target_job.id)
    assert read.stale is True
    assert read.stale_reasons
    # 历史结果仍在（可继续查看），但不得被刷新成「新鲜」
    assert read.claims
    assert db_session.query(models.ResumeClaim).first().fingerprint == original_fingerprint


def test_claim_analysis_empty_claim_still_blocks_after_profile_change(db_session, persisted_profile):
    """对照项：主张文本为空时无法继续，必须要求重新生成。"""
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    target_job = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI product."))
    generate_claim_analysis(db_session, target_job.id, provider=FakeClaimProvider(claim_payload(persisted_profile.skills[0].id)))
    for row in db_session.query(models.ResumeClaim).all():
        row.claim = ""
    persisted_profile.skills[0].name = "Changed skill"
    db_session.commit()

    with pytest.raises(HTTPException) as caught:
        get_claim_analysis(db_session, target_job.id)

    assert caught.value.status_code == 409
