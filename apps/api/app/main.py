from __future__ import annotations

import os
import unicodedata
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

        client_options = {"api_key": os.environ["OPENAI_API_KEY"]}
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            client_options["base_url"] = base_url
        self.client = OpenAI(**client_options)
        self.model = os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_RESUME_MODEL") or "gpt-4o-mini"

    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Extract explicit resume facts only. For every evidence_text, copy a VERBATIM contiguous excerpt from the resume. Do not paraphrase, summarize, translate, or rewrite evidence_text. Preserve evidence_text exactly as shown. Keep evidence excerpts concise. Do not infer skill proficiency; proficiency must remain null.",
                },
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


def _normalize_text_with_spans(text: str) -> tuple[str, list[tuple[int, int]]]:
    normalized_chars: list[str] = []
    source_spans: list[tuple[int, int]] = []
    pending_space: tuple[int, int] | None = None

    for index, character in enumerate(text):
        compatibility_text = unicodedata.normalize("NFKC", character).replace("\u00a0", " ")
        for normalized_character in compatibility_text.casefold():
            if normalized_character.isspace():
                pending_space = (pending_space[0], index + 1) if pending_space else (index, index + 1)
                continue
            if pending_space is not None and normalized_chars:
                normalized_chars.append(" ")
                source_spans.append(pending_space)
            pending_space = None
            normalized_chars.append(normalized_character)
            source_spans.append((index, index + 1))

    return "".join(normalized_chars), source_spans


def normalize_text(text: str) -> str:
    return _normalize_text_with_spans(text)[0]


def anchor_fact_to_source(source_text: str, fact_value: str, candidate_evidence: str) -> str | None:
    normalized_source, source_spans = _normalize_text_with_spans(source_text)
    normalized_fact = normalize_text(fact_value)
    normalized_candidate = normalize_text(candidate_evidence)
    if not normalized_fact:
        return None

    match_start = -1
    match_text = ""
    if normalized_fact in normalized_candidate:
        match_start = normalized_source.find(normalized_candidate)
        match_text = normalized_candidate
    if match_start == -1:
        match_start = normalized_source.find(normalized_fact)
        match_text = normalized_fact
    if match_start == -1:
        return None

    match_end = match_start + len(match_text) - 1
    source_start = source_spans[match_start][0]
    source_end = source_spans[match_end][1]
    return source_text[source_start:source_end]


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
    fact_groups = (
        ("education", result.education),
        ("skill", result.skills),
        ("experience", result.experiences),
        ("certification", result.certifications),
    )
    for category, facts in fact_groups:
        for index, fact in enumerate(facts):
            normalized_evidence = normalize_text(fact.evidence_text)
            anchored_evidence = anchor_fact_to_source(source_text, get_primary_fact_value(fact), fact.evidence_text)
            if anchored_evidence is None:
                failure_reason = (
                    "evidence_not_in_source"
                    if normalized_evidence not in normalized_source
                    else "fact_not_in_evidence"
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Resume evidence validation failed: {category}[{index}]: {failure_reason}",
                )
            fact.evidence_text = anchored_evidence
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
