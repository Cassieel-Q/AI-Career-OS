"""导出与快照的隐私边界（可信求职 v1.2 · Sprint D/F）。

守的是三件事：

1. **简历侧只看简历事实**：网申资料里的身份证号、家庭情况、健康状态、档案所在地、
   紧急联系人、可入职时间等敏感字段，绝不能出现在简历生成载荷里。
2. **文件名只带姓名/公司/岗位/版本**：不写手机号、邮箱，更不写任何密钥。
3. **投递快照只存简历内容**：表里不该出现密钥类字段。

这些都是「导出即外发」的位置——一旦漏出去，用户没法收回。
"""

from __future__ import annotations

import pytest

from app import models
from app.application_profile_service import (
    SENSITIVE_FIELDS,
    application_fill_facts,
    assert_resume_payload_has_no_sensitive_fields,
    resume_visible_facts,
)
from app.resume_studio_service import build_resume_filename

#: 一眼就该被挡下来的密钥形状（只列真正的密钥形状——「Authorization」这种头部名本身不敏感）
SECRET_SHAPES = ("sk-", "api_key", "apikey", "bearer", "access_token")


@pytest.fixture
def profile_with_sensitive(db_session):
    profile = models.UserProfile(status="CONFIRMED", full_name="陈林", phone="13800000000", email="chenlin@example.com")
    db_session.add(profile)
    db_session.flush()
    db_session.add(
        models.Experience(
            profile_id=profile.id,
            title="校园二手平台产品实习",
            organization="某高校",
            dates="2025.03-2025.07",
            description="访谈12名同学，完成PRD和Figma原型。",
            experience_type="INTERNSHIP",
        )
    )
    db_session.commit()
    db_session.refresh(profile)
    return profile


# --------------------------------------------------------------------------
# 1. 简历侧事实边界
# --------------------------------------------------------------------------


def test_resume_visible_facts_exclude_application_section(db_session, profile_with_sensitive) -> None:
    facts = resume_visible_facts(db_session, profile_with_sensitive.id)

    assert "application" not in facts
    assert_resume_payload_has_no_sensitive_fields(facts)


def test_application_fill_facts_include_application_section(db_session, profile_with_sensitive) -> None:
    """对照项：网申填表确实能读到网申资料——只有它这一个入口可以。"""
    assert "application" in application_fill_facts(db_session, profile_with_sensitive.id)


@pytest.mark.parametrize("field", SENSITIVE_FIELDS)
def test_guard_rejects_every_sensitive_field(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        assert_resume_payload_has_no_sensitive_fields({"sections": [{"entries": [{field: "敏感值"}]}]})


def test_guard_accepts_a_clean_payload() -> None:
    assert_resume_payload_has_no_sensitive_fields({"basics": {"name": {"text": "陈林"}}, "sections": []})


# --------------------------------------------------------------------------
# 2. 文件名：只有姓名/公司/岗位/版本
# --------------------------------------------------------------------------


def test_filename_never_contains_phone_or_email() -> None:
    name = build_resume_filename(
        name="陈林 13800000000 chenlin@example.com",
        company="Acme",
        role="AI 产品经理实习生",
        revision=2,
        draft=False,
    )
    assert "13800000000" not in name
    assert "chenlin@example.com" not in name
    assert "chenlinexamplecom" not in name  # 抹掉 @ 与 . 之后的残留也不许留
    assert name.endswith("_v2.pdf")


def test_filename_never_contains_secret_shapes() -> None:
    name = build_resume_filename(
        name="陈林",
        company="sk-live-abcdef123456",
        role="Authorization: Bearer abcdef",
        revision=1,
        draft=False,
    )
    for shape in SECRET_SHAPES:
        assert shape.lower() not in name.lower()


def test_filename_has_no_path_separators() -> None:
    """防目录穿越：公司/岗位来自 JD 文本，不能带出路径分隔符。"""
    name = build_resume_filename(
        name="陈林",
        company="../../etc/passwd",
        role="..\\windows\\system32",
        revision=1,
        draft=True,
    )
    assert "/" not in name
    assert "\\" not in name
    assert ".." not in name
    assert name.endswith("_v1_DRAFT.pdf")


def test_draft_and_final_names_are_always_distinguishable() -> None:
    kwargs = {"name": "陈林", "company": "Acme", "role": "产品经理实习生", "revision": 3}
    draft = build_resume_filename(draft=True, **kwargs)
    final = build_resume_filename(draft=False, **kwargs)
    assert draft != final
    assert "_DRAFT" in draft and "_DRAFT" not in final


# --------------------------------------------------------------------------
# 3. 投递快照只存简历内容
# --------------------------------------------------------------------------


def test_delivery_snapshot_table_has_no_secret_columns() -> None:
    columns = {column.name for column in models.DeliverySnapshot.__table__.columns}
    assert {"document_json", "content_hash", "pdf_path", "studio_revision"} <= columns
    assert not any(token in name.lower() for name in columns for token in ("key", "secret", "token", "password"))
