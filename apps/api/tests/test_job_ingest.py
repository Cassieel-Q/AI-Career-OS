"""岗位统一入口测试：正文抽取、文件解析、去重、筛选。"""
from __future__ import annotations

import io
import zipfile

from app import job_ingest_service as ingest


def test_html_to_text_strips_scripts_and_keeps_blocks():
    raw = """
    <html><head><title>AI 产品经理 - 示例公司</title>
    <script>var x = '职位：不要出现';</script><style>.a{color:red}</style></head>
    <body><h1>AI 产品经理</h1><p>职责：负责大模型产品</p><ul><li>熟悉 RAG</li><li>有 ToB 经验</li></ul></body></html>
    """
    text = ingest.html_to_text(raw)
    assert "AI 产品经理" in text
    assert "熟悉 RAG" in text
    assert "不要出现" not in text
    assert "color:red" not in text


def test_extract_txt_file():
    text, status = ingest.extract_file_text("jd.txt", "公司：示例\n职位：产品经理".encode("utf-8"))
    assert status == "PARSED" and "产品经理" in text


def test_extract_docx_file():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "word/document.xml",
            "<w:document><w:body><w:p><w:t>公司：示例公司</w:t></w:p><w:p><w:t>职位：AI 产品经理</w:t></w:p></w:body></w:document>",
        )
    text, status = ingest.extract_file_text("jd.docx", buffer.getvalue())
    assert status == "PARSED"
    assert "示例公司" in text and "AI 产品经理" in text


def test_image_is_explicitly_unsupported():
    _text, status = ingest.extract_file_text("jd.png", b"\x89PNG\r\n\x1a\n")
    assert status == "UNSUPPORTED_IMAGE"


def test_dedupe_key_is_stable_and_ignores_spacing():
    a = ingest.dedupe_key("示例公司", "AI 产品经理", "上海")
    b = ingest.dedupe_key(" 示例公司 ", "ai 产品经理", " 上海 ")
    assert a == b
    assert ingest.dedupe_key("示例公司", "算法工程师", "上海") != a


def test_fetch_url_rejects_non_http():
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        ingest.fetch_url_text("ftp://example.com/job")


def test_sources_endpoint_lists_real_adapters(client):
    body = client.get("/api/v1/job-ingest/sources").json()
    ids = {item["id"] for item in body["sources"]}
    # generic_url 已升级为浏览器桥采集来源 browser（见 M1 适配器契约）
    assert {"paste", "browser", "file", "remoteok", "remotive"} <= ids
    remoteok = next(item for item in body["sources"] if item["id"] == "remoteok")
    assert remoteok["auto_collect"] is True


