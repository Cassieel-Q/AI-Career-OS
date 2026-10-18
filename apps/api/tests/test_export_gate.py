"""草稿 / 正式投递版分离与导出前检查（可信求职 v1.2 · Sprint D · 指令 4.1-4.4）。

覆盖：
- 分级 BLOCK / WARN / INFO
- 缺姓名在草稿只是提示、在正式投递版必须阻塞（P05）
- 草稿可导出且文件名带 _DRAFT、正文盖草稿标记
- 正式版必须通过检查，且不能跳过确认
- 文件名规范与非法字符过滤
- 旧快照不被新修订替换
"""

from __future__ import annotations

from urllib.parse import unquote
from uuid import UUID

import pytest

from app.resume_studio_service import build_resume_filename, export_checks


def _node(text: str = "", *, claim_status: str = "CONFIRMED", risk_level: str = "LOW") -> dict:
    return {"id": "n1", "text": text, "claim_status": claim_status, "risk_level": risk_level}


def _document(*, name: str = "张三", phone: str = "13800138000", email: str = "", bullet_text: str = "完成 PRD") -> dict:
    return {
        "schema_version": 1,
        "basics": {
            "name": _node(name),
            "phone": _node(phone),
            "email": _node(email, claim_status="NEEDS_CONFIRMATION"),
            "location": _node("上海"),
        },
        "sections": [
            {
                "kind": "experience",
                "title": {"id": "t1", "text": "经历", "claim_status": "CONFIRMED"},
                "entries": [
                    {
                        "status": "INCLUDED",
                        "title": {"id": "e1", "text": "校园二手平台", "claim_status": "CONFIRMED"},
                        "subtitle": _node(""),
                        "date": _node(""),
                        "location": _node(""),
                        "bullets": [{"id": "b1", "text": bullet_text, "claim_status": "CONFIRMED"}],
                    }
                ],
            }
        ],
    }


def test_clean_document_passes_both_modes() -> None:
    for final in (False, True):
        assert [c for c in export_checks(_document(), final=final) if c["level"] == "block"] == []


def test_missing_name_warns_for_draft_but_blocks_final() -> None:
    """P05：姓名缺失不能还让用户「确认当前修订版」并下载投递版。"""
    document = _document(name="")
    draft_blocks = [c for c in export_checks(document, final=False) if c["level"] == "block"]
    assert draft_blocks == [], "草稿仍应允许导出"
    assert any(c["code"] == "missing_name" and c["level"] == "warn" for c in export_checks(document, final=False))
    final_blocks = [c for c in export_checks(document, final=True) if c["level"] == "block"]
    assert any(c["code"] == "missing_name" for c in final_blocks)


def test_missing_contact_blocks_only_final() -> None:
    document = _document(phone="", email="")
    assert [c for c in export_checks(document, final=False) if c["level"] == "block"] == []
    assert any(c["code"] == "missing_contact" for c in export_checks(document, final=True) if c["level"] == "block")


def test_high_risk_unconfirmed_fact_blocks_final_export() -> None:
    document = _document()
    document["sections"][0]["entries"][0]["bullets"][0] = {
        "id": "b1",
        "text": "负责用户增长，日活提升 30%",
        "claim_status": "NEEDS_CONFIRMATION",
        "risk_level": "HIGH",
    }
    assert [c for c in export_checks(document, final=False) if c["level"] == "block"] == []
    final_blocks = [c for c in export_checks(document, final=True) if c["level"] == "block"]
    assert any(c["code"] == "unconfirmed_fact" and c.get("high_risk") for c in final_blocks)


def test_placeholder_residue_blocks_every_mode() -> None:
    document = _document(bullet_text="完成 PRD【待补充】")
    for final in (False, True):
        assert any(c["code"] == "placeholder_residue" for c in export_checks(document, final=final))


def test_empty_resume_blocks_every_mode() -> None:
    document = _document()
    document["sections"][0]["entries"][0]["bullets"] = []
    for final in (False, True):
        assert any(c["code"] == "empty_resume" for c in export_checks(document, final=final))


def test_info_level_does_not_block_anything() -> None:
    document = _document()
    document["sections"][0]["entries"][0]["bullets"] = [
        {"id": f"b{index}", "text": f"要点 {index}", "claim_status": "CONFIRMED"} for index in range(30)
    ]
    checks = export_checks(document, final=True)
    assert any(check["level"] == "info" for check in checks)
    assert [check for check in checks if check["level"] == "block"] == []


# --------------------------------------------------------------------------
# 文件名
# --------------------------------------------------------------------------


def test_final_filename_follows_the_agreed_pattern() -> None:
    name = build_resume_filename(
        name="张三", company="某某科技", role="AI 产品实习生", revision=2, draft=False
    )
    assert name == "张三_某某科技_AI_产品实习生_v2.pdf"


def test_draft_filename_is_clearly_marked() -> None:
    name = build_resume_filename(name="张三", company="Acme", role="PM", revision=3, draft=True)
    assert name == "张三_Acme_PM_v3_DRAFT.pdf"


