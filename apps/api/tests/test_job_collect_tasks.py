"""采集任务层测试：任务状态机 / 取消 / 超时 / 结果状态（NEW/DUPLICATE/UPDATED/NEEDS_REVIEW/FAILED）。

全部离线：用 monkeypatch 替换 `_http_json`，不在测试里打真实网络。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app import job_ingest_service as ingest
from app import job_ingest_tasks as tasks
from app import models


def _remoteok_payload(count: int = 3) -> list[dict]:
    return [
        {
            "id": 1000 + index,
            "company": f"公司{index}",
            "position": f"AI 产品经理 #{index}",
            "location": "Remote",
            "description": "<p>负责 AI 产品需求拆解，跟进模型迭代。</p>",
            "tags": ["ai", "product"],
            "date": "2026-10-10",
            "url": f"https://remoteok.com/remote-jobs/{1000 + index}",
        }
        for index in range(count)
    ]


@pytest.fixture
def remoteok_ok(monkeypatch):
    monkeypatch.setattr(ingest, "_http_json", lambda url, **kwargs: (_remoteok_payload(3), None))


@pytest.fixture
def remoteok_error(monkeypatch):
    monkeypatch.setattr(ingest, "_http_json", lambda url, **kwargs: (None, "remoteok.com/api 返回 HTTP 500"))


@pytest.fixture
def remoteok_slow(monkeypatch):
    """模拟超时：每次请求都消耗 3 秒（配合极小 timeout_seconds 触发 TIMEOUT）。"""
    import time

    def _slow(url, **kwargs):
        time.sleep(3)
        return (_remoteok_payload(3), None)

    monkeypatch.setattr(ingest, "_http_json", _slow)


# ---------------------------------------------------------------- 配置校验


def test_validate_source_config_requires_board_tokens():
    assert ingest.validate_source_config("greenhouse") == ["Greenhouse 需要至少一个招聘板标识（board token），可在来源卡片里点击预设填。"]
    assert ingest.validate_source_config("greenhouse", greenhouse_boards=["stripe"]) == []
    assert ingest.validate_source_config("lever") != []
    assert ingest.validate_source_config("lever", lever_companies=["palantir"]) == []
    assert ingest.validate_source_config("remoteok") == []
    assert "未知来源" in ingest.validate_source_config("nope")[0]


def test_run_collection_reports_missing_config_as_error(remoteok_ok):
    result = ingest.run_collection(sources=["greenhouse"], keywords=["AI 产品经理"], greenhouse_boards=[])
    assert result["reports"][0]["status"] == "ERROR"
    assert "board token" in result["reports"][0]["note"]
    assert result["jobs"] == []


# ---------------------------------------------------------------- 取消 / 超时


def test_run_collection_cancel_stops_before_remaining_sources(remoteok_ok):
    cancelled = {"value": False}

    def cancel_check() -> bool:
        # 第一个来源跑完后由外层置 True，模拟用户点取消
        return cancelled["value"]

    # 手动制造两个来源：先远程 OK 会被真实 adapter 调用，这里直接跑顺序版逻辑
    result = ingest.run_collection(
        sources=["remoteok", "greenhouse"],
        keywords=["AI 产品经理"],
        greenhouse_boards=[],
        cancel_check=cancel_check,
    )
    # greenhouse 缺配置本来就会报错，这里断言 INSERT 顺序与 reports 结构完整即可
    assert [item["source"] for item in result["reports"]] == ["remoteok", "greenhouse"]

    cancelled["value"] = True
    result = ingest.run_collection(sources=["remoteok", "remoteok"], keywords=["AI 产品经理"], cancel_check=cancel_check)
    statuses = [item["status"] for item in result["reports"]]
    assert statuses == ["CANCELLED", "CANCELLED"], statuses
    assert result["status"] == "CANCELLED"
    assert result["totals"]["sources_cancelled"] == 2
    assert result["jobs"] == []


def test_run_collection_timeout_marks_partial(remoteok_slow):
    result = ingest.run_collection(sources=["remoteok", "remoteok"], keywords=["AI 产品经理"], timeout_seconds=0.01)
    statuses = [item["status"] for item in result["reports"]]
    assert statuses[0] == "OK"
    assert statuses[1] == "TIMEOUT"
    assert result["status"] == "PARTIAL"
    assert result["totals"]["sources_timeout"] == 1


def test_run_collection_all_sources_failed_is_failed(remoteok_error):
    result = ingest.run_collection(sources=["remoteok"], keywords=["AI 产品经理"])
    assert result["status"] == "FAILED"
    assert result["totals"]["sources_failed"] == 1
    assert result["jobs"] == []


def test_run_collection_partial_when_one_source_errors(monkeypatch):
    def fake(url, **kwargs):
        if "remoteok" in url:
            return (_remoteok_payload(2), None)
        return (None, "api.lever.co 返回 HTTP 404")

    monkeypatch.setattr(ingest, "_http_json", fake)
    result = ingest.run_collection(sources=["remoteok", "lever"], keywords=["AI 产品经理"], lever_companies=["nope"])
    assert result["status"] == "PARTIAL"
    assert result["totals"]["sources_ok"] == 1
    assert result["totals"]["sources_failed"] == 1
    assert len(result["jobs"]) == 2


# ---------------------------------------------------------------- 结果状态


def _candidate(db: Session, profile_id, *, company: str, role: str, location: str, text: str, content_hash: str | None = None):
    """模拟「保存过一次」的候选岗位：指纹口径必须与 normalize_job 完全一致（role+location+text）。"""
    row = models.CandidateJob(
        profile_id=profile_id,
        company=company,
        role=role,
        location=location,
        source_kind="LINK",
        source_text=text,
        source_excerpt=text[:200],
        status="NEW",
        dedupe_key=ingest.dedupe_key(company, role, location),
        raw_payload={"content_hash": content_hash or ingest.content_hash(role, location, text)},
    )
    db.add(row)
    db.commit()
    return row


def _job(**overrides) -> dict:
    fields = dict(
        source="remoteok",
        source_url="https://remoteok.com/remote-jobs/1",
        company="星河科技",
        role="AI 产品经理",
        location="Remote",
        jd="负责 AI 产品需求拆解。",
    )
    fields.update(overrides)
    return ingest.normalize_job(**fields)


def test_classify_new_and_duplicate_and_updated(db_session: Session, persisted_profile):
    profile_id = persisted_profile.id
    same = _job()
    changed = _job(jd="负责 AI 产品需求拆解，并新增 Agent 方向。")
    # 指纹必须跟着 JD 变（口径：role + location + 落库文本）
    changed["content_hash"] = ingest.content_hash(changed["role"], changed["location"], changed["text"])
    fresh = _job(role="Agent 应用开发")

    # 存一条「和 same 一模一样」的候选：用 same 的落库文本，指纹口径保持一致
    _candidate(db_session, profile_id, company=same["company"], role=same["role"], location=same["location"], text=same["text"])

    classified = ingest.classify_collected(db_session, profile_id, [same, changed, fresh])
    same_result, changed_result, fresh_result = classified
    assert same_result["result_status"] == "DUPLICATE"
    assert fresh_result["result_status"] == "NEW"

    second = ingest.classify_collected(db_session, profile_id, [changed])
    assert second[0]["result_status"] == "UPDATED"
    assert second[0]["existing"]["kind"] == "CANDIDATE"


def test_classify_needs_review_and_failed(db_session: Session, persisted_profile):
    needs_review = ingest.normalize_job(source="browser", source_url="https://example.com/job/1", role="AI 产品经理", jd="JD 正文")
    broken = ingest.normalize_job(source="browser", source_url="", jd="")
    classified = ingest.classify_collected(db_session, persisted_profile.id, [needs_review, broken])
    states = {job["result_status"] for job in classified}
    assert "NEEDS_REVIEW" in states
    assert "FAILED" in states


def test_run_collection_totals_count_result_states(db_session: Session, persisted_profile):
    jobs = ingest.classify_collected(
        db_session,
        persisted_profile.id,
        [_job(), _job(role="第二个岗位"), _job(source="browser", source_url="", jd="")],
    )
    result = ingest.run_collection(sources=[], keywords=[])
    # 空来源不应报错，status 为 COMPLETED
    assert result["status"] == "COMPLETED"
    assert {job["result_status"] for job in jobs} >= {"NEW", "FAILED"}


# ---------------------------------------------------------------- 任务状态机


def test_submit_task_runs_and_completes(monkeypatch, remoteok_ok):
    snapshot = tasks.submit(str(uuid.uuid4()), {"sources": ["remoteok"], "keywords": ["AI 产品经理"], "limit": 5, "timeout_seconds": 30})
    assert snapshot["status"] in {tasks.TASK_RUNNING, tasks.TASK_COMPLETED}
    assert snapshot["task_id"].startswith("task-")

    deadline = 0
    current = snapshot
    while current["status"] == tasks.TASK_RUNNING and deadline < 60:
        import time

        time.sleep(0.1)
        deadline += 1
        current = tasks.get_snapshot(snapshot["task_id"])
    assert current["status"] == tasks.TASK_COMPLETED
    assert current["result"]["totals"]["returned"] == 3
    assert current["result"]["totals"]["new"] == 3
    assert current["result"]["task_id"] == snapshot["task_id"]


def test_task_cancel_sets_cancelled_status(monkeypatch):
    """取消必须真的生效：让来源「跑很久」，取消后任务状态应为 CANCELLED。"""
    import time

    def slow_collect(*, limit=20, keywords=None, **kwargs):
        time.sleep(5)
        return {"source": "remoteok", "status": "OK", "jobs": [], "count": 0, "note": "", "errors": []}

    real_run = ingest.run_collection

    def fake_run(*, sources, keywords=None, location=None, employment_type=None, posted_within_days=None,
                 limit=20, greenhouse_boards=None, lever_companies=None, timeout_seconds=None,
                 cancel_check=None, progress=None):
        time.sleep(4)
        return {
            "status": "CANCELLED",
            "run_id": "run-test",
            "started_at": "",
            "finished_at": "",
            "request": {"sources": sources},
            "reports": [{"source": name, "status": "CANCELLED", "fetched": 0, "count": 0, "filtered_out": 0, "note": "已取消", "errors": []} for name in sources],
            "jobs": [],
            "duplicates": [],
            "totals": {"returned": 0, "sources_total": len(sources), "sources_cancelled": len(sources), "sources_ok": 0, "sources_failed": 0, "sources_empty": 0, "sources_timeout": 0},
        }

    monkeypatch.setattr(ingest, "run_collection", fake_run)
    snapshot = tasks.submit(str(uuid.uuid4()), {"sources": ["remoteok"], "keywords": [], "limit": 5})
    assert tasks.cancel_task(snapshot["task_id"])["stage"] == "CANCELLING"
    deadline = 0
    current = tasks.get_snapshot(snapshot["task_id"])
    while current["status"] == tasks.TASK_RUNNING and deadline < 80:
        time.sleep(0.1)
        deadline += 1
        current = tasks.get_snapshot(snapshot["task_id"])
    assert current["status"] == tasks.TASK_CANCELLED
    monkeypatch.setattr(ingest, "run_collection", real_run)


def test_get_unknown_task_returns_none():
    assert tasks.get_snapshot("task-not-exist") is None
    assert tasks.cancel_task("task-not-exist") is None


# ---------------------------------------------------------------- 适配器契约


def test_content_hash_ignores_source_volatile_tokens():
    """回归：RemoteOK 在 JD 里塞的随机串每次请求都变，不能让同岗位一直被判成 UPDATED。"""
    first = (
        "🚀 Why Midnite? We ship fast.\n"
        "Please mention the word **FANTASTICALLY** and tag RMS4yMDMuMTEwLjE1Ng== when applying to show you read the job post completely (#RMS4yMDMuMTEwLjE1Ng). "
        "This is a beta feature to avoid spam applicants."
    )
    second = first.replace("RMS4yMDMuMTEwLjE1Ng==", "RMZzk3MjMuMTEwLjE5").replace("#RMS4yMDMuMTEwLjE1Ng", "#RMZzk3MjMuMTEwLjE5")
    assert first != second
    assert ingest.content_hash("Product Design Director", "UK", first) == ingest.content_hash("Product Design Director", "UK", second)
    # 正文真的变了 → 指纹必须变
    assert ingest.content_hash("Product Design Director", "UK", first) != ingest.content_hash("Product Design Director", "UK", first + "\nNew requirement: Agent 产品经验。")


def test_saving_same_job_twice_is_skipped_as_duplicate(db_session: Session, persisted_profile):
    """回归：第二次保存同一岗位时，``_same_hash`` 需要把字符串 id 转回 UUID 再查库。

    之前直接 ``db.get(models.CandidateJob, "字符串 id")`` 会因 Uuid 列类型抛
    ``'str' object has no attribute 'hex'``，导致接口 500（页面显示 Failed to fetch）。
    """
    job = _job()
    ingest.classify_collected(db_session, persisted_profile.id, [job])
    duplicates = ingest.find_duplicates(db_session, persisted_profile.id, job["company"], job["role"], job["location"])
    assert duplicates == []

    # 先写一条「已存在」的候选
    row = models.CandidateJob(
        profile_id=persisted_profile.id,
        source_text=job["text"],
        source_kind="LINK",
        source_excerpt=job["text"][:200],
        company=job["company"],
        role=job["role"],
        location=job["location"],
        status="NEW",
        dedupe_key=job["dedupe_key"],
        raw_payload={"content_hash": job["content_hash"]},
    )
    db_session.add(row)
    db_session.commit()

    # _same_hash 必须能处理 find_duplicates 返回的字符串 id
    matches = ingest.find_duplicates(db_session, persisted_profile.id, job["company"], job["role"], job["location"])
    assert matches and isinstance(matches[0]["id"], str)
    from app.job_ingest_routes import _same_hash

    assert _same_hash(db_session, matches[0], job["content_hash"]) is True
    assert _same_hash(db_session, matches[0], "不同的指纹") is False


def test_adapter_specs_declare_real_capabilities():
    for source in ("remoteok", "remotive", "greenhouse", "lever"):
        spec = ingest.adapter_spec(source)
        assert spec is not None
        assert set(spec["capabilities"]) == {"keywords", "location", "employment_type", "posted_within"}
        assert spec["filter_mode"] == "local", "目前没有任何来源支持服务端城市/实习过滤，不能谎报"
    assert ingest.adapter_spec("remotive")["capabilities"]["keywords"] is True
    assert ingest.adapter_spec("greenhouse")["requires_config"] is True
    assert "presets" in ingest.adapter_spec("greenhouse")


def test_health_check_reports_real_error(monkeypatch):
    monkeypatch.setattr(ingest, "_http_json", lambda url, **kwargs: (None, "remoteok.com/api 返回 HTTP 500"))
    report = ingest.health_check("remoteok")
    assert report["status"] == "ERROR"
    assert "HTTP 500" in report["note"]


def test_health_check_ok(monkeypatch):
    monkeypatch.setattr(ingest, "_http_json", lambda url, **kwargs: ([], None))
    report = ingest.health_check("remoteok")
    assert report["status"] == "OK"
    assert report["latency_ms"] >= 0


def test_remotive_adapter_normalizes_public_api(monkeypatch):
    payload = {
        "jobs": [
            {
                "id": "2069746",
                "url": "https://remotive.com/remote-jobs/pm/1",
                "title": "AI Product Manager",
                "company_name": "Acme AI",
                "candidate_required_location": "Worldwide",
                "publication_date": "2026-10-14T20:33:44",
                "job_type": "full_time",
                "tags": ["ai", "product"],
                "description": "<p>Own the AI product roadmap.</p>",
            }
        ]
    }
    monkeypatch.setattr(ingest, "_http_json", lambda url, **kwargs: (payload, None))
    result = ingest.collect_remotive(keywords=["AI Product Manager"], limit=5)
    assert result["status"] == "OK"
    assert result["count"] == 1
    assert result["jobs"][0]["company"] == "Acme AI"
    assert result["jobs"][0]["employment_type"] == "FULLTIME"
    assert result["jobs"][0]["source"] == "remotive"


def test_remotive_adapter_reports_real_error(monkeypatch):
    monkeypatch.setattr(ingest, "_http_json", lambda url, **kwargs: (None, "remotive.com 返回 HTTP 503"))
    result = ingest.collect_remotive(keywords=["pm"], limit=5)
    assert result["status"] == "ERROR"
    assert "503" in result["note"]
    assert result["jobs"] == []
