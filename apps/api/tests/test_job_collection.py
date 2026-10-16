"""一键采集引擎测试：统一 Job Schema、多关键词、筛选、Greenhouse/Lever 适配器、网页采集归一化。

全部用离线夹具（monkeypatch `_http_json`），不在测试里打真实网络。
"""
from __future__ import annotations

import pytest

from app import job_ingest_service as ingest


# ---------------------------------------------------------------- Job Schema


def test_normalize_job_produces_unified_schema():
    job = ingest.normalize_job(
        source="remoteok",
        source_url="https://remoteok.com/remote-jobs/1",
        company="星河科技",
        role="AI 产品经理",
        location="Remote",
        jd="负责大模型产品需求拆解。",
        posted_at="2026-10-10",
    )
    assert job["schema"] == ingest.JOB_SCHEMA
    assert job["dedupe_key"] == ingest.dedupe_key("星河科技", "AI 产品经理", "Remote")
    assert job["needs_confirm"] == []
    assert "公司：星河科技" in job["text"]
    assert job["jd_excerpt"].startswith("负责大模型产品")


def test_normalize_job_marks_missing_fields_as_needs_confirm():
    job = ingest.normalize_job(source="browser", role="AI 产品经理", jd="JD 正文")
    assert set(job["needs_confirm"]) == {"company", "location"}


def test_detect_employment_type_intern_and_fulltime():
    assert ingest.detect_employment_type("AI PM Intern", "", "") == "INTERN"
    assert ingest.detect_employment_type("AI 产品经理", "", "本岗位为全职") == "FULLTIME"
    assert ingest.detect_employment_type("算法工程师", "", "") == "UNKNOWN"


# ---------------------------------------------------------------- 多关键词


def test_job_matches_any_keyword_and_supports_chinese():
    job = ingest.normalize_job(source="x", company="星河科技", role="Agent 产品经理", jd="负责 Agent 应用落地")
    # 多关键词取「或」：第二个命中即可
    assert ingest.job_matches(job, ["AI 产品经理", "Agent 产品经理"])
    assert ingest.job_matches(job, ["agent 产品经理"])
    # 完全不同的关键词不应命中
    assert not ingest.job_matches(job, ["AI PM 实习"])
    assert not ingest.job_matches(job, ["前端工程师"])


def test_latin_multiword_keyword_requires_all_tokens():
    job = ingest.normalize_job(source="x", role="Director US Tax & Accounting", jd="We ship product and report to the director.")
    # JD 里只出现部分词元（有 product 没有 manager）→ 不应算命中
    assert ingest.job_match_score(job, "product manager") == 0
    assert ingest.job_matches(job, ["product manager"]) is False
    # 两个词元只在 JD 里共现、岗位名毫无关联 → 不算命中
    loose = ingest.normalize_job(source="x", role="Director US Tax", jd="Works with the product and the manager.")
    assert ingest.job_match_score(loose, "product manager") == 0
    # 岗位名里至少有一个词元 → 算命中
    partial = ingest.normalize_job(source="x", role="Product Operations Lead", jd="Own the roadmap.")
    assert ingest.job_match_score(partial, "product manager") >= 1


def test_job_match_score_prefers_title_hit():
    en = ingest.normalize_job(source="x", role="Product Manager, AI", jd="Own roadmap.")
    assert ingest.job_match_score(en, "product manager") == 3
    zh = ingest.normalize_job(source="x", role="AI 产品经理", jd="负责大模型产品。")
    assert ingest.job_match_score(zh, "AI 产品经理") == 3
    assert ingest.job_match_score(zh, "product manager") == 0


def test_rank_jobs_puts_title_matches_first():
    jobs = [
        ingest.normalize_job(source="x", role="Tax Director", jd="product manager mentioned once"),
        ingest.normalize_job(source="x", role="Product Manager", jd="Anything."),
    ]
    ranked = ingest.rank_jobs(jobs, ["product manager"])
    assert ranked[0]["role"] == "Product Manager"


def test_job_matches_empty_keywords_returns_true():
    job = ingest.normalize_job(source="x", role="任意岗位")
    assert ingest.job_matches(job, []) is True


