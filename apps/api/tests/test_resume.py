from io import BytesIO

import fitz
from fastapi.testclient import TestClient

from app import main
from app.main import ResumeExtractionResult, app, set_resume_provider


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
            education=[{"institution": "Example University", "degree": "MSc", "evidence_text": "MSc"}],
            skills=[{"name": "Python", "evidence_text": "Python", "proficiency": None}],
            experiences=[{"title": "Research Assistant", "organization": "Lab", "evidence_text": "Research Assistant"}],
            certifications=[],
        )


class FabricatedEvidenceProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Fabricated evidence"}])


def test_valid_text_pdf_returns_draft_profile_with_evidence() -> None:
    set_resume_provider(MockResumeProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("MSc Python Research Assistant")), "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["skills"][0]["evidence_text"] == "Python"
    assert body["skills"][0]["proficiency"] is None


def test_non_pdf_is_rejected() -> None:
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.txt", BytesIO(b"not a pdf"), "text/plain")},
    )
    assert response.status_code == 415


def test_pdf_without_extractable_text_is_rejected() -> None:
    document = fitz.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("scan.pdf", BytesIO(data), "application/pdf")},
    )
    assert response.status_code == 422
    assert "extractable text" in response.json()["detail"]


def test_text_extraction_failure_is_rejected_as_client_error(monkeypatch) -> None:
    class BrokenDocument:
        def __iter__(self):
            return iter([object()])

        def close(self) -> None:
            pass

    monkeypatch.setattr(main.fitz, "open", lambda **_: BrokenDocument())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(b"valid-looking input"), "application/pdf")},
    )
    assert response.status_code == 422
    assert "extract" in response.json()["detail"].lower()


def test_provider_evidence_must_come_from_pdf_text() -> None:
    set_resume_provider(FabricatedEvidenceProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Python")), "application/pdf")},
    )
    assert response.status_code == 502
    assert "evidence" in response.json()["detail"].lower()


def test_resume_schema_rejects_missing_evidence() -> None:
    try:
        ResumeExtractionResult(skills=[{"name": "Python"}])
    except Exception as error:
        assert "evidence_text" in str(error)
    else:
        raise AssertionError("missing evidence_text should fail validation")


def test_unconfigured_provider_returns_explicit_service_error() -> None:
    set_resume_provider(None)
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("MSc Python")), "application/pdf")},
    )
    assert response.status_code == 503
