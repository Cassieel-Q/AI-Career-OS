"""M3 求职管理补齐：投递版本绑定 / PDF 快照 / 打招呼话术 / 看板聚合。

核心契约：
- 「我当初投的是哪份简历」必须可回答：绑定 resume_version_id + studio_revision + PDF 快照。
- 只能绑定 Studio 已确认的版本（投出去的必须是用户确认过的内容）。
- 打招呼话术只引用真实事实（档案/已确认简历/JD 解析），不编造、不自动发送。
- 看板复用 JobApplication / InterviewRecord / Reminder，不建第二套事实来源。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app import models
from test_resume_studio_document import _mission_with_resume


@pytest.fixture(autouse=True)
def configure_typst(monkeypatch):
    binary = Path(__file__).resolve().parents[3] / ".runtime" / "typst-0.15.1" / "typst-x86_64-pc-windows-msvc" / "typst.exe"
    if binary.exists():
        monkeypatch.setenv("TYPST_BIN", str(binary))


@pytest.fixture()
def snapshot_dir(tmp_path, monkeypatch):
    from app import local_mode

    monkeypatch.setenv(local_mode.DATASET_ENV, str(tmp_path))
    return tmp_path / "pdf_snapshots"


def _confirmed_studio(client, db_session, mission) -> dict:
    """把 mission 推进到「Studio 已确认」：确认定向简历 → Studio 初始导入 → 确认。"""
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    client.post(f"/api/v1/job-missions/{mission.id}/confirm-target-resume", json={})
    doc = client.get(base).json()
    confirmed = client.post(f"{base}/confirm", headers={"If-Match": str(doc["revision"])})
    assert confirmed.status_code == 200, confirmed.json()
    return confirmed.json()


def _make_application(client, db_session, profile) -> dict:
    response = client.post(
        f"/api/v1/profiles/{profile.id}/applications",
        json={"company": "甲公司", "role": "后端开发工程师", "location": "深圳", "channel": "内推"},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def _bindable_mission(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    mission.resume_source = {"profile_id": str(mission.profile_id)}
    mission.workflow_state = "TARGET_RESUME_DRAFT"
    db_session.commit()
    return mission


def test_bind_resume_records_version_revision_and_pdf_snapshot(client, db_session, persisted_profile, snapshot_dir):
    mission = _bindable_mission(db_session)
    confirmed = _confirmed_studio(client, db_session, mission)
    application = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/applications",
        json={"company": "甲公司", "role": "后端开发工程师", "location": "深圳", "channel": "内推", "mission_id": str(mission.id)},
    ).json()

    bound = client.post(f"/api/v1/applications/{application['id']}/bind-resume", json={})
    assert bound.status_code == 200, bound.json()
    body = bound.json()
    assert body["resume_version_id"]
    assert body["studio_revision"] == confirmed["revision"]
    assert body["has_pdf_snapshot"] is True
    snapshot = Path(body["pdf_snapshot_path"])
    assert snapshot.exists() and snapshot.read_bytes()[:4] == b"%PDF"

    # 回答「我当初投的是哪份简历」：下载快照是同一份 PDF
    download = client.get(f"/api/v1/applications/{application['id']}/resume-snapshot")
    assert download.status_code == 200
    assert download.content[:4] == b"%PDF"
    assert download.headers["content-type"].startswith("application/pdf")


def test_bind_resume_requires_confirmed_studio_revision(client, db_session, persisted_profile, snapshot_dir):
    mission = _bindable_mission(db_session)
    client.post(f"/api/v1/job-missions/{mission.id}/confirm-target-resume", json={})
    # Studio 只导入、不确认 → 绑定必须被拒绝（投出去的必须是确认过的内容）
    application = _make_application(client, db_session, persisted_profile)
    bound = client.post(f"/api/v1/applications/{application['id']}/bind-resume", json={})
    assert bound.status_code == 409
    assert "确认" in bound.json()["detail"]["message"] if isinstance(bound.json()["detail"], dict) else "确认" in str(bound.json()["detail"])


def test_bind_resume_without_any_confirmed_resume_is_rejected(client, db_session, persisted_profile, snapshot_dir):
    mission, _, _ = _mission_with_resume(db_session)
    mission.resume_source = {"profile_id": str(mission.profile_id)}
    mission.workflow_state = "RESUME_STRATEGY_CONFIRMED"
    db_session.commit()
    application = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/applications",
        json={"company": "乙公司", "role": "数据分析师", "mission_id": str(mission.id)},
    ).json()
    bound = client.post(f"/api/v1/applications/{application['id']}/bind-resume", json={})
    assert bound.status_code == 409


def test_greeting_generation_only_uses_real_facts(client, db_session, persisted_profile, snapshot_dir):
    mission = _bindable_mission(db_session)
    _confirmed_studio(client, db_session, mission)
    application = _make_application(client, db_session, persisted_profile)

    generated = client.post(f"/api/v1/applications/{application['id']}/greeting")
    assert generated.status_code == 200, generated.json()
    body = generated.json()
    assert body["greeting_short"], "必须生成简洁版"
    assert body["greeting_long"], "必须生成详细版"
    # 话术引用真实姓名与岗位（来自档案与投递记录），不编造
    assert "后端开发工程师" in body["greeting_short"]
    assert "甲公司" in body["greeting_long"]
    # 不编造具体数字承诺
    for banned in ("提升300%", "增长10倍", "年薪"):
        assert banned not in body["greeting_short"]

    # 可编辑：用户改完保存，接口按用户版本返回
    updated = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"greeting_short": "您好，我对这个岗位很感兴趣，简历已附上。"},
    )
    assert updated.status_code == 200
    assert updated.json()["greeting_short"] == "您好，我对这个岗位很感兴趣，简历已附上。"


def test_greeting_fallback_when_no_resume_yet(client, db_session, persisted_profile):
    application = _make_application(client, db_session, persisted_profile)
    generated = client.post(f"/api/v1/applications/{application['id']}/greeting")
    assert generated.status_code == 200
    body = generated.json()
    # 没有简历事实时如实降级：不虚构经历，只保留姓名 + 岗位 + 附件指引
    assert "后端开发工程师" in body["greeting_short"]
    assert body["greeting_long"]


def test_board_aggregates_columns_versions_interviews_and_reminders(client, db_session, persisted_profile, snapshot_dir):
    mission = _bindable_mission(db_session)
    _confirmed_studio(client, db_session, mission)
    application = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/applications",
        json={"company": "甲公司", "role": "后端开发工程师", "location": "深圳", "channel": "内推", "mission_id": str(mission.id)},
    ).json()
    bound = client.post(f"/api/v1/applications/{application['id']}/bind-resume", json={}).json()
    client.post(f"/api/v1/applications/{application['id']}/greeting")

    db_session.add(
        models.InterviewRecord(
            profile_id=persisted_profile.id,
            company="甲公司",
            role="后端开发工程师",
            interview_round="一面",
            interviewed_on=date.today(),
            notes="算法题 + 项目深挖",
        )
    )
    db_session.add(
        models.Reminder(
            profile_id=persisted_profile.id,
            title="跟进甲公司 HR",
            due_at=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    board = client.get(f"/api/v1/profiles/{persisted_profile.id}/applications/board")
    assert board.status_code == 200, board.json()
    data = board.json()
    assert data["total"] == 1
    assert data["columns"]["PENDING"]["count"] == 1
    # 版本使用记录：能回答「这版简历投过哪些岗位」
    usage = data["version_usage"]
    assert len(usage) == 1
    assert usage[0]["resume_version_id"] == bound["resume_version_id"]
    assert usage[0]["used_by"][0]["company"] == "甲公司"
    # 最近面试 + 提醒（应用内提醒，明确不宣称系统推送）
    assert data["recent_interviews"][0]["company"] == "甲公司"
    assert data["recent_interviews"][0]["interview_round"] == "一面"
    assert data["reminders"][0]["title"] == "跟进甲公司 HR"
    assert "不" in data["reminder_note"]


def test_application_read_exposes_jd_source(client, db_session, persisted_profile):
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/applications",
        json={"company": "丙公司", "role": "测试开发", "jd_source": "https://example.com/jd/9"},
    )
    assert created.status_code == 201
    assert created.json()["jd_source"] == "https://example.com/jd/9"


def test_reminder_crud_and_board_visibility(client, db_session, persisted_profile):
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/reminders",
        json={"title": "一面后 24 小时内发感谢信", "due_at": "2026-10-21T09:00:00Z"},
    )
    assert created.status_code == 201, created.json()
    reminder = created.json()
    assert reminder["status"] == "PENDING"

    listed = client.get(f"/api/v1/profiles/{persisted_profile.id}/reminders").json()
    assert any(item["title"] == "一面后 24 小时内发感谢信" for item in listed)

    done = client.post(f"/api/v1/reminders/{reminder['id']}/complete")
    assert done.status_code == 200
    assert done.json()["status"] == "DONE"
