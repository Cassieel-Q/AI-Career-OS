"""无模型建档与本机档案恢复（可信求职 v1.2 · Sprint C · 指令 3.2 / 3.4）。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.local_resume_parse import local_resume_extraction

CLIENT_HEADER = "X-AI-Career-Client"
CLIENT_VALUE = "ai-career-web"

RESUME_TEXT = """张三
zhangsan@example.com 13800138000

教育经历
复旦大学 本科 计算机科学与技术 2021-2025

专业技能
Python、SQL、Figma、数据分析

实习经历
2024.03-2024.09 某某科技 产品实习生
负责需求调研与原型设计，输出 PRD。

证书
CET-6 580 分
"""


def test_local_parse_splits_sections_without_a_model() -> None:
    result = local_resume_extraction(RESUME_TEXT)
    assert any("复旦" in item["institution"] for item in result["education"])
    assert "Python" in [item["name"] for item in result["skills"]]
    assert result["experiences"], "实习经历必须被识别出来"
    assert any("CET-6" in item["name"] for item in result["certifications"])
    assert result["email"] == "zhangsan@example.com"
    assert result["phone"] == "13800138000"


def test_local_parse_never_invents_facts_for_empty_text() -> None:
    result = local_resume_extraction("")
    assert result["education"] == []
    assert result["skills"] == []
    assert result["experiences"] == []
    assert result["certifications"] == []


def test_local_parse_falls_back_when_no_section_headings() -> None:
    text = "某某大学 本科 2020-2024\n2024.03 某某公司 产品实习\n负责需求调研"
    result = local_resume_extraction(text)
    assert result["education"] or result["experiences"], "没有标题时也要做保守兜底"


def test_local_ingest_works_without_any_model_configured(client, persisted_profile) -> None:
    """P01：没配模型也必须能建档，这条路径完全不调 provider。"""
    response = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/resumes/local",
        json={"raw_text": RESUME_TEXT},
        headers={CLIENT_HEADER: CLIENT_VALUE},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parse_source"] == "LOCAL_RULE"
    assert body["parsed_counts"]["skills"] >= 3
    assert body["parsed_counts"]["experiences"] >= 1


def test_local_ingest_rejects_too_short_text(client, persisted_profile) -> None:
    response = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/resumes/local",
        json={"raw_text": "太短"},
        headers={CLIENT_HEADER: CLIENT_VALUE},
    )
    assert response.status_code == 422


def test_local_ingest_requires_client_header(client, persisted_profile) -> None:
    response = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/resumes/local",
        json={"raw_text": RESUME_TEXT},
    )
    assert response.status_code == 403


def test_local_ingest_rejects_cross_site_requests(client, persisted_profile) -> None:
    response = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/resumes/local",
        json={"raw_text": RESUME_TEXT},
        headers={CLIENT_HEADER: CLIENT_VALUE, "sec-fetch-site": "cross-site"},
    )
    assert response.status_code == 403


def test_local_profile_list_is_available_after_clearing_storage(client, persisted_profile, db_session) -> None:
    """P07：清了浏览器存储后，仍然能从服务端读回已有档案。"""
    response = client.get("/api/v1/local/profiles", headers={CLIENT_HEADER: CLIENT_VALUE})
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [item["profile_id"] for item in body["profiles"]]
    assert str(persisted_profile.id) in ids
    # 只给恢复所需的最小信息，不返回简历正文
    for item in body["profiles"]:
        assert set(item) == {"profile_id", "label", "status", "experience_count", "created_at", "updated_at"}
        assert "resume_text" not in item


def test_local_profile_list_requires_client_header(client, persisted_profile) -> None:
    assert client.get("/api/v1/local/profiles").status_code == 403


def test_local_profile_list_rejects_untrusted_origin(client, persisted_profile) -> None:
    response = client.get(
        "/api/v1/local/profiles",
        headers={CLIENT_HEADER: CLIENT_VALUE, "origin": "https://evil.example.com", "sec-fetch-site": "cross-site"},
    )
    assert response.status_code == 403


def test_confirmed_profile_cannot_be_replaced_by_local_ingest(client, db_session, persisted_profile) -> None:
    from app.profile_service import confirm_profile

    confirm_profile(db_session, persisted_profile.id)
    response = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/resumes/local",
        json={"raw_text": RESUME_TEXT},
        headers={CLIENT_HEADER: CLIENT_VALUE},
    )
    assert response.status_code == 409