def test_job_matches_english_token_does_not_hit_unrelated_jd():
    job = ingest.normalize_job(source="x", role="Product Manager", jd="We build infrastructure.")
    assert ingest.job_matches(job, ["product manager"])
    assert not ingest.job_matches(job, ["quantitative trading"])


# ---------------------------------------------------------------- 筛选


def test_filter_jobs_by_location_employment_and_posted_days():
    jobs = [
        ingest.normalize_job(source="x", role="AI 实习", location="北京", employment_type="INTERN", posted_at="2026-10-01"),
        ingest.normalize_job(source="x", role="AI 全职", location="上海", employment_type="FULLTIME", posted_at="2026-10-01"),
        ingest.normalize_job(source="x", role="AI 老岗位", location="北京", employment_type="FULLTIME", posted_at="2020-01-01"),
    ]
    assert len(ingest.filter_jobs(jobs, location="北京")) == 2
    assert [item["role"] for item in ingest.filter_jobs(jobs, employment_type="INTERN")] == ["AI 实习"]
    assert [item["role"] for item in ingest.filter_jobs(jobs, posted_within_days=30)] == ["AI 实习", "AI 全职"]
    # 北京 + 全职：只有「AI 老岗位」同时满足（发布时间筛选在上面单独验证）
    assert [item["role"] for item in ingest.filter_jobs(jobs, location="北京", employment_type="FULLTIME")] == ["AI 老岗位"]


def test_filter_jobs_keeps_unknown_posted_at():
    jobs = [ingest.normalize_job(source="x", role="无发布时间")]
    assert len(ingest.filter_jobs(jobs, posted_within_days=7)) == 1


# ---------------------------------------------------------------- RemoteOK


def test_collect_remoteok_filters_by_keywords(monkeypatch):
    payload = [
        {"id": "legal"},  # RemoteOK 首条是法律声明，须被跳过
        {
            "id": "1",
            "company": "Thyme Care",
            "position": "Product Manager, AI",
            "location": "Remote",
            "tags": ["product", "ai"],
            "description": "<p>Build AI features.</p>",
            "date": "2026-10-12",
            "url": "https://remoteok.com/remote-jobs/1",
        },
        {
            "id": "2",
            "company": "Other",
            "position": "Staff SRE",
            "location": "Remote",
            "tags": ["devops"],
            "description": "Run clusters.",
            "date": "2026-10-12",
            "url": "https://remoteok.com/remote-jobs/2",
        },
    ]
    monkeypatch.setattr(ingest, "_http_json", lambda url, timeout=20.0: (payload, None))
    result = ingest.collect_remoteok(keywords=["product manager"], limit=10)
    assert result["status"] == "OK"
    assert result["count"] == 1
    assert result["jobs"][0]["role"] == "Product Manager, AI"
    assert result["jobs"][0]["source"] == "remoteok"


def test_collect_remoteok_reports_real_http_error(monkeypatch):
    monkeypatch.setattr(ingest, "_http_json", lambda url, timeout=20.0: (None, "RemoteOK 返回 HTTP 503"))
    result = ingest.collect_remoteok(limit=5)
    assert result["status"] == "ERROR"
    assert result["jobs"] == []
    assert "503" in result["note"]


# ---------------------------------------------------------------- Greenhouse


def test_collect_greenhouse_maps_board_payload(monkeypatch):
    payload = {
        "jobs": [
            {
                "id": 10,
                "title": "Product Manager, AI",
                "absolute_url": "https://boards.greenhouse.io/stripe/jobs/10",
                "content": "<p>Own AI product surface.</p>",
                "location": {"name": "Remote"},
                "updated_at": "2026-10-09T10:00:00-04:00",
            },
            {
                "id": 11,
                "title": "Engineering Intern, Platform",
                "absolute_url": "https://boards.greenhouse.io/stripe/jobs/11",
                "content": "<p>Intern project.</p>",
                "location": {"name": "San Francisco"},
                "updated_at": "2026-10-09T10:00:00-04:00",
            },
        ]
    }
    monkeypatch.setattr(ingest, "_http_json", lambda url, timeout=20.0: (payload, None))
    result = ingest.collect_greenhouse(boards=["stripe"], limit=10, keywords=["product manager"])
    assert result["status"] == "OK"
    assert result["count"] == 1
    job = result["jobs"][0]
    assert job["role"] == "Product Manager, AI"
    assert job["location"] == "Remote"
    # 公开接口不返回公司名 → 用招聘板标识占位并标记待确认
    assert job["company"] == "stripe"
    assert "company" in job["needs_confirm"]


