from __future__ import annotations

import os
from typing import Protocol

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

MAX_RESUME_BYTES = 10 * 1024 * 1024


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
        text = "\n".join(page.get_text() for page in document).strip()
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


app = FastAPI(title="AI Career OS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
        return ResumeExtractionResult.model_validate(provider.extract(text))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail="Resume extraction provider failed") from error
