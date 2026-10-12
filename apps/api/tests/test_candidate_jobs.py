"""目标一 · 候选岗位暂存区：拆分可回溯、整篇兜底、不臆造身份、导入幂等。"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.mission_service as mission_service
from app import candidate_job_service as svc
from app import models


TWO_JOBS = """字节跳动 - 产品经理实习生
公司：字节跳动
岗位：产品经理实习生
地点：北京
岗位描述：负责社区产品需求分析与数据复盘，推动跨团队协作落地。

百度 - Agent 产品实习生
公司：百度
岗位：Agent 产品实习生
地点：北京
岗位描述：负责 Agent 产品的对话体验设计与评测，撰写需求文档。
"""


def _stub_create_mission(db, profile_id, payload, provider=None):
    """离线桩：直接建 TargetJob + JobMission，避免真实模型调用。"""
    digest = mission_service.content_hash(payload.raw_text)
    target_job = models.TargetJob(
        profile_id=profile_id, raw_text=payload.raw_text, content_hash=digest, status="CURRENT"
    )
    db.add(target_job)
    db.flush()
    mission = models.JobMission(
        profile_id=profile_id,
        target_job_id=target_job.id,
        display_name="stub",
        company="STUB",
        role="STUB",
        status="DRAFT",
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return {"id": mission.id, "company": mission.company, "role": mission.role}


# ---------------------------------------------------------------------------
# 模型 / 归一化
# ---------------------------------------------------------------------------


def test_candidate_jobs_table_registered() -> None:
    assert "candidate_jobs" in models.Base.metadata.tables
    columns = models.Base.metadata.tables["candidate_jobs"].columns
    for field in [
        "profile_id",
        "source_text",
        "source_hash",
        "source_kind",
        "recognition_source",
        "source_excerpt",
        "company",
        "role",
        "location",
        "raw_payload",
        "status",
        "imported_mission_id",
        "created_at",
        "updated_at",
    ]:
        assert field in columns, f"missing {field}"


def test_normalization_ignores_whitespace_and_width_but_keeps_meaning() -> None:
    assert svc.normalize_for_match("北京 字节") == svc.normalize_for_match("北京\u3000字节")
    assert svc.normalize_for_match("Py-Thon") == svc.normalize_for_match("py-thon")


# ---------------------------------------------------------------------------
# 拆分与回溯
# ---------------------------------------------------------------------------


def test_multi_jd_excerpt_is_traceable_to_source() -> None:
    candidates = svc.build_candidates(TWO_JOBS)
    assert len(candidates) == 2
    for cand in candidates:
        assert cand["recognition_source"] == "HEURISTIC_SPLIT"
        assert svc.excerpt_in_source(cand["source_excerpt"], TWO_JOBS)
    assert candidates[0]["company"] == "字节跳动"
    assert candidates[1]["company"] == "百度"


def test_unreliable_split_returns_single_whole_text_draft() -> None:
    source = (
        "我们在招一个数据分析师负责指标体系搭建与看板开发，"
        "要求熟悉 SQL 与可视化工具，能够独立完成从取数到结论的全流程。"
    )
    candidates = svc.build_candidates(source)
    assert len(candidates) == 1
    assert candidates[0]["recognition_source"] == "WHOLE_TEXT"
    assert candidates[0]["source_excerpt"] == source


def test_identity_is_not_invented_when_absent() -> None:
    block = "岗位描述：负责日常运营数据的整理与周报输出，需要细心，能够"
    candidates = svc.build_candidates(block + "\n配合团队完成月度复盘工作。")
    assert len(candidates) == 1
    assert candidates[0]["company"] == ""
    assert "company_missing" in candidates[0]["warnings"]


def test_parse_is_idempotent_within_same_batch(db_session, persisted_profile) -> None:
    first = svc.parse_candidates(db_session, persisted_profile.id, TWO_JOBS)
    second = svc.parse_candidates(db_session, persisted_profile.id, TWO_JOBS)
    assert [str(r.id) for r in first] == [str(r.id) for r in second]
    rows = svc.list_candidates(db_session, persisted_profile.id)
    assert len(rows) == 2
    assert all(row.status == "DRAFT" for row in rows)


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------


def test_confirm_and_reject_transitions(db_session, persisted_profile) -> None:
    rows = svc.parse_candidates(db_session, persisted_profile.id, TWO_JOBS)
    assert svc.confirm_candidate(db_session, rows[0].id).status == "CONFIRMED"
    assert svc.reject_candidate(db_session, rows[1].id).status == "REJECTED"
    rejected = svc.get_candidate(db_session, rows[1].id)
    with pytest.raises(HTTPException) as exc:
        svc.import_candidate(db_session, rejected.id)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# 导入幂等
# ---------------------------------------------------------------------------


def test_import_is_idempotent(db_session, persisted_profile, monkeypatch) -> None:
    monkeypatch.setattr(mission_service, "create_mission", _stub_create_mission)
    rows = svc.parse_candidates(db_session, persisted_profile.id, TWO_JOBS)
    target = rows[0]
    svc.confirm_candidate(db_session, target.id)

    first = svc.import_candidate(db_session, target.id)
    assert first["status"] == "IMPORTED"
    assert first["reused"] is False

    second = svc.import_candidate(db_session, target.id)
    assert second["mission_id"] == first["mission_id"]
    assert second["reused"] is True

    missions = (
        db_session.query(models.JobMission)
        .filter(models.JobMission.profile_id == persisted_profile.id)
        .all()
    )
    assert len(missions) == 1


def test_import_reuses_existing_mission_by_content_hash(db_session, persisted_profile, monkeypatch) -> None:
    """同一份文本已建过岗时，不重复建岗，直接复用（幂等）。"""
    monkeypatch.setattr(mission_service, "create_mission", _stub_create_mission)
    rows = svc.parse_candidates(db_session, persisted_profile.id, TWO_JOBS)
    created = svc.import_candidate(db_session, rows[0].id)
    existing_mission_id = created["mission_id"]

    # 另造一条候选，但把它伪装成与已导入岗位完全相同的文本
    other = svc.parse_candidates(db_session, persisted_profile.id, TWO_JOBS)[1]
    other.company = rows[0].company
    other.role = rows[0].role
    other.location = rows[0].location
    other.source_excerpt = rows[0].source_excerpt
    db_session.commit()

    result = svc.import_candidate(db_session, other.id)
    assert result["reused"] is True
    assert result["mission_id"] == existing_mission_id


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


def test_candidate_routes_roundtrip(client, persisted_profile) -> None:
    pid = str(persisted_profile.id)
    resp = client.post(f"/api/v1/profiles/{pid}/candidate-jobs/parse", json={"source_text": TWO_JOBS})
    assert resp.status_code == 201, resp.text
    parsed = resp.json()
    assert len(parsed) == 2
    assert all(item["status"] == "DRAFT" for item in parsed)
    assert all(item["source_excerpt"] for item in parsed)

    listed = client.get(f"/api/v1/profiles/{pid}/candidate-jobs").json()
    assert len(listed) == 2

    cid = parsed[0]["id"]
    patched = client.patch(f"/api/v1/candidate-jobs/{cid}", json={"role": "产品经理(改)"})
    assert patched.status_code == 200
    assert patched.json()["role"] == "产品经理(改)"
    assert patched.json()["recognition_source"] == "MANUAL"

    assert client.post(f"/api/v1/candidate-jobs/{cid}/confirm").status_code == 200
    assert client.post(f"/api/v1/candidate-jobs/{parsed[1]['id']}/reject").json()["status"] == "REJECTED"


def test_missing_profile_returns_404(client) -> None:
    resp = client.post(f"/api/v1/profiles/{uuid4()}/candidate-jobs/parse", json={"source_text": TWO_JOBS})
    assert resp.status_code == 404
