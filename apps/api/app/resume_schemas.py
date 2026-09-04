from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExperienceType(StrEnum):
    WORK = "WORK"
    INTERNSHIP = "INTERNSHIP"
    CAMPUS = "CAMPUS"
    PROJECT = "PROJECT"
    OTHER = "OTHER"


class ExtractedFact(BaseModel):
    evidence_text: str = Field(min_length=1)
    raw_value: str | None = None
    canonical_value: str | None = None
    evidence_start: int | None = None
    evidence_end: int | None = None


class Education(ExtractedFact):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    dates: str | None = None
    relevant_courses: list[str] = Field(default_factory=list)


class Skill(ExtractedFact):
    name: str
    proficiency: None = None


class Experience(ExtractedFact):
    title: str
    organization: str | None = None
    dates: str | None = None
    description: str | None = None
    experience_type: ExperienceType = ExperienceType.OTHER
    source_section: str | None = None


class Certification(ExtractedFact):
    name: str
    issuer: str | None = None
    date: str | None = None
    score: str | None = None
    status: str | None = None


class ResumeExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
