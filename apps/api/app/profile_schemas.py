from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProfileStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class Proficiency(StrEnum):
    AWARE = "AWARE"
    BASIC = "BASIC"
    PROJECT_READY = "PROJECT_READY"
    PROFICIENT = "PROFICIENT"


class ExperienceType(StrEnum):
    WORK = "WORK"
    INTERNSHIP = "INTERNSHIP"
    CAMPUS = "CAMPUS"
    PROJECT = "PROJECT"
    OTHER = "OTHER"


class SourceType(StrEnum):
    AI_EXTRACTED = "AI_EXTRACTED"
    USER_ENTERED = "USER_ENTERED"
    USER_EDITED = "USER_EDITED"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ProfileItemInput(BaseModel):
    id: UUID | None = None
    evidence_text: str | None = None
    source_type: SourceType = SourceType.USER_ENTERED

    @field_validator("evidence_text", mode="before")
    @classmethod
    def normalize_evidence(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def require_evidence_for_resume_sources(self):
        if self.source_type != SourceType.USER_ENTERED and self.evidence_text is None:
            raise ValueError("evidence_text is required for resume-sourced facts")
        return self


class EducationInput(ProfileItemInput):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    dates: str | None = None
    relevant_courses: list[str] = Field(default_factory=list)

    @field_validator("institution", mode="before")
    @classmethod
    def require_institution(cls, value: str) -> str:
        normalized = _blank_to_none(value)
        if normalized is None:
            raise ValueError("institution must not be blank")
        return normalized

    @field_validator("degree", "field_of_study", "dates", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("relevant_courses", mode="before")
    @classmethod
    def normalize_courses(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []
        return list(dict.fromkeys(course.strip() for course in value if course and course.strip()))


class ProfileSkillInput(ProfileItemInput):
    name: str
    proficiency: Proficiency | None = None

    @field_validator("name", mode="before")
    @classmethod
    def require_name(cls, value: str) -> str:
        normalized = _blank_to_none(value)
        if normalized is None:
            raise ValueError("name must not be blank")
        return normalized


class ExperienceInput(ProfileItemInput):
    title: str
    organization: str | None = None
    dates: str | None = None
    description: str | None = None
    experience_type: ExperienceType = ExperienceType.OTHER

    @field_validator("title", mode="before")
    @classmethod
    def require_title(cls, value: str) -> str:
        normalized = _blank_to_none(value)
        if normalized is None:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("organization", "dates", "description", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class CertificationInput(ProfileItemInput):
    name: str
    issuer: str | None = None
    date: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def require_name(cls, value: str) -> str:
        normalized = _blank_to_none(value)
        if normalized is None:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("issuer", "date", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ProfileUpdate(BaseModel):
    education: list[EducationInput] = Field(default_factory=list)
    skills: list[ProfileSkillInput] = Field(default_factory=list)
    experiences: list[ExperienceInput] = Field(default_factory=list)
    certifications: list[CertificationInput] = Field(default_factory=list)


class EducationRead(EducationInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ProfileSkillRead(ProfileSkillInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ExperienceRead(ExperienceInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class CertificationRead(CertificationInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: UUID
    status: ProfileStatus
    created_at: datetime
    updated_at: datetime
    education: list[EducationRead]
    skills: list[ProfileSkillRead]
    experiences: list[ExperienceRead]
    certifications: list[CertificationRead]
