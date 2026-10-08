"""Schemas for the interview records library (hand-written real interviews)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .proof_schemas import InterviewGapType


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


ALLOWED_ROUNDS = ("一面", "二面", "三面", "其他")


def _validate_item_order(items: list[InterviewRecordItemCreate]) -> None:
    orders = [item.sort_order if item.sort_order is not None else index for index, item in enumerate(items)]
    if len(set(orders)) != len(orders):
        raise ValueError("问答顺序不能重复")


class InterviewRecordItemCreate(_Strict):
    question: str = Field(min_length=1, max_length=4_000)
    context: str | None = Field(default=None, max_length=4_000)
    my_answer: str = Field(min_length=1, max_length=20_000)
    sort_order: int | None = Field(default=None, ge=0, le=100)

    @field_validator("question", "my_answer", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("context", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value


class InterviewRecordCreate(_Strict):
    company: str = Field(min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    interview_round: str = Field(min_length=1, max_length=64)
    interviewed_on: date
    notes: str | None = Field(default=None, max_length=8_000)
    mission_id: UUID | None = None
    items: list[InterviewRecordItemCreate] = Field(min_length=1, max_length=40)

    @field_validator("company", "interview_round", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("role", "notes", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    @model_validator(mode="after")
    def validate_round_and_items(self) -> Self:
        if self.interview_round not in ALLOWED_ROUNDS:
            raise ValueError("面试轮次请选择：一面 / 二面 / 三面 / 其他")
        if not self.items:
            raise ValueError("请至少录入一道题和回答")
        _validate_item_order(self.items)
        return self


class InterviewRecordItemPatch(_Strict):
    id: UUID | None = None
    question: str | None = Field(default=None, max_length=4_000)
    context: str | None = Field(default=None, max_length=4_000)
    my_answer: str | None = Field(default=None, max_length=20_000)
    sort_order: int | None = Field(default=None, ge=0, le=100)


class InterviewRecordPatch(_Strict):
    company: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    interview_round: str | None = Field(default=None, min_length=1, max_length=64)
    interviewed_on: date | None = None
    notes: str | None = Field(default=None, max_length=8_000)
    mission_id: UUID | None = None
    items: list[InterviewRecordItemCreate] | None = Field(default=None, min_length=1, max_length=40)

    @field_validator("company", "interview_round", "interviewed_on", mode="before")
    @classmethod
    def validate_required_patch(cls, value: object, info) -> object:
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        if isinstance(value, str) and info.field_name != "interviewed_on":
            value = value.strip()
        if info.field_name == "interview_round" and value not in ALLOWED_ROUNDS:
            raise ValueError("面试轮次请选择：一面 / 二面 / 三面 / 其他")
        return value

    @field_validator("role", "notes", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_item_order(self) -> Self:
        if self.items is not None:
            _validate_item_order(self.items)
        return self


class InterviewRecordItemRead(_Strict):
    id: UUID
    record_id: UUID
    sort_order: int
    question: str
    context: str | None
    my_answer: str
    evaluation: dict[str, object] | None
    created_at: datetime


class InterviewRecordRead(_Strict):
    id: UUID
    profile_id: UUID
    mission_id: UUID | None
    company: str
    role: str | None
    interview_round: str
    interviewed_on: date
    notes: str | None
    status: str
    strong_points: list[str]
    weak_points: list[str]
    gap_type: InterviewGapType | str | None
    gap_why: str | None
    recommended_next_action: str | None
    coaching: dict[str, object] | None
    items: list[InterviewRecordItemRead]
    created_at: datetime
    updated_at: datetime
    evaluated: bool = False


class InterviewRecordCompanyGroup(_Strict):
    company: str
    company_key: str
    record_count: int
    latest_interviewed_on: date | None
    rounds: list[str]
    records: list[InterviewRecordRead]


class InterviewRecordListRead(_Strict):
    records: list[InterviewRecordRead]
    companies: list[InterviewRecordCompanyGroup]
