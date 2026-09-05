from io import BytesIO
import logging
import sys
from types import SimpleNamespace

import fitz
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from openai import APIStatusError
from sqlalchemy.exc import SQLAlchemyError

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


class NonexistentEvidenceProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(skills=[{"name": "Kubernetes", "evidence_text": "Fabricated evidence"}])


class UnsupportedFactProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(skills=[{"name": "Kubernetes", "evidence_text": "Python"}])


class NormalizingProvider:
    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        return ResumeExtractionResult(
            education=[
                {
                    "institution": "Example University",
                    "field_of_study": "Computer Science",
                    "relevant_courses": ["ML", "DB"],
                    "evidence_text": "Example University Computer Science Courses: ML, DB",
                }
            ],
            skills=[{"name": "Word, Excel, PPT", "evidence_text": "Skills: Word, Excel, PPT"}],
            experiences=[
                {
                    "title": "Student Union Minister",
                    "source_section": "Campus",
                    "experience_type": "WORK",
                    "evidence_text": "Campus: Student Union Minister",
                }
            ],
            certifications=[],
        )


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


def test_resume_upload_persists_normalized_profile_facts() -> None:
    set_resume_provider(NormalizingProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={
            "file": (
                "resume.pdf",
                BytesIO(
                    pdf_bytes(
                        "Example University Computer Science Courses: ML, DB\n"
                        "Skills: Word, Excel, PPT\nCampus: Student Union Minister"
                    )
                ),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["education"][0]["relevant_courses"] == ["ML", "DB"]
    assert {skill["name"] for skill in body["skills"]} == {"Word", "Excel", "PowerPoint"}
    powerpoint = next(skill for skill in body["skills"] if skill["name"] == "PowerPoint")
    assert powerpoint["raw_value"] == "PPT"
    assert powerpoint["canonical_value"] == "PowerPoint"
    assert powerpoint["evidence_start"] is not None
    assert powerpoint["evidence_end"] is not None
    assert body["experiences"][0]["experience_type"] == "CAMPUS"


def test_profile_persistence_failure_has_distinct_error(monkeypatch) -> None:
    set_resume_provider(MockResumeProvider())

    def fail_persistence(*args, **kwargs):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(main, "create_draft_profile", fail_persistence)
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Example University MSc Python Research Assistant Lab")), "application/pdf")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Profile persistence failed"


def test_provider_timeout_returns_safe_diagnostic_and_timeout_status(client: TestClient, caplog) -> None:
    class TimeoutProvider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            raise TimeoutError("resume-content-secret")

    set_resume_provider(TimeoutProvider())
    try:
        with caplog.at_level(logging.ERROR, logger=main.logger.name):
            response = client.post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf_bytes("resume-source-secret")), "application/pdf")},
            )
    finally:
        set_resume_provider(None)

    assert response.status_code == 504
    assert response.json()["detail"] == "Resume extraction provider timed out"
    provider_logs = [record.getMessage() for record in caplog.records if "provider_failure" in record.getMessage()]
    assert provider_logs
    diagnostic = provider_logs[-1]
    assert "failure_type=timeout" in diagnostic
    assert "stage=initial_extraction" in diagnostic
    assert "exception_class=TimeoutError" in diagnostic
    assert "upstream_status=none" in diagnostic
    assert "elapsed_ms=" in diagnostic
    assert "total_llm_calls=1" in diagnostic
    assert "resume-source-secret" not in caplog.text
    assert "resume-content-secret" not in caplog.text


