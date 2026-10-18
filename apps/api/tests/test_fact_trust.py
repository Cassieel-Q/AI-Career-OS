"""事实核对契约测试（可信求职 v1.2 · Sprint A · 指令 1.1 / 1.3 / 1.4）。

核心断言：**「提取到」「采纳改写」「核实事实」三件事互不推导。**
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.fact_trust import (
    FactSource,
    VerificationStatus,
    coverage_score,
    extract_numeric_values,
    is_attested,
    legacy_verification,
    screen_text,
)
from app.fact_trust_schemas import FactAttestCreate
from app.fact_trust_service import analyze_aspects, attest_fact, attested_fact_texts, list_facts


def _profile(db: Session, *, status: str = "DRAFT", description: str = "访谈12名同学，完成PRD和Figma原型。") -> models.UserProfile:
    profile = models.UserProfile(status=status, full_name="测试同学")
    db.add(profile)
    db.flush()
    db.add(
        models.Experience(
            profile_id=profile.id,
            title="校园二手平台产品实习",
            organization="某高校",
            description=description,
            experience_type="INTERNSHIP",
        )
    )
    db.add(models.ProfileSkill(profile_id=profile.id, name="Figma", proficiency="PROJECT_READY"))
    db.commit()
    db.refresh(profile)
    return profile


# --------------------------------------------------------------------------
# 状态迁移：旧状态不得批量升级为「用户已核实」
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "legacy",
    ["CONFIRMED", "ACCEPTED", "READY", "SUPPORTED", "DEFENDABLE", "NEEDS_CONFIRMATION", "UNREVIEWED", "UNKNOWN_STATUS"],
)
def test_legacy_statuses_never_become_user_attested(legacy: str) -> None:
    assert legacy_verification(legacy) is VerificationStatus.UNREVIEWED
    assert not is_attested(legacy)


def test_only_user_attested_counts_as_verified() -> None:
    assert is_attested(VerificationStatus.USER_ATTESTED)
    assert legacy_verification("USER_ATTESTED") is VerificationStatus.USER_ATTESTED
    assert legacy_verification("REJECTED") is VerificationStatus.REJECTED


def test_legacy_source_mapping_defaults_to_extracted() -> None:
    from app.fact_trust import legacy_source

    assert legacy_source("SUPPORTED") is FactSource.SOURCE_EXTRACTED
    assert legacy_source("SUGGESTED") is FactSource.AI_PROPOSED
    assert legacy_source("EDITED") is FactSource.USER_PROVIDED


# --------------------------------------------------------------------------
# 确定性闸门
# --------------------------------------------------------------------------


def test_extract_numeric_values_reads_chinese_numerals() -> None:
    assert 12 in extract_numeric_values("访谈12名同学")
    assert 12 in extract_numeric_values("访谈十二名同学")
    assert 50 in extract_numeric_values("五十位创作者")
    assert 300 in extract_numeric_values("三百人")


def test_screen_text_blocks_unsupported_numbers_and_terms() -> None:
    result = screen_text("我带领团队上线了这个功能，效率提升40%。", "访谈12名同学，完成PRD和Figma原型。")
    assert not result.supported
    assert 40 in result.missing_numbers
    assert result.reasons


def test_screen_text_allows_supported_statement() -> None:
    result = screen_text("我访谈了12名同学，完成PRD和Figma原型。", "访谈12名同学，完成PRD和Figma原型。")
    assert result.supported


def test_screen_text_fails_closed_without_evidence() -> None:
    result = screen_text("我访谈了12名同学。", "")
    assert not result.supported
    assert "缺少可核对的事实语料" in result.reasons[0]


def test_coverage_score_is_symmetric_zero_for_unrelated_text() -> None:
    assert coverage_score("量子计算", "校园二手平台") == 0.0
    assert coverage_score("访谈12名同学", "访谈12名同学") == 1.0


# --------------------------------------------------------------------------
# 缺失维度分析
# --------------------------------------------------------------------------


def test_analyze_aspects_flags_missing_result() -> None:
    present, missing = analyze_aspects("访谈12名同学，完成PRD和Figma原型。")
    assert "可核对结果" in missing
    assert "个人动作" in present


# --------------------------------------------------------------------------
# 事实列表与核对动作
# --------------------------------------------------------------------------


def test_facts_start_unreviewed_even_when_profile_is_confirmed(db_session: Session) -> None:
    """档案状态 CONFIRMED 不等于事实已核实。"""
    profile = _profile(db_session, status="CONFIRMED")
    facts = list_facts(db_session, profile.id)
    assert facts.pending_count == 2
    assert facts.attested_count == 0
    assert all(fact.verification_status == "UNREVIEWED" for fact in facts.facts)
    assert all(fact.verified_at is None for fact in facts.facts)


def test_attest_records_user_confirmation(db_session: Session) -> None:
    profile = _profile(db_session)
    key = f"experience:{profile.experiences[0].id}"
    read = attest_fact(db_session, profile.id, FactAttestCreate(fact_key=key, status="USER_ATTESTED"))
    assert read.status == "USER_ATTESTED"
    assert read.verified_at is not None

    facts = list_facts(db_session, profile.id)
    assert facts.attested_count == 1
    assert facts.pending_count == 1
    assert attested_fact_texts(db_session, profile.id)


def test_rejected_fact_is_not_treated_as_verified(db_session: Session) -> None:
    profile = _profile(db_session)
    key = f"experience:{profile.experiences[0].id}"
    attest_fact(db_session, profile.id, FactAttestCreate(fact_key=key, status="REJECTED", note="这段不是我做的"))
    facts = list_facts(db_session, profile.id)
    assert facts.rejected_count == 1
    assert facts.attested_count == 0
    assert attested_fact_texts(db_session, profile.id) == []


def test_attest_rejects_legacy_status_values(db_session: Session) -> None:
    profile = _profile(db_session)
    key = f"experience:{profile.experiences[0].id}"
    with pytest.raises(HTTPException) as exc:
        attest_fact(db_session, profile.id, FactAttestCreate(fact_key=key, status="CONFIRMED"))
    assert exc.value.status_code == 422


def test_attest_unknown_fact_key_returns_404(db_session: Session) -> None:
    profile = _profile(db_session)
    with pytest.raises(HTTPException) as exc:
        attest_fact(db_session, profile.id, FactAttestCreate(fact_key="experience:not-a-real-id", status="USER_ATTESTED"))
    assert exc.value.status_code == 404


def test_withdrawing_attestation_clears_verification(db_session: Session) -> None:
    profile = _profile(db_session)
    key = f"experience:{profile.experiences[0].id}"
    attest_fact(db_session, profile.id, FactAttestCreate(fact_key=key, status="USER_ATTESTED"))
    read = attest_fact(db_session, profile.id, FactAttestCreate(fact_key=key, status="UNREVIEWED"))
    assert read.verified_at is None
    assert list_facts(db_session, profile.id).attested_count == 0


def test_edited_fact_only_writes_back_when_explicitly_requested(db_session: Session) -> None:
    profile = _profile(db_session)
    experience_id = profile.experiences[0].id
    key = f"experience:{experience_id}"

    attest_fact(
        db_session,
        profile.id,
        FactAttestCreate(fact_key=key, status="USER_ATTESTED", fact_text="我负责访谈并产出PRD", apply_to_source=False),
    )
    db_session.refresh(profile)
    assert profile.experiences[0].description.startswith("访谈12名同学")

    attest_fact(
        db_session,
        profile.id,
        FactAttestCreate(fact_key=key, status="USER_ATTESTED", fact_text="我负责访谈并产出PRD", apply_to_source=True),
    )
    db_session.refresh(profile)
    assert profile.experiences[0].description == "我负责访谈并产出PRD"


def test_missing_profile_returns_404(db_session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        list_facts(db_session, uuid4())
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------
# HTTP 路由
# --------------------------------------------------------------------------


def test_fact_routes_list_and_attest(client, db_session: Session) -> None:
    profile = _profile(db_session)
    response = client.get(f"/api/v1/profiles/{profile.id}/facts")
    assert response.status_code == 200
    body = response.json()
    assert body["pending_count"] == 2

    key = body["facts"][0]["fact_key"]
    attest = client.post(
        f"/api/v1/profiles/{profile.id}/facts/attest",
        json={"fact_key": key, "status": "USER_ATTESTED"},
    )
    assert attest.status_code == 200
    assert attest.json()["status"] == "USER_ATTESTED"

    attested = client.get(f"/api/v1/profiles/{profile.id}/facts/attested")
    assert attested.status_code == 200
    assert attested.json()["facts"]
