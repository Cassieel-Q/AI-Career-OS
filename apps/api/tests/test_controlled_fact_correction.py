"""受控字段修正 + 起止时间进入事实签名（FINAL FREEZE · P1-A / P1-B）。

为什么有这个文件
----------------

P1-A：已确认档案的字段修正
    档案被置为 ``CONFIRMED`` 后，``PUT /profiles/{id}`` 一律 409（既有产品规则，
    ``test_confirmed_profile_cannot_be_edited`` 锁着）。但用户确实会填错经历标题、
    公司、起止时间。本轮的方案是**保留整体锁定、开放受控单项修正**：

    - 入口只有 ``POST /profiles/{id}/facts/attest`` + ``field_updates`` +
      ``apply_to_source=true``——「修正」与「写回」是同一次用户确认动作；
    - 只开放白名单字段（经历：标题/组织/起止时间/描述；技能：名称）；
    - 返回新旧值对照与影响面，用户看得见改了什么；
    - 岗位简历版本不自动更新，历史投递快照不受影响。

P1-B：起止时间进入事实签名
    旧签名只覆盖标题/组织/描述，改时间不触发失效——旧的 ``USER_ATTESTED`` 会继续
    给新事实背书。本轮新增 ``signature_text``（内部签名，含时间），
    ``fact_text`` 继续承担页面展示，两者分离。

覆盖不到的部分（不做过度声明）：真实模型下的改写效果、真人用户研究均未执行。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.fact_impact_service import analyze_impact, sync_mission
from app.fact_trust import VerificationStatus, is_attested
from app.fact_trust_schemas import FactAttestCreate
from app.fact_trust_service import (
    attest_fact,
    invalidate_changed_attestations,
    list_facts,
    lock_legacy_signatures,
)
from app.profile_schemas import ProfileUpdate
from app.profile_service import update_draft_profile


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
    db.add(models.ProfileSkill(profile_id=profile.id, name="需求分析", proficiency="PROJECT_READY"))
    db.commit()
    db.refresh(profile)
    return profile


def _row(db: Session, profile_id, fact_key: str) -> models.FactAttestation:
    return db.scalar(
        select(models.FactAttestation).where(
            models.FactAttestation.profile_id == profile_id,
            models.FactAttestation.fact_key == fact_key,
        )
    )


def _attest(db: Session, profile_id, fact_key: str, **kwargs) -> object:
    payload = FactAttestCreate(fact_key=fact_key, status=VerificationStatus.USER_ATTESTED.value, **kwargs)
    return attest_fact(db, profile_id, payload)


def _payload(profile: models.UserProfile, *, dates_override: str | None = None) -> ProfileUpdate:
    """按 id 回写（带 id 才会复用同一行，事实键才稳定）。"""
    return ProfileUpdate(
        full_name="测试同学",
        experiences=[
            {
                "id": str(item.id),
                "title": item.title,
                "organization": item.organization,
                "dates": dates_override if dates_override and item is profile.experiences[0] else item.dates,
                "description": item.description,
                "experience_type": item.experience_type,
            }
            for item in profile.experiences
        ],
    )


# ===========================================================================
# P1-A：已确认档案的受控字段修正
# ===========================================================================


def test_confirmed_profile_still_refuses_whole_profile_put(db_session: Session) -> None:
    """对照项：整体 PUT 依然被拒（既有编辑保护，本轮必须保持有效）。"""
    profile = _build(db_session, status="CONFIRMED")
    with pytest.raises(HTTPException) as caught:
        update_draft_profile(db_session, profile.id, _payload(profile, dates_override="2025.03-2025.09"))
    assert caught.value.status_code == 409


def test_confirmed_profile_allows_controlled_dates_correction(db_session: Session) -> None:
    """已确认档案可通过核对入口修正起止时间，并返回新旧值对照。"""
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"

    read = _attest(
        db_session,
        profile.id,
        key,
        apply_to_source=True,
        field_updates={"dates": "2025.03-2025.09"},
    )

    assert read.applied_to_source is True
    assert read.applied_fields == ["dates"]
    assert read.field_changes[0].old_value == "2025.03-2025.07"
    assert read.field_changes[0].new_value == "2025.03-2025.09"
    db_session.refresh(profile)
    assert profile.experiences[0].dates == "2025.03-2025.09"


def test_controlled_correction_covers_title_organization_and_description(db_session: Session) -> None:
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"

    read = _attest(
        db_session,
        profile.id,
        key,
        apply_to_source=True,
        field_updates={
            "title": "校园二手平台产品负责人",
            "organization": "某高校创业团队",
            "description": "访谈12名同学，完成PRD和Figma原型，并跟进一轮灰度。",
        },
    )

    assert set(read.applied_fields) == {"title", "organization", "description"}
    db_session.refresh(profile)
    exp = profile.experiences[0]
    assert exp.title == "校园二手平台产品负责人"
    assert exp.organization == "某高校创业团队"
    assert exp.source_type == "USER_ENTERED"


def test_correction_requires_write_back(db_session: Session) -> None:
    """不允许「不写回的字段修正」——修正与写回必须是同一次动作。"""
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"

    with pytest.raises(HTTPException) as caught:
        _attest(db_session, profile.id, key, field_updates={"dates": "2025.03-2025.09"})
    assert caught.value.status_code == 422


def test_correction_rejects_fields_outside_the_whitelist(db_session: Session) -> None:
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"

    with pytest.raises(HTTPException) as caught:
        _attest(
            db_session,
            profile.id,
            key,
            apply_to_source=True,
            field_updates={"full_name": "张三", "salary": "30000"},
        )
    assert caught.value.status_code == 422
    assert "full_name" in str(caught.value.detail)


def test_skill_allows_name_only(db_session: Session) -> None:
    profile = _build(db_session, status="CONFIRMED")
    key = f"skill:{profile.skills[0].id}"

    read = _attest(db_session, profile.id, key, apply_to_source=True, field_updates={"name": "需求分析与原型设计"})
    assert read.applied_fields == ["name"]

    with pytest.raises(HTTPException) as caught:
        _attest(db_session, profile.id, key, apply_to_source=True, field_updates={"proficiency": "PROFICIENT"})
    assert caught.value.status_code == 422


def test_correction_without_attestation_leaves_fact_unreviewed(db_session: Session) -> None:
    """修正了内容但没有确认为属实 → 不算已核实（不能绕过核对）。"""
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"
    _attest(db_session, profile.id, key)

    read = attest_fact(
        db_session,
        profile.id,
        FactAttestCreate(
            fact_key=key,
            status=VerificationStatus.UNREVIEWED.value,
            apply_to_source=True,
            field_updates={"dates": "2025.02-2025.06"},
        ),
    )

    assert read.applied_to_source is True
    assert read.status == VerificationStatus.UNREVIEWED.value
    assert read.verified_at is None
    db_session.refresh(profile)
    assert profile.experiences[0].dates == "2025.02-2025.06"


def test_correction_does_not_disturb_other_facts(db_session: Session) -> None:
    """改 A 经历，B 经历的核对记录不能连坐失效。"""
    profile = _build(db_session, status="CONFIRMED")
    _attest(db_session, profile.id, f"experience:{profile.experiences[0].id}")
    _attest(db_session, profile.id, f"experience:{profile.experiences[1].id}")
    untouched = f"experience:{profile.experiences[1].id}"

    _attest(
        db_session,
        profile.id,
        f"experience:{profile.experiences[0].id}",
        apply_to_source=True,
        field_updates={"dates": "2025.03-2025.09"},
    )

    assert is_attested(_row(db_session, profile.id, untouched).status)


def test_no_change_no_write(db_session: Session) -> None:
    """提交相同的值不算修正，也不产生误导性的变更记录。"""
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"

    read = _attest(db_session, profile.id, key, apply_to_source=True, field_updates={"dates": "2025.03-2025.07"})

    assert read.applied_fields == []
    assert read.field_changes == []


# ===========================================================================
# P1-B：起止时间进入事实签名
# ===========================================================================


def test_changing_dates_via_put_revokes_attestation(db_session: Session) -> None:
    """核心回归：改时间后旧签名必须失效（旧实现只对标题/组织/描述生效）。"""
    profile = _build(db_session)
    key = f"experience:{profile.experiences[0].id}"
    _attest(db_session, profile.id, key)
    assert is_attested(_row(db_session, profile.id, key).status)

    update_draft_profile(db_session, profile.id, _payload(profile, dates_override="2025.03-2025.09"))

    row = _row(db_session, profile.id, key)
    assert row.status == VerificationStatus.UNREVIEWED.value
    assert not is_attested(row.status)
    assert row.verified_at is None


@pytest.mark.parametrize(
    "field,value",
    [("title", "校园二手平台产品负责人"), ("organization", "某高校创业团队")],
)
def test_title_and_organization_changes_also_revoke(db_session: Session, field: str, value: str) -> None:
    profile = _build(db_session)
    exp = profile.experiences[0]
    key = f"experience:{exp.id}"
    _attest(db_session, profile.id, key)

    setattr(exp, field, value)
    db_session.flush()
    invalidate_changed_attestations(db_session, profile)
    db_session.commit()

    assert not is_attested(_row(db_session, profile.id, key).status)


def test_rechecking_after_correction_records_new_signature(db_session: Session) -> None:
    """失效 → 重新核对 → 新签名覆盖新的时间，之后再改时间仍会失效。"""
    profile = _build(db_session, status="CONFIRMED")
    key = f"experience:{profile.experiences[0].id}"
    _attest(db_session, profile.id, key)

    # 修正时间并同时确认为属实：留下新事实的核对记录
    read = _attest(db_session, profile.id, key, apply_to_source=True, field_updates={"dates": "2025.03-2025.09"})
    assert is_attested(read.status)
    first_signature = _row(db_session, profile.id, key).signature_text
    assert first_signature is not None

    # 再改一次时间（不核对）→ 必须失效
    db_session.refresh(profile)
    profile.experiences[0].dates = "2025.03-2025.12"
    db_session.flush()
    assert invalidate_changed_attestations(db_session, profile) == 1
    assert not is_attested(_row(db_session, profile.id, key).status)


def test_legacy_attestation_is_not_mass_upgraded(db_session: Session) -> None:
    """旧格式记录（无 signature_text）：不批量升级、不批量失效，补写后按签名判定。"""
    profile = _build(db_session)
    key = f"experience:{profile.experiences[0].id}"
    _attest(db_session, profile.id, key)

    # 模拟升级前的数据：签名列为空
    row = _row(db_session, profile.id, key)
    row.signature_text = None
    db_session.commit()

    assert invalidate_changed_attestations(db_session, profile) == 0  # 内容没变 → 不该误伤
    db_session.flush()
    db_session.refresh(row)
    assert row.signature_text is not None  # 保守迁移：补写当前签名
    assert is_attested(row.status)

    # 迁移之后，改时间同样会失效
    db_session.refresh(profile)
    profile.experiences[0].dates = "2025.03-2025.10"
    db_session.flush()
    assert invalidate_changed_attestations(db_session, profile) == 1


def test_signature_is_separated_from_display_text(db_session: Session) -> None:
    """内部签名与页面展示文本分离：展示文本不含时间，签名含时间。"""
    profile = _build(db_session)
    key = f"experience:{profile.experiences[0].id}"
    _attest(db_session, profile.id, key)

    displayed = next(fact for fact in list_facts(db_session, profile.id).facts if fact.fact_key == key)
    assert "2025.03-2025.07" not in displayed.original_text
    assert "2025.03-2025.07" in (_row(db_session, profile.id, key).signature_text or "")


def test_invalidate_is_idempotent(db_session: Session) -> None:
    """重复运行不得误伤已核对事实。"""
    profile = _build(db_session)
    _attest(db_session, profile.id, f"experience:{profile.experiences[0].id}")
    _attest(db_session, profile.id, f"experience:{profile.experiences[1].id}")

    assert invalidate_changed_attestations(db_session, profile) == 0
    assert invalidate_changed_attestations(db_session, profile) == 0
    assert list_facts(db_session, profile.id).attested_count == 2


def test_lock_legacy_signatures_runs_before_mutation(db_session: Session) -> None:
    """PUT 全程：先锁定旧签名，再改字段，改完失效（顺序错了就锁不住旧状态）。"""
    profile = _build(db_session)
    key = f"experience:{profile.experiences[0].id}"
    _attest(db_session, profile.id, key)
    _row(db_session, profile.id, key).signature_text = None
    db_session.commit()

    update_draft_profile(db_session, profile.id, _payload(profile, dates_override="2025.01-2025.05"))

    assert not is_attested(_row(db_session, profile.id, key).status)


# ===========================================================================
# P1-A 与岗位版本的一致性：影响面提示 + 只更新选中 + 快照不变
# ===========================================================================


def _mission_with_studio(db_session: Session, profile, experience, *, company: str, role: str):
    from test_resume_studio_document import _mission_with_resume

    mission, _exp, _resume = _mission_with_resume(db_session)
    job = models.TargetJob(profile_id=profile.id, raw_text=f"{company} {role}", content_hash=f"{company}{role}")
    db_session.add(job)
    db_session.flush()
    return mission


def test_correction_shows_impact_and_only_synced_mission_changes(db_session: Session) -> None:
    """修正共享事实后：影响面提示「可能需要更新」，只同步选中的那一份。"""
    from test_multi_job_version_consistency import _add_mission, _studio_document
    from test_resume_studio_document import _mission_with_resume

    mission_a, experience, _ = _mission_with_resume(db_session)
    profile = db_session.get(models.UserProfile, mission_a.profile_id)
    profile.status = "CONFIRMED"
    mission_b = _add_mission(db_session, profile, experience, company="Beta", role="PM")
    mission_c = _add_mission(db_session, profile, experience, company="Gamma", role="APM")
    db_session.commit()

    def revisions() -> dict:
        return {
            str(m.id): _studio_document(db_session, m.id).revision
            for m in (mission_a, mission_b, mission_c)
        }

    before = revisions()
    # 同步一次，让 Studio 文档记录当前事实文本（dates 进 Studio 的 date 节点）
    from app.fact_impact_service import sync_mission as _sync

    for mission in (mission_a, mission_b, mission_c):
        _sync(db_session, profile.id, "experience", experience.id, mission.id)
    db_session.commit()
    before = revisions()

    key = f"experience:{experience.id}"
    _attest(db_session, profile.id, key, apply_to_source=True, field_updates={"dates": "2025.03-2025.09"})
    db_session.commit()

    impact = analyze_impact(db_session, profile.id, "experience", experience.id)
    assert impact["total_missions"] >= 3
    assert impact["needs_update_count"] >= 1
    assert "可能需要更新" in impact["summary"]
    assert impact["auto_update"] is False

    # 只更新 B
    _sync(db_session, profile.id, "experience", experience.id, mission_b.id)
    db_session.commit()
    after = revisions()

    assert after[str(mission_b.id)] != before[str(mission_b.id)]
    assert after[str(mission_a.id)] == before[str(mission_a.id)]
    assert after[str(mission_c.id)] == before[str(mission_c.id)]

    # 历史投递快照不受影响
    snapshots = list(
        db_session.scalars(select(models.DeliverySnapshot).where(models.DeliverySnapshot.profile_id == profile.id)).all()
    )
    assert snapshots == []


def test_delivery_snapshot_is_untouched_by_correction(db_session: Session) -> None:
    """修正共享事实 → 同步岗位版本 → 已有的投递快照内容哈希不变。"""
    from test_multi_job_version_consistency import _studio_document
    from test_resume_studio_document import _mission_with_resume

    mission, experience, _ = _mission_with_resume(db_session)
    profile = db_session.get(models.UserProfile, mission.profile_id)
    profile.status = "CONFIRMED"
    db_session.commit()

    studio = _studio_document(db_session, mission.id)
    from app.delivery_version_service import record_snapshot

    snapshot = record_snapshot(db_session, mission, studio, source="TEST")
    db_session.commit()
    assert snapshot is not None
    original_hash = snapshot.content_hash
    original_json = dict(snapshot.document_json or {})

    _attest(
        db_session,
        profile.id,
        f"experience:{experience.id}",
        apply_to_source=True,
        field_updates={"dates": "2025.03-2025.09"},
    )
    sync_mission(db_session, profile.id, "experience", experience.id, mission.id)
    db_session.commit()

    db_session.refresh(snapshot)
    assert snapshot.content_hash == original_hash
    assert (snapshot.document_json or {}) == original_json