def test_filename_strips_windows_illegal_characters() -> None:
    name = build_resume_filename(
        name='张/三\\:*?"<>|', company="A|B", role="PM\t", revision=1, draft=False
    )
    for illegal in '/\\:*?"<>|\t':
        assert illegal not in name


def test_filename_never_repeats_revision_in_draft_and_final() -> None:
    final = build_resume_filename(name="李", company="C", role="R", revision=4, draft=False)
    draft = build_resume_filename(name="李", company="C", role="R", revision=4, draft=True)
    assert final == "李_C_R_v4.pdf"
    assert draft == "李_C_R_v4_DRAFT.pdf"


# --------------------------------------------------------------------------
# HTTP：草稿与正式版分离
# --------------------------------------------------------------------------


def _create_mission(client, persisted_profile):
    from uuid import UUID

    from app.mission_provider import set_mission_provider
    from app.mission_schemas import JobExtractionPayload, WhatMattersPayload

    class _Stub:
        def parse_jd(self, raw_text):
            return JobExtractionPayload.model_validate(
                {
                    "company": "某某科技",
                    "role": "AI 产品实习生",
                    "role_family": "PRODUCT",
                    "seniority": "INTERN",
                    "responsibilities": ["负责需求"],
                    "requirements": [],
                    "preferred_requirements": [],
                    "capabilities": ["需求分析"],
                    "keywords": ["产品"],
                }
            )

        def build_what_matters(self, **_kwargs):
            return WhatMattersPayload.model_validate(
                {
                    "core_capabilities": [{"name": "需求分析", "why": "JD 要求", "evidence_refs": []}],
                    "high_importance_requirements": [],
                    "evidence_expected": [],
                    "likely_success_signals": [],
                    "bonus_capabilities": [],
                    "potential_interview_focus": [],
                    "confidence": 0.8,
                    "jd_evidence_refs": [],
                }
            )

    set_mission_provider(_Stub())
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/job-missions",
        json={"raw_text": "某某科技 AI 产品实习生：负责需求分析。"},
    )
    assert created.status_code == 201, created.text
    return UUID(created.json()["id"])


def _seed_document(db_session, mission_id: UUID) -> None:
    """直接放一份 Studio 文档，绕过「先生成定向简历」的前置流程。"""
    from uuid import uuid4

    from app import models

    db_session.add(
        models.ResumeStudioDocument(
            mission_id=mission_id,
            source_target_resume_id=uuid4(),
            revision=1,
            language="zh",
            template_id="zh-classic",
            document_json=_document(),
        )
    )
    db_session.commit()


def test_final_pdf_requires_confirmation_while_draft_is_always_available(
    client, db_session, persisted_profile
) -> None:
    mission_id = _create_mission(client, persisted_profile)
    _seed_document(db_session, mission_id)

    final = client.get(f"/api/v1/job-missions/{mission_id}/resume-studio/pdf")
    assert final.status_code == 409, final.text

    draft = client.get(f"/api/v1/job-missions/{mission_id}/resume-studio/pdf?draft=1")
    assert draft.status_code == 200, draft.text
    assert draft.headers.get("X-Resume-Draft") == "1"
    filename = unquote(draft.headers.get("X-Resume-Filename") or "")
    assert filename.endswith("_DRAFT.pdf"), filename
    assert "张三" in filename, filename


def test_final_pdf_blocks_when_the_final_checks_fail(client, db_session, persisted_profile) -> None:
    """确认过修订号也不行：正式口径还有阻塞项时必须拒绝。"""
    from app import models

    mission_id = _create_mission(client, persisted_profile)
    document = _document(name="")
    from uuid import uuid4

    db_session.add(
        models.ResumeStudioDocument(
            mission_id=mission_id,
            source_target_resume_id=uuid4(),
            revision=1,
            language="zh",
            template_id="zh-classic",
            document_json=document,
            confirmed_revision=1,
        )
    )
    db_session.commit()
    response = client.get(f"/api/v1/job-missions/{mission_id}/resume-studio/pdf")
    assert response.status_code == 409, response.text
    assert "missing_name" in response.text


def test_preview_returns_both_draft_and_final_checks(client, db_session, persisted_profile) -> None:
    mission_id = _create_mission(client, persisted_profile)
    _seed_document(db_session, mission_id)
    preview = client.post(f"/api/v1/job-missions/{mission_id}/resume-studio/preview", json={"revision": 1})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert "checks" in body and "final_checks" in body
    # 文档里有姓名与联系方式，正式口径不应阻塞
    assert [check for check in body["final_checks"] if check["level"] == "block"] == []


def test_download_headers_are_exposed_to_the_browser() -> None:
    """P08：不暴露 Content-Disposition，前端就只能拿到默认文件名。"""
    from app.main import app

    cors = next(middleware for middleware in app.user_middleware if "CORSMiddleware" in str(middleware))
    options = getattr(cors, "kwargs", {}) or {}
    exposed = options.get("expose_headers") or []
    assert "Content-Disposition" in exposed
    assert "X-Resume-Filename" in exposed