def test_collect_greenhouse_reports_404_as_real_error(monkeypatch):
    monkeypatch.setattr(
        ingest,
        "_http_json",
        lambda url, timeout=20.0: (None, "https://boards-api.greenhouse.io/v1/boards/nope/jobs?content=true 返回 HTTP 404"),
    )
    result = ingest.collect_greenhouse(boards=["nope"], limit=5)
    assert result["status"] == "ERROR"
    assert result["count"] == 0
    assert "404" in result["note"]
    assert result["jobs"] == []


def test_collect_greenhouse_requires_board_tokens():
    result = ingest.collect_greenhouse(boards=[], limit=5)
    assert result["status"] == "EMPTY"
    assert "招聘板标识" in result["note"]


# ---------------------------------------------------------------- Lever


def test_collect_lever_maps_postings(monkeypatch):
    payload = [
        {
            "id": "a",
            "text": "AI Product Manager Intern",
            "hostedUrl": "https://jobs.lever.co/demo/a",
            "applyUrl": "https://jobs.lever.co/demo/a/apply",
            "descriptionPlain": "Work on AI features.",
            "categories": {"location": "Remote", "commitment": "Intern", "team": "Product"},
            "createdAt": 1760000000000,
        }
    ]
    monkeypatch.setattr(ingest, "_http_json", lambda url, timeout=20.0: (payload, None))
    result = ingest.collect_lever(companies=["leverdemo"], limit=10)
    assert result["status"] == "OK"
    job = result["jobs"][0]
    assert job["company"] == "leverdemo"
    assert job["employment_type"] == "INTERN"
    assert job["location"] == "Remote"
    assert job["posted_at"] is not None


# ---------------------------------------------------------------- 统一采集


def test_run_collection_aggregates_per_source_report(monkeypatch):
    def fake(url, timeout=20.0):
        if "remoteok" in url:
            return (
                [
                    {
                        "id": "1",
                        "company": "星河科技",
                        "position": "AI Product Manager",
                        "location": "Remote",
                        "tags": ["ai"],
                        "description": "Build AI.",
                        "date": "2026-10-12",
                        "url": "https://remoteok.com/remote-jobs/1",
                    }
                ],
                None,
            )
        if "greenhouse" in url:
            return ({"jobs": [{"id": 5, "title": "AI Product Manager", "absolute_url": "u", "content": "<p>x</p>", "location": {"name": "Remote"}, "updated_at": "2026-10-12"}]}, None)
        return (None, "返回 HTTP 404")

    monkeypatch.setattr(ingest, "_http_json", fake)
    result = ingest.run_collection(
        sources=["remoteok", "greenhouse", "lever"],
        keywords=["AI Product Manager"],
        limit=20,
        lever_companies=["missing-co"],
        greenhouse_boards=["stripe"],
    )
    assert result["totals"]["sources_ok"] == 2
    assert result["totals"]["sources_failed"] == 1
    by_source = {item["source"]: item for item in result["reports"]}
    assert by_source["lever"]["status"] == "ERROR"
    assert "404" in by_source["lever"]["note"]
    # 公司名不同（一个来自接口、一个是 board token 占位），不应判为跨来源重复
    assert result["totals"]["cross_source_duplicates"] == 0
    assert result["totals"]["returned"] == 2


def test_run_collection_unknown_source_is_reported_not_swallowed():
    result = ingest.run_collection(sources=["nope"], limit=5)
    assert result["reports"][0]["status"] == "ERROR"
    assert "未知来源" in result["reports"][0]["note"]
    assert result["jobs"] == []


