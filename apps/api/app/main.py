from __future__ import annotations

import os
from typing import Protocol

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

MAX_RESUME_BYTES = 10 * 1024 * 1024
LOCAL_FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class Education(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    dates: str | None = None
    evidence_text: str = Field(min_length=1)


class Skill(BaseModel):
    name: str
    evidence_text: str = Field(min_length=1)
    proficiency: None = None


class Experience(BaseModel):
    title: str
    organization: str | None = None
    dates: str | None = None
    description: str | None = None
    evidence_text: str = Field(min_length=1)


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None
    evidence_text: str = Field(min_length=1)


class ResumeExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)


class ResumeProvider(Protocol):
    def extract(self, evidence_text: str) -> ResumeExtractionResult: ...


class OpenAIResumeProvider:
    def __init__(self) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = os.getenv("OPENAI_RESUME_MODEL", "gpt-4o-mini")

    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": "Extract explicit resume facts only. Preserve evidence_text. Do not infer skill proficiency; proficiency must remain null."},
                {"role": "user", "content": evidence_text},
            ],
            response_format=ResumeExtractionResult,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no structured resume result")
        return ResumeExtractionResult.model_validate(parsed)


_resume_provider: ResumeProvider | None = None


def set_resume_provider(provider: ResumeProvider | None) -> None:
    global _resume_provider
    _resume_provider = provider


def extract_pdf_text(data: bytes) -> str:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as error:
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF") from error
    try:
        try:
            text = "\n".join(page.get_text() for page in document).strip()
        except Exception as error:
            raise HTTPException(status_code=422, detail="The PDF text could not be extracted") from error
    finally:
        document.close()
    if not text:
        raise HTTPException(status_code=422, detail="The PDF contains no extractable text")
    return text


def get_resume_provider() -> ResumeProvider:
    if _resume_provider is not None:
        return _resume_provider
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="Resume extraction service is not configured")
    return OpenAIResumeProvider()


def get_allowed_frontend_origins() -> list[str]:
    configured_origins = [
        origin.strip().rstrip("/")
        for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return list(dict.fromkeys([*LOCAL_FRONTEND_ORIGINS, *configured_origins]))


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


def get_primary_fact_value(fact: Education | Skill | Experience | Certification) -> str:
    if isinstance(fact, Education):
        return fact.institution
    if isinstance(fact, Skill):
        return fact.name
    if isinstance(fact, Experience):
        return fact.title
    return fact.name


def validate_evidence_trace(result: ResumeExtractionResult, source_text: str) -> ResumeExtractionResult:
    normalized_source = normalize_text(source_text)
    facts = [*result.education, *result.skills, *result.experiences, *result.certifications]
    for fact in facts:
        normalized_evidence = normalize_text(fact.evidence_text)
        normalized_fact = normalize_text(get_primary_fact_value(fact))
        if normalized_evidence not in normalized_source or normalized_fact not in normalized_evidence:
            raise HTTPException(status_code=502, detail="Resume extraction evidence was not found in the PDF")
    return result


app = FastAPI(title="AI Career OS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_frontend_origins(),
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/resumes", response_model=ResumeExtractionResult)
async def upload_resume(file: UploadFile = File(...)) -> ResumeExtractionResult:
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported")
    data = await file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume PDF exceeds the 10 MB limit")
    text = extract_pdf_text(data)
    provider = get_resume_provider()
    try:
        result = ResumeExtractionResult.model_validate(provider.extract(text))
        return validate_evidence_trace(result, text)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail="Resume extraction provider failed") from error
