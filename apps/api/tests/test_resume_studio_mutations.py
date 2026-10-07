import pytest
from fastapi import HTTPException

from app.resume_studio_service import apply_operation, export_checks, get_or_create_document, read_document
from test_resume_studio_document import _mission_with_resume


def _first_entry(document):
    return next(section for section in document["document"]["sections"] if section["kind"] == "experience")["entries"][0]


def test_stale_revision_does_not_overwrite_a_saved_edit(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    original = read_document(get_or_create_document(db_session, mission.id))
    bullet_id = _first_entry(original)["bullets"][0]["id"]

    saved = apply_operation(db_session, mission.id, 1, {"type": "set_text", "node_id": bullet_id, "text": "Saved wording"})
    with pytest.raises(HTTPException) as caught:
        apply_operation(db_session, mission.id, 1, {"type": "set_text", "node_id": bullet_id, "text": "Stale wording"})

    assert saved["revision"] == 2
    assert caught.value.status_code == 409
    assert _first_entry(read_document(get_or_create_document(db_session, mission.id)))["bullets"][0]["text"] == "Saved wording"


def test_new_metric_requires_fact_confirmation_only_while_included(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    first = read_document(get_or_create_document(db_session, mission.id))
    entry_id = _first_entry(first)["id"]

    added = apply_operation(db_session, mission.id, 1, {"type": "add_bullet", "entry_id": entry_id, "text": "Improved conversion by 37%"})
    new_bullet = _first_entry(added)["bullets"][-1]
    assert new_bullet["claim_status"] == "NEEDS_CONFIRMATION"
    assert new_bullet["risk_level"] == "HIGH"
    assert any(item["node_id"] == new_bullet["id"] and item["level"] == "block" for item in export_checks(added["document"]))

    omitted = apply_operation(db_session, mission.id, 2, {"type": "omit", "node_id": new_bullet["id"]})
    assert not any(item.get("node_id") == new_bullet["id"] for item in export_checks(omitted["document"]))

    restored = apply_operation(db_session, mission.id, 3, {"type": "restore", "node_id": new_bullet["id"]})
    assert any(item.get("node_id") == new_bullet["id"] for item in export_checks(restored["document"]))
    confirmed = apply_operation(db_session, mission.id, 4, {"type": "confirm_fact", "node_id": new_bullet["id"]})
    assert not any(item.get("node_id") == new_bullet["id"] for item in export_checks(confirmed["document"]))


def test_added_entries_and_bullets_keep_ids_when_reordered(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    first = read_document(get_or_create_document(db_session, mission.id))
    section_id = next(section for section in first["document"]["sections"] if section["kind"] == "experience")["id"]

    added = apply_operation(db_session, mission.id, 1, {"type": "add_entry", "section_id": section_id, "title": "New Internship"})
    new_entry = next(section for section in added["document"]["sections"] if section["id"] == section_id)["entries"][-1]
    assert new_entry["title"]["claim_status"] == "NEEDS_CONFIRMATION"
    moved = apply_operation(db_session, mission.id, 2, {"type": "move", "node_id": new_entry["id"], "before_id": _first_entry(added)["id"]})
    entries = next(section for section in moved["document"]["sections"] if section["id"] == section_id)["entries"]
    assert entries[0]["id"] == new_entry["id"]
    assert entries[1]["id"] == _first_entry(added)["id"]


def test_browser_and_agent_share_revisioned_document_endpoint(client, db_session):
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    initial = client.get(base)
    assert initial.status_code == 200
    bullet_id = _first_entry(initial.json())["bullets"][0]["id"]

    saved = client.patch(base, headers={"If-Match": "1"}, json={"type": "set_text", "node_id": bullet_id, "text": "Shared API wording"})
    stale = client.patch(base, headers={"If-Match": "1"}, json={"type": "set_text", "node_id": bullet_id, "text": "Lost wording"})

    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert stale.status_code == 409
    assert stale.json()["detail"]["latest"]["revision"] == 2
    assert _first_entry(client.get(base).json())["bullets"][0]["text"] == "Shared API wording"