def test_extract_file_endpoint_returns_unsupported_note(client):
    files = {"file": ("jd.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    body = client.post("/api/v1/job-ingest/extract-file", files=files).json()
    assert body["status"] == "UNSUPPORTED_IMAGE"
    assert "OCR" in body["note"]


def test_library_filters_by_keyword_and_company(client, persisted_profile, db_session):
    from app import models

    db_session.add_all(
        [
            models.CandidateJob(
                profile_id=persisted_profile.id,
                source_text="公司：甲公司\n职位：AI 产品经理\n地点：上海",
                source_hash="hash-a",
                source_excerpt="甲公司 AI 产品经理",
                source_excerpt_hash="excerpt-a",
                company="甲公司",
                role="AI 产品经理",
                location="上海",
                source_url="https://example.com/job/1",
                parse_status="PARSED",
            ),
            models.CandidateJob(
                profile_id=persisted_profile.id,
                source_text="公司：乙公司\n职位：算法工程师\n地点：北京",
                source_hash="hash-b",
                source_excerpt="乙公司 算法工程师",
                source_excerpt_hash="excerpt-b",
                company="乙公司",
                role="算法工程师",
                location="北京",
                parse_status="PARSED",
            ),
        ]
    )
    db_session.commit()

    base = f"/api/v1/profiles/{persisted_profile.id}/job-ingest/library"
    all_items = client.get(base).json()
    assert all_items["count"] == 2
    assert "甲公司" in all_items["facets"]["companies"]

    by_keyword = client.get(base, params={"q": "算法"}).json()
    assert by_keyword["count"] == 1 and by_keyword["items"][0]["company"] == "乙公司"

    by_company = client.get(base, params={"company": "甲公司"}).json()
    assert by_company["count"] == 1 and by_company["items"][0]["role"] == "AI 产品经理"

    by_location = client.get(base, params={"location": "北京"}).json()
    assert by_location["count"] == 1 and by_location["items"][0]["company"] == "乙公司"

    assert all_items["items"][0]["source_url"] in (None, "https://example.com/job/1")


def test_save_collected_skips_duplicates(client, persisted_profile, db_session):
    from app import models

    db_session.add(
        models.CandidateJob(
            profile_id=persisted_profile.id,
            source_text="公司：甲公司\n职位：AI 产品经理",
            source_hash="dup-hash",
            source_excerpt="甲公司 AI 产品经理",
            source_excerpt_hash="dup-excerpt",
            company="甲公司",
            role="AI 产品经理",
            location="上海",
        )
    )
    db_session.commit()

    payload = {
        "jobs": [
            {
                "source": "remoteok",
                "source_url": "https://remoteok.com/remote-jobs/1",
                "company": "甲公司",
                "role": "AI 产品经理",
                "location": "上海",
                "text": "公司：甲公司\n职位：AI 产品经理\n地点：上海\n要求：熟悉 RAG",
            }
        ]
    }
    body = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-ingest/save-collected", json=payload).json()
    assert body["saved_count"] == 0
    assert body["skipped_count"] == 1
    # 库里已有记录的正文更短，本次带来了新内容 → 语义是 UPDATED（有更新），不是 DUPLICATE
    assert body["skipped"][0]["reason"] == "UPDATED"

    # 默认不动库里内容 → 再保存一次相同内容仍是 UPDATED；用户选择更新后 → 才变成 DUPLICATE
    body2 = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-ingest/save-collected", json=payload).json()
    assert body2["skipped"][0]["reason"] == "UPDATED"
    body3 = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/job-ingest/save-collected",
        json={**payload, "update_duplicates": True},
    ).json()
    assert body3["updated_count"] == 1
    body4 = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-ingest/save-collected", json=payload).json()
    assert body4["skipped_count"] == 1
    assert body4["skipped"][0]["reason"] == "DUPLICATE"


def test_collected_job_saves_once_and_rerun_is_deduplicated(client, persisted_profile):
    base = f"/api/v1/profiles/{persisted_profile.id}/job-ingest"
    job = {
        "source": "remoteok",
        "source_url": "https://remoteok.com/remote-jobs/999",
        "company": "星野智能",
        "role": "AI 产品经理",
        "location": "上海",
        "collected_at": "2026-10-16T12:00:00+00:00",
        "text": "公司：星野智能\n职位：AI 产品经理\n地点：上海\n职责：负责大模型产品需求拆解与评测方案设计，推动能力落地。",
    }

    first = client.post(f"{base}/save-collected", json={"jobs": [job]}).json()
    assert first["saved_count"] == 1
    assert first["skipped_count"] == 0

    library = client.get(f"{base}/library").json()
    assert library["count"] == 1, "一条采集结果应只落一条候选岗位"
    item = library["items"][0]
    assert item["company"] == "星野智能"
    assert item["source_url"] == job["source_url"]
    assert item["parse_status"] == "PARSED"
    assert item["collected_at"]

    second = client.post(f"{base}/save-collected", json={"jobs": [job]}).json()
    assert second["saved_count"] == 0
    assert second["skipped_count"] == 1
    assert second["skipped"][0]["reason"] == "DUPLICATE"
    assert client.get(f"{base}/library").json()["count"] == 1
