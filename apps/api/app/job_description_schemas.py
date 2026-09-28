from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


def _validated_raw_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("raw_text must contain non-whitespace text")
    return value


def _normalized_source_url(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("source_url must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source_url must be an HTTP(S) URL with a host")
    return normalized


class JobDescriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    source_url: str | None = None

    _validate_raw_text = field_validator("raw_text", mode="before")(_validated_raw_text)
    _normalize_source_url = field_validator("source_url", mode="before")(_normalized_source_url)


class JobDescriptionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str | None = None
    source_url: str | None = None

    @field_validator("raw_text", mode="before")
    @classmethod
    def validate_raw_text(cls, value: object) -> str:
        return _validated_raw_text(value)

    _normalize_source_url = field_validator("source_url", mode="before")(_normalized_source_url)


class JobDescriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    target_role_id: UUID
    raw_text: str
    source_url: str | None
    created_at: datetime
    updated_at: datetime