def test_run_collection_removes_cross_source_duplicates(monkeypatch):
    def fake(url, timeout=20.0):
        return (
            [
                {
                    "id": "1",
                    "company": "星河科技",
                    "position": "AI PM",
                    "location": "Remote",
                    "tags": [],
                    "description": "same job",
                    "url": "https://remoteok.com/remote-jobs/1",
                }
            ],
            None,
        )

    monkeypatch.setattr(ingest, "_http_json", fake)
    result = ingest.run_collection(sources=["remoteok", "remoteok"], limit=20)
    assert result["totals"]["returned"] == 1
    assert result["totals"]["cross_source_duplicates"] == 1


# ---------------------------------------------------------------- 网页采集归一化


def test_normalize_browser_capture_keeps_low_confidence_as_needs_confirm():
    job = ingest.normalize_browser_capture(
        {
            "page_url": "https://example.com/jobs/1",
            "page_title": "AI 产品经理",
            "company": "",
            "role": "AI 产品经理",
            "location": "北京",
            "jd": "负责大模型产品。",
            "confidence": {"company": "MISSING", "role": "HIGH", "location": "HIGH", "jd": "LOW"},
            "extraction": "dom",
        }
    )
    assert job["source"] == "browser"
    assert set(job["needs_confirm"]) == {"company", "jd"}
    assert job["raw"]["extraction"] == "dom"


# ---------------------------------------------------------------- 路由


def test_collect_endpoint_returns_report_shape(client, monkeypatch):
    monkeypatch.setattr(
        ingest,
        "run_collection",
        lambda **kwargs: {
            "run_id": "run-test",
            "reports": [{"source": "remoteok", "status": "OK", "count": 1, "note": ""}],
            "jobs": [ingest.normalize_job(source="remoteok", company="A", role="B", location="Remote", jd="C")],
            "duplicates": [],
            "totals": {"returned": 1, "cross_source_duplicates": 0, "sources_ok": 1, "sources_failed": 0, "sources_empty": 0},
            "started_at": "x",
            "finished_at": "y",
            "request": {},
        },
    )
    body = client.post(
        "/api/v1/job-ingest/collect",
        json={"keywords": ["AI 产品经理"], "sources": ["remoteok"], "limit": 10},
    ).json()
    assert body["totals"]["returned"] == 1
    assert body["jobs"][0]["jd_excerpt"] == "C"


def test_collect_browser_returns_503_when_bridge_down(client, monkeypatch):
    from app import webform_browser as browser

    def boom():
        raise browser.BrowserBridgeError("受控浏览器未启动或不可达")

    monkeypatch.setattr(browser, "extract_job", boom)
    response = client.post("/api/v1/job-ingest/collect-browser")
    assert response.status_code == 503


def test_collect_browser_preview_does_not_persist(client, monkeypatch, persisted_profile, db_session):
    from app import models, webform_browser as browser
    from sqlalchemy import select

    monkeypatch.setattr(
        browser,
        "extract_job",
        lambda: {
            "status": "OK",
            "page_url": "https://example.com/jobs/9",
            "page_title": "AI 产品经理 - 示例",
            "company": "示例科技",
            "role": "AI 产品经理",
            "location": "北京",
            "jd": "负责大模型产品需求拆解。",
            "confidence": {"company": "HIGH", "role": "HIGH", "location": "HIGH", "jd": "HIGH"},
            "extraction": "jsonld",
        },
    )
    body = client.post("/api/v1/job-ingest/collect-browser").json()
    assert body["status"] == "OK"
    assert body["job"]["company"] == "示例科技"
    # 预览不应该写库
    rows = db_session.scalars(select(models.CandidateJob).where(models.CandidateJob.profile_id == persisted_profile.id)).all()
    assert len(rows) == 0


def test_collect_browser_blocked_page_is_reported(client, monkeypatch):
    from app import webform_browser as browser

    monkeypatch.setattr(
        browser,
        "extract_job",
        lambda: {"status": "BLOCKED", "page_url": "https://example.com/login", "page_title": "登录", "note": "需要登录"},
    )
    body = client.post("/api/v1/job-ingest/collect-browser").json()
    assert body["status"] == "BLOCKED"
    assert body["job"] is None
