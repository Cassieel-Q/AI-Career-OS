"""改事实 ≠ 绕过核对（可信求职 v1.2 · Sprint A/E）。

为什么有这个文件
----------------
Sprint A 把「提取到 / 采纳改写 / 核实事实」拆成互不推导的三件事。这里守住它的一个
推论：**事实文本一旦变化，之前那次「用户已核实」就不再对应当前文本**，必须退回
``UNREVIEWED`` 重新核对。否则等于用旧签名给新文本背书——简历、参考回答都会把它
当成「用户确认过的事实」放行。

两条改事实的路径都要覆盖：

- ``PUT /profiles/{id}``（DRAFT 档案逐字段修正）——本文件主要测这条；
- ``POST /profiles/{id}/facts/attest`` + ``apply_to_source=true``（**已确认档案**改共享
  事实的唯一入口，见 ``apps/web/app/fact-check.tsx``）。这条是「核对」与「写回」同一次
  动作，签名随之更新，不存在绕过核对的口子。

已确认档案在 ``PUT /profiles/{id}`` 上仍然 409（``test_confirmed_profile_cannot_be_edited``
锁的是这条），本文件不改动它——需要改共享 IS 事实时走上面第二条路径。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.fact_trust import VerificationStatus, is_attested
from app.fact_trust_schemas import FactAttestCreate
from app.fact_trust_service import attest_fact, invalidate_changed_attestations, list_facts
from app.profile_schemas import ProfileUpdate
from app.profile_service import update_draft_profile
from app.resume_schemas import ResumeExtractionResult  # noqa: F401  仅用于构造覆盖用例


def _build(db: Session, *, status: str = "DRAFT") -> models.UserProfile:
    profile = models.UserProfile(status=status, full_name="测试同学")
    db.add(profile)
    db.flush()
    db.add(
        models.Experience(
            profile_id=profile.id,
            title="校园二手平台产品实习",
            organization="某高校",
            dates="2025.03-2025.07",
            description="访谈12名同学，完成PRD和Figma原型。",
            experience_type="INTERNSHIP",
        )
    )
    db.add(
        models.Experience(
            profile_id=profile.id,
            title="另一个项目",
            organization="实验室",
            dates="2024.09-2025.01",
            description="做了一版竞品分析。",
            experience_type="PROJECT",
        )
    )
    db.commit()
    db.refresh(profile)
    return profile


def _attest_all(db: Session, profile_id) -> None:
    for fact in list_facts(db, profile_id).facts:
        attest_fact(
            db,
            profile_id,
            FactAttestCreate(fact_key=fact.fact_key, status=VerificationStatus.USER_ATTESTED.value),
        )


def _row(db: Session, profile_id, fact_key: str) -> models.FactAttestation:
    return db.scalar(
        select(models.FactAttestation).where(
            models.FactAttestation.profile_id == profile_id,
            models.FactAttestation.fact_key == fact_key,
        )
    )


def _payload(profile: models.UserProfile, *, description_override: str | None = None) -> ProfileUpdate:
    """按 id 回写（带 id 才会复用同一行，事实键才稳定）。

    改的是 ``description``：事实签名比对的文本目前由「标题 / 组织 / 描述」组成
    （``fact_trust_service._iter_facts``），时间不在其中——这点作为残留风险记在
    known-issues.md，本轮不扩大改动面。
    """
    return ProfileUpdate(
        full_name="测试同学",
        experiences=[
            {
                "id": str(item.id),
                "title": item.title,
                "organization": item.organization,
                "dates": item.dates,
                "description": (
                    description_override if description_override and item is profile.experiences[0] else item.description
                ),
                "experience_type": item.experience_type,
            }
            for item in profile.experiences
        ],
    )


# --------------------------------------------------------------------------
# 1. 改事实 → 该事实的签名失效
# --------------------------------------------------------------------------


def test_editing_a_fact_revokes_its_attestation(db_session: Session) -> None:
    profile = _build(db_session)
    _attest_all(db_session, profile.id)
    key = f"experience:{profile.experiences[0].id}"
    assert is_attested(_row(db_session, profile.id, key).status)

    update_draft_profile(db_session, profile.id, _payload(profile, description_override="访谈12名同学，完成PRD和Figma原型，并跟进了一轮灰度。"))

    row = _row(db_session, profile.id, key)
    assert row.status == VerificationStatus.UNREVIEWED.value
    assert not is_attested(row.status)
    assert row.verified_at is None
    assert row.verified_by is None


def test_unchanged_facts_keep_their_attestation(db_session: Session) -> None:
    """只改 A 事实，B 事实的签名不能被连坐。"""
    profile = _build(db_session)
    _attest_all(db_session, profile.id)
    changed_key = f"experience:{profile.experiences[0].id}"
    untouched_key = f"experience:{profile.experiences[1].id}"

    update_draft_profile(db_session, profile.id, _payload(profile, description_override="访谈12名同学，完成PRD和Figma原型，并跟进了一轮灰度。"))

    assert not is_attested(_row(db_session, profile.id, changed_key).status)
    assert is_attested(_row(db_session, profile.id, untouched_key).status)


def test_deleting_a_fact_revokes_its_attestation(db_session: Session) -> None:
    """事实被删掉后，残留的签名不能继续为简历背书。"""
    profile = _build(db_session)
    _attest_all(db_session, profile.id)
    removed_key = f"experience:{profile.experiences[0].id}"
    kept = profile.experiences[1]

    update_draft_profile(
        db_session,
        profile.id,
        ProfileUpdate(
            full_name="测试同学",
            experiences=[
                {
                    "id": str(kept.id),
                    "title": kept.title,
                    "organization": kept.organization,
                    "dates": kept.dates,
                    "description": kept.description,
                    "experience_type": kept.experience_type,
                }
            ],
        ),
    )

    assert not is_attested(_row(db_session, profile.id, removed_key).status)


def test_invalidate_reports_changed_count(db_session: Session) -> None:
    profile = _build(db_session)
    _attest_all(db_session, profile.id)

    assert invalidate_changed_attestations(db_session, profile) == 0  # 未改动 → 不撤销

    profile.experiences[0].description = "访谈12名同学，完成PRD和Figma原型，并跟进了一轮灰度。"
    db_session.flush()
    assert invalidate_changed_attestations(db_session, profile) == 1


# --------------------------------------------------------------------------
# 2. 已确认档案改共享事实：必须走「核对即写回」，不能绕过
# --------------------------------------------------------------------------


def test_confirmed_profile_put_still_rejected(db_session: Session) -> None:
    """对照项：直接 PUT 改已确认档案仍然被拒（既有产品规则，本轮不改）。"""
    profile = _build(db_session, status="CONFIRMED")

    with pytest.raises(HTTPException) as caught:
        update_draft_profile(db_session, profile.id, _payload(profile, description_override="访谈12名同学，完成PRD和Figma原型，并跟进了一轮灰度。"))

    assert caught.value.status_code == 409


def test_confirmed_profile_fact_can_be_updated_by_attestation(db_session: Session) -> None:
    """已确认档案改共享事实的唯一入口：核对 + 写回同一次动作，签名跟着新文本走。"""
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"
    new_text = "校园二手平台产品实习 / 某高校 / 访谈12名同学，完成PRD和Figma原型，并把时间修正为 2025.03-2025.09。"

    read = attest_fact(
        db_session,
        profile.id,
        FactAttestCreate(
            fact_key=key,
            status=VerificationStatus.USER_ATTESTED.value,
            fact_text=new_text,
            apply_to_source=True,
        ),
    )

    assert read.applied_to_source is True
    assert is_attested(read.status)
    db_session.refresh(profile)
    assert "2025.03-2025.09" in (profile.experiences[0].description or "")