def test_provider_connection_error_returns_safe_unavailable_diagnostic(client: TestClient, caplog) -> None:
    class ConnectionProvider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            raise ConnectionError("authorization-secret")

    set_resume_provider(ConnectionProvider())
    try:
        with caplog.at_level(logging.ERROR, logger=main.logger.name):
            response = client.post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf_bytes("connection-resume-secret")), "application/pdf")},
            )
    finally:
        set_resume_provider(None)

    assert response.status_code == 502
    assert response.json()["detail"] == "Resume extraction provider unavailable"
    diagnostic = next(record.getMessage() for record in caplog.records if "provider_failure" in record.getMessage())
    assert "failure_type=connection_error" in diagnostic
    assert "stage=initial_extraction" in diagnostic
    assert "exception_class=ConnectionError" in diagnostic
    assert "authorization-secret" not in caplog.text
    assert "connection-resume-secret" not in caplog.text


def test_provider_status_error_returns_safe_status_diagnostic(client: TestClient, caplog) -> None:
    request = httpx.Request("POST", "https://gateway.example/v1/chat/completions")
    response = httpx.Response(503, request=request, content=b'{"error":"provider-body-secret"}')

    class StatusProvider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            raise APIStatusError(
                "provider-body-secret",
                response=response,
                body={"error": "provider-body-secret"},
            )

    set_resume_provider(StatusProvider())
    try:
        with caplog.at_level(logging.ERROR, logger=main.logger.name):
            result = client.post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf_bytes("status-resume-secret")), "application/pdf")},
            )
    finally:
        set_resume_provider(None)

    assert result.status_code == 502
    assert result.json()["detail"] == "Resume extraction provider unavailable"
    diagnostic = next(record.getMessage() for record in caplog.records if "provider_failure" in record.getMessage())
    assert "failure_type=upstream_status_error" in diagnostic
    assert "stage=initial_extraction" in diagnostic
    assert "exception_class=APIStatusError" in diagnostic
    assert "upstream_status=503" in diagnostic
    assert "status-resume-secret" not in caplog.text
    assert "provider-body-secret" not in caplog.text


def test_invalid_structured_output_returns_safe_diagnostic(client: TestClient, caplog) -> None:
    class InvalidStructuredOutputProvider:
        def extract(self, evidence_text: str) -> object:
            return {"skills": [{"name": "Python"}]}

    set_resume_provider(InvalidStructuredOutputProvider())
    try:
        with caplog.at_level(logging.ERROR, logger=main.logger.name):
            response = client.post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf_bytes("structured-resume-secret")), "application/pdf")},
            )
    finally:
        set_resume_provider(None)

    assert response.status_code == 502
    assert response.json()["detail"] == "Resume extraction returned invalid structured output"
    diagnostic = next(record.getMessage() for record in caplog.records if "provider_failure" in record.getMessage())
    assert "failure_type=structured_output_validation" in diagnostic
    assert "stage=initial_extraction" in diagnostic
    assert "exception_class=ValidationError" in diagnostic
    assert "structured-resume-secret" not in caplog.text


def test_provider_failure_during_experience_repair_reports_repair_stage(client: TestClient, caplog) -> None:
    class RepairFailureProvider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            return ResumeExtractionResult(
                experiences=[
                    {
                        "title": "Student Union",
                        "experience_type": "CAMPUS",
                        "source_section": "Campus Experience",
                        "evidence_text": "Student Union",
                    }
                ]
            )

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EXPERIENCE"
            raise TimeoutError("repair-provider-body-secret")

    source = "Campus Experience\nStudent Union\n\nWork Experience\nBackend Engineer"
    set_resume_provider(RepairFailureProvider())
    try:
        with caplog.at_level(logging.ERROR, logger=main.logger.name):
            response = client.post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf_bytes(source)), "application/pdf")},
            )
    finally:
        set_resume_provider(None)

    assert response.status_code == 504
    assert response.json()["detail"] == "Resume extraction provider timed out"
    diagnostic = next(record.getMessage() for record in caplog.records if "provider_failure" in record.getMessage())
    assert "failure_type=timeout" in diagnostic
    assert "stage=experience_repair" in diagnostic
    assert "total_llm_calls=2" in diagnostic
    assert "repair-provider-body-secret" not in caplog.text


