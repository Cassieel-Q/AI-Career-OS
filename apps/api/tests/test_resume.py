from io import BytesIO
import sys
from types import SimpleNamespace

import fitz
import pytest
from fastapi import HTTPException
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
            education=[{"institution": "Example University", "degree": "MSc", "evidence_text": "Example University MSc"}],
            skills=[{"name": "Python", "evidence_text": "Python", "proficiency": None}],
            experiences=[{"title": "Research Assistant", "organization": "Lab", "evidence_text": "Research Assistant Lab"}],
            certifications=[],
        )


class FabricatedEvidenceProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Fabricated evidence"}])


class UnsupportedFactProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(skills=[{"name": "Kubernetes", "evidence_text": "Python"}])


def test_valid_text_pdf_returns_draft_profile_with_evidence() -> None:
    set_resume_provider(MockResumeProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Example University MSc Python Research Assistant Lab")), "application/pdf")},
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


def test_provider_fact_must_be_supported_by_its_evidence() -> None:
    set_resume_provider(UnsupportedFactProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Python")), "application/pdf")},
    )
    assert response.status_code == 502
    assert "evidence" in response.json()["detail"].lower()


def test_evidence_matching_accepts_exact_excerpt() -> None:
    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

    assert main.validate_evidence_trace(result, "Python") is result


def test_evidence_matching_accepts_pdf_line_break_as_space() -> None:
    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python Developer"}])

    assert main.validate_evidence_trace(result, "Python\nDeveloper") is result


def test_evidence_matching_accepts_repeated_whitespace() -> None:
    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python SQL"}])

    assert main.validate_evidence_trace(result, "Python\t\t  SQL") is result


def test_evidence_matching_normalizes_nbsp_and_unicode_compatibility_forms() -> None:
    result = ResumeExtractionResult(skills=[{"name": "FastAPI", "evidence_text": "FastAPI Engineer"}])

    assert main.validate_evidence_trace(result, "\u00a0ＦａｓｔＡＰＩ\u00a0Engineer\u00a0") is result


def test_evidence_matching_rejects_paraphrased_or_nonexistent_excerpt() -> None:
    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Created an AI assistant"}])

    with pytest.raises(HTTPException) as error:
        main.validate_evidence_trace(result, "Built an AI document assistant")

    assert error.value.status_code == 502


def test_configured_frontend_origins_are_allowed(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.example.com, https://preview.example.com")
    assert main.get_allowed_frontend_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://app.example.com",
        "https://preview.example.com",
    ]


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


def test_openai_provider_uses_configured_gateway_and_primary_model(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gateway-model")
    monkeypatch.setenv("OPENAI_RESUME_MODEL", "legacy-model")

    provider = main.OpenAIResumeProvider()

    assert captured == {
        "api_key": "test-key",
        "base_url": "https://gateway.example/v1",
    }
    assert provider.model == "gateway-model"


def test_openai_provider_uses_sdk_default_endpoint_without_base_url(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_RESUME_MODEL", "legacy-model")

    provider = main.OpenAIResumeProvider()

    assert captured == {"api_key": "test-key"}
    assert provider.model == "legacy-model"


def test_openai_provider_uses_existing_default_model_when_unconfigured(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            pass

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_RESUME_MODEL", raising=False)

    provider = main.OpenAIResumeProvider()

    assert provider.model == "gpt-4o-mini"


def test_openai_api_key_is_not_logged(monkeypatch, caplog) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            pass

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with caplog.at_level("INFO"):
        main.OpenAIResumeProvider()

    assert "test-key" not in caplog.text


def test_openai_prompt_requires_verbatim_contiguous_evidence(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        def parse(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=ResumeExtractionResult()))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs: str) -> None:
            self.beta = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    main.OpenAIResumeProvider().extract("Example University")
    prompt = captured["messages"][0]["content"]

    assert "VERBATIM contiguous excerpt" in prompt
    assert "Do not paraphrase, summarize, translate, or rewrite evidence_text" in prompt
    assert "Keep evidence excerpts concise" in prompt
