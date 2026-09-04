from io import BytesIO

import fitz
from fastapi.testclient import TestClient

from app.main import ResumeExtractionResult, set_resume_provider


def pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


class MockResumeProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(
            education=[{"institution": "Example University", "degree": "MSc", "evidence_text": "Example University MSc"}],
            skills=[{"name": "Python", "evidence_text": "Python", "proficiency": None}],
            experiences=[{"title": "Research Assistant", "organization": "Lab", "evidence_text": "Research Assistant Lab"}],
            certifications=[],
        )


def upload_mock_resume(client: TestClient):
    set_resume_provider(MockResumeProvider())
    return client.post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Example University MSc Python Research Assistant Lab")), "application/pdf")},
    )


def test_resume_upload_persists_draft_profile(client: TestClient) -> None:
    response = upload_mock_resume(client)

    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"]
    assert body["status"] == "DRAFT"
    assert body["skills"][0]["proficiency"] is None
    assert body["skills"][0]["source_type"] == "AI_EXTRACTED"


def test_profile_can_be_read(client: TestClient, persisted_profile) -> None:
    response = client.get(f"/api/v1/profiles/{persisted_profile.id}")

    assert response.status_code == 200
    assert response.json()["profile_id"] == str(persisted_profile.id)
    assert response.json()["education"][0]["institution"] == "Example University"


def test_normalized_courses_and_experience_type_are_persisted(client: TestClient, persisted_profile) -> None:
    education_id = str(persisted_profile.education[0].id)
    experience_id = str(persisted_profile.experiences[0].id)
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}",
        json={
            "education": [
                {
                    "id": education_id,
                    "institution": "Example University",
                    "relevant_courses": ["Machine Learning", "Database Systems"],
                }
            ],
            "experiences": [
                {
                    "id": experience_id,
                    "title": "Research Assistant",
                    "experience_type": "PROJECT",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["education"][0]["relevant_courses"] == ["Machine Learning", "Database Systems"]
    assert response.json()["experiences"][0]["experience_type"] == "PROJECT"

    reloaded = client.get(f"/api/v1/profiles/{persisted_profile.id}")
    assert reloaded.json()["education"][0]["relevant_courses"] == ["Machine Learning", "Database Systems"]
    assert reloaded.json()["experiences"][0]["experience_type"] == "PROJECT"


def test_put_edits_adds_and_deletes_items(client: TestClient, persisted_profile) -> None:
    original_skill_id = str(persisted_profile.skills[0].id)
    payload = {
        "education": [],
        "skills": [
            {
                "id": original_skill_id,
                "name": "Python 3",
                "evidence_text": "Python",
                "source_type": "USER_EDITED",
                "proficiency": "PROJECT_READY",
            },
            {"name": "SQL", "source_type": "USER_ENTERED", "proficiency": "BASIC"},
        ],
        "experiences": [],
        "certifications": [{"name": "AWS CCP", "source_type": "USER_ENTERED"}],
    }

    response = client.put(f"/api/v1/profiles/{persisted_profile.id}", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DRAFT"
    assert {skill["name"] for skill in body["skills"]} == {"Python 3", "SQL"}
    assert body["skills"][0]["proficiency"] in {"PROJECT_READY", "BASIC"}
    edited_skill = next(skill for skill in body["skills"] if skill["name"] == "Python 3")
    assert edited_skill["source_type"] == "USER_EDITED"
    assert body["certifications"][0]["evidence_text"] is None
    assert body["certifications"][0]["source_type"] == "USER_ENTERED"


def test_credential_score_and_status_survive_profile_round_trip(client: TestClient, persisted_profile) -> None:
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}",
        json={"certifications": [{"name": "CET-6", "score": "300", "status": None}]},
    )

    assert response.status_code == 200
    assert response.json()["certifications"][0]["score"] == "300"
    assert response.json()["certifications"][0]["status"] is None

    reloaded = client.get(f"/api/v1/profiles/{persisted_profile.id}")
    assert reloaded.json()["certifications"][0]["score"] == "300"


def test_existing_ai_evidence_is_server_owned_and_edit_becomes_user_edited(
    client: TestClient, persisted_profile
) -> None:
    original_skill = persisted_profile.skills[0]
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}",
        json={"skills": [{"id": str(original_skill.id), "name": "Python 3"}]},
    )

    assert response.status_code == 200
    edited_skill = response.json()["skills"][0]
    assert edited_skill["evidence_text"] == "Python"
    assert edited_skill["source_type"] == "USER_EDITED"


def test_existing_ai_evidence_cannot_be_replaced_by_put(client: TestClient, persisted_profile) -> None:
    original_skill = persisted_profile.skills[0]
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}",
        json={
            "skills": [
                {
                    "id": str(original_skill.id),
                    "name": original_skill.name,
                    "evidence_text": "Untrusted replacement",
                    "source_type": "USER_EDITED",
                }
            ]
        },
    )

    assert response.status_code == 200
    returned_skill = response.json()["skills"][0]
    assert returned_skill["evidence_text"] == "Python"
    assert returned_skill["source_type"] == "AI_EXTRACTED"


def test_invalid_proficiency_is_rejected(client: TestClient, persisted_profile) -> None:
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}",
        json={"skills": [{"name": "Python", "proficiency": "EXPERT"}]},
    )

    assert response.status_code == 422


def test_confirm_changes_state_and_reads_back(client: TestClient, persisted_profile) -> None:
    response = client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm")

    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
    assert client.get(f"/api/v1/profiles/{persisted_profile.id}").json()["status"] == "CONFIRMED"


def test_confirm_rejects_empty_profile(client: TestClient, db_session) -> None:
    from app.models import UserProfile

    profile = UserProfile()
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    response = client.post(f"/api/v1/profiles/{profile.id}/confirm")

    assert response.status_code == 422


def test_confirmed_profile_cannot_be_edited(client: TestClient, persisted_profile) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200

    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}",
        json={"skills": [{"name": "Python", "source_type": "USER_ENTERED"}]},
    )

    assert response.status_code == 409