def test_unexpected_processing_failure_returns_safe_diagnostic(client: TestClient, caplog, monkeypatch) -> None:
    class Provider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            return ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

    def fail_normalization(result: ResumeExtractionResult) -> ResumeExtractionResult:
        raise RuntimeError("internal-provider-body-secret")

    monkeypatch.setattr(main, "normalize_resume_extraction", fail_normalization)
    set_resume_provider(Provider())
    try:
        with caplog.at_level(logging.ERROR, logger=main.logger.name):
            response = client.post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf_bytes("internal-resume-secret Python")), "application/pdf")},
            )
    finally:
        set_resume_provider(None)

    assert response.status_code == 500
    assert response.json()["detail"] == "Resume extraction processing failed"
    diagnostic = next(record.getMessage() for record in caplog.records if "provider_failure" in record.getMessage())
    assert "failure_type=unexpected_internal_processing" in diagnostic
    assert "stage=grounding_normalization" in diagnostic
    assert "exception_class=RuntimeError" in diagnostic
    assert "internal-provider-body-secret" not in caplog.text
    assert "internal-resume-secret" not in caplog.text


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


def test_provider_evidence_is_replaced_with_deterministic_source_anchor() -> None:
    set_resume_provider(FabricatedEvidenceProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Python")), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["skills"][0]["evidence_text"] == "Python"


def test_provider_evidence_not_in_source_diagnostic_is_safe() -> None:
    set_resume_provider(NonexistentEvidenceProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Python")), "application/pdf")},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "Resume evidence validation failed: skill[0]: evidence_not_in_source"
    assert "Fabricated evidence" not in detail
    assert "Kubernetes" not in detail
    assert "Python" not in detail


def test_provider_fact_must_be_supported_by_its_evidence() -> None:
    set_resume_provider(UnsupportedFactProvider())
    response = TestClient(app).post(
        "/api/v1/resumes",
        files={"file": ("resume.pdf", BytesIO(pdf_bytes("Python")), "application/pdf")},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "Resume evidence validation failed: skill[0]: fact_not_in_evidence"
    assert "Kubernetes" not in detail
    assert "Python" not in detail


def test_anchor_fact_to_source_accepts_valid_model_evidence() -> None:
    assert main.anchor_fact_to_source("Python", "Python", "Python") == "Python"


def test_anchor_fact_to_source_recovers_fact_from_paraphrased_evidence() -> None:
    assert main.anchor_fact_to_source("Python", "Python", "Experienced with Python programming") == "Python"


def test_anchor_fact_to_source_preserves_pdf_whitespace_span() -> None:
    assert main.anchor_fact_to_source("Python\nDeveloper", "Python", "Python Developer") == "Python\nDeveloper"


def test_anchor_fact_to_source_rejects_fact_absent_from_source() -> None:
    assert main.anchor_fact_to_source("Python", "Kubernetes", "Kubernetes") is None


def test_anchor_fact_to_source_handles_decomposed_unicode() -> None:
    assert main.anchor_fact_to_source("Cafe\u0301", "Café", "Café") == "Cafe\u0301"


def test_anchor_fact_to_source_handles_composed_hangul_jamo() -> None:
    assert main.anchor_fact_to_source("가", "가", "가") == "가"


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
        "timeout": 30.0,
        "max_retries": 0,
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

    assert captured == {
        "api_key": "test-key",
        "timeout": 30.0,
        "max_retries": 0,
    }
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


def test_openai_section_prompt_requires_experience_type_and_source_section(monkeypatch) -> None:
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

    main.OpenAIResumeProvider().extract_section("工作经历\nBackend Engineer", "EXPERIENCE")
    prompt = captured["messages"][0]["content"]

    assert "experience_type" in prompt
    assert "source_section" in prompt
    assert "WORK" in prompt
    assert "INTERNSHIP" in prompt
    assert "PROJECT" in prompt
    assert "exact heading" in prompt
