from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
