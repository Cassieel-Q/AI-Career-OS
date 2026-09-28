from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.role_exploration_schemas import RoleCode
from app.target_role_service import select_target_role
from test_target_role_service import _ready_profile


@pytest.fixture
def target(db_session, persisted_profile):
    db_session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    _ready_profile(db_session, persisted_profile)
    return select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)


def collection(target_id):
    return f"/api/v1/target-roles/{target_id}/job-descriptions"


def item(jd_id):
    return f"/api/v1/job-descriptions/{jd_id}"


def add(client, target, text="Build AI applications", **kwargs):
    response = client.post(collection(target.id), json={"raw_text": text, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


def test_empty_current_collection_and_first_jd_restore(client, target):
    assert client.get(collection(target.id)).json() == []
    raw = "  Build AI apps\r\nMaintain Python services.  "
    jd = add(client, target, raw)
    assert jd["raw_text"] == raw
    assert jd["source_url"] is None
    assert jd["target_role_id"] == str(target.id)
    assert "content_hash" not in jd
    assert client.get(collection(target.id)).json() == [jd]


@pytest.mark.parametrize("raw", [None, "", " \r\n\t", 42, [], {}])
def test_invalid_raw_create_and_patch(client, target, raw):
    assert client.post(collection(target.id), json={"raw_text": raw}).status_code == 422
    jd = add(client, target)
    assert client.patch(item(jd["id"]), json={"raw_text": raw}).status_code == 422


@pytest.mark.parametrize("url", [None, "", " \n\t", "https://example.com/jobs/1"])
def test_source_url_optional_and_blank_normalization(client, target, url):
    jd = add(client, target, source_url=url)
    assert jd["source_url"] == (url if url and url.strip() else None)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///tmp/a", "not a url", "https://", 42])
def test_bad_source_url_rejected(client, target, url):
    assert client.post(collection(target.id), json={"raw_text": "JD", "source_url": url}).status_code == 422


def test_patch_omission_null_blank_and_hash(client, target, db_session):
    jd = add(client, target, source_url="https://example.com/one")
    row_type = models.JobDescription
    original_hash = db_session.get(row_type, UUID(jd["id"])).content_hash
    changed = client.patch(item(jd["id"]), json={"raw_text": "Build another application"})
    assert changed.status_code == 200
    assert changed.json()["source_url"] == "https://example.com/one"
    db_session.expire_all()
    assert db_session.get(row_type, UUID(jd["id"])).content_hash != original_hash
    for url in [None, "https://example.com/two", " "]:
        response = client.patch(item(jd["id"]), json={"source_url": url})
        assert response.status_code == 200
        assert response.json()["raw_text"] == "Build another application"
        assert response.json()["source_url"] == (url if url and url.strip() else None)
    before_noop = client.get(collection(target.id)).json()[0]
    assert client.patch(item(jd["id"]), json={}).json() == before_noop


def test_exact_duplicate_create_edit_and_distinct_content(client, target):
    first = add(client, target, "Build AI apps\nUse Python")
    duplicate = client.post(collection(target.id), json={
        "raw_text": " \tBuild  AI apps\r\nUse Python  ", "source_url": "https://example.com/other",
    })
    assert duplicate.status_code == 409
    second = add(client, target, "Build AI apps\nUse Rust")
    assert client.patch(item(second["id"]), json={"raw_text": first["raw_text"]}).status_code == 409
    assert client.patch(item(first["id"]), json={"raw_text": first["raw_text"]}).status_code == 200
    add(client, target, "build AI apps\nUse Python")
    add(client, target, "Build AI apps!\nUse Python")
    assert len(client.get(collection(target.id)).json()) == 4


def test_maximum_ten_and_delete_frees_slot(client, target):
    records = [add(client, target, f"Synthetic JD {i}") for i in range(10)]
    assert client.post(collection(target.id), json={"raw_text": "Eleventh"}).status_code == 409
    assert client.patch(item(records[0]["id"]), json={"raw_text": "Edited at ten"}).status_code == 200
    deleted = client.delete(item(records[0]["id"]))
    assert deleted.status_code == 204 and deleted.content == b""
    add(client, target, "Replacement sample")
    assert len(client.get(collection(target.id)).json()) == 10


def test_stable_order_with_timestamp_ties(client, target, db_session):
    saved = [add(client, target, f"JD {i}") for i in range(3)]
    for row in db_session.scalars(select(models.JobDescription)):
        row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.commit()
    assert [row["id"] for row in client.get(collection(target.id)).json()] == sorted(row["id"] for row in saved)


def test_missing_target_or_jd(client):
    assert client.post(collection(uuid4()), json={"raw_text": "JD"}).status_code == 404
    assert client.get(collection(uuid4())).status_code == 404
    assert client.patch(item(uuid4()), json={"raw_text": "JD"}).status_code == 404
    assert client.delete(item(uuid4())).status_code == 404


@pytest.mark.parametrize("extra", ["role_name", "role_profile_version", "role_exploration_id", "target_role_id", "content_hash"])
def test_hidden_state_rejected(client, target, extra):
    assert client.post(collection(target.id), json={"raw_text": "JD", extra: "forged"}).status_code == 422
    jd = add(client, target)
    assert client.patch(item(jd["id"]), json={extra: "forged"}).status_code == 422


def test_stale_context_rejects_all_operations(client, target, db_session, persisted_profile):
    jd = add(client, target)
    persisted_profile.status = "DRAFT"
    db_session.commit()
    assert client.get(collection(target.id)).status_code == 409
    assert client.post(collection(target.id), json={"raw_text": "Other"}).status_code == 409
    assert client.patch(item(jd["id"]), json={"raw_text": "Other"}).status_code == 409
    assert client.delete(item(jd["id"])).status_code == 409


def test_same_role_keeps_samples_but_replacement_is_new_parent(client, target, db_session):
    jd = add(client, target)
    same = select_target_role(db_session, target.profile_id, target.role_code)
    assert same.id == target.id
    assert len(client.get(collection(target.id)).json()) == 1
    replaced = select_target_role(db_session, target.profile_id, RoleCode.AI_DATA_ANALYST)
    assert replaced.id != target.id
    assert client.get(collection(replaced.id)).json() == []
    assert client.post(collection(target.id), json={"raw_text": "Late old request"}).status_code == 404
    assert client.patch(item(jd["id"]), json={"raw_text": "Late edit"}).status_code == 404
    assert client.delete(item(jd["id"])).status_code == 404
    assert list(db_session.scalars(select(models.JobDescription))) == []


def test_preference_invalidation_cascades_through_target_to_jds(client, target, db_session):
    add(client, target)
    response = client.put(f"/api/v1/profiles/{target.profile_id}/preferences", json={
        "priority_order": ["FAST_EMPLOYMENT", "LESS_CODING"], "weekly_hours": 24,
    })
    assert response.status_code == 200
    assert client.get(collection(target.id)).status_code == 404
    assert list(db_session.scalars(select(models.JobDescription))) == []


def test_direct_target_deletion_cascades(client, target, db_session):
    add(client, target)
    db_session.delete(db_session.get(models.TargetRole, target.id))
    db_session.commit()
    assert list(db_session.scalars(select(models.JobDescription))) == []


def test_safe_persistence_failure(client, target, monkeypatch):
    from sqlalchemy.orm import Session

    def fail_commit(self):
        raise SQLAlchemyError("private connection details")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post(collection(target.id), json={"raw_text": "JD"})
    assert response.status_code == 503
    assert "private" not in response.text
