"""题库路由（目标三）。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import question_bank_service as svc
from .database import get_db


router = APIRouter(prefix="/api/v1")


class BankCreateRequest(BaseModel):
    name: str = "默认题库"
    mission_id: UUID | None = None


class ItemCreateRequest(BaseModel):
    question_text: str = Field(min_length=1)
    category: str | None = None
    difficulty: str = "MEDIUM"
    interviewer_style: str | None = None
    source: str = "MODEL"
    jd_requirement_refs: list[str] = Field(default_factory=list)
    experience_refs: list[str] = Field(default_factory=list)
    why_asked: str | None = None
    expected_evidence: list[str] = Field(default_factory=list)
    followup_paths: list[str] = Field(default_factory=list)
    sample_answer: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class ReferenceAnswerRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    answer_text: str
    grounding: str
    evidence_refs: list = Field(default_factory=list)


class ItemRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    bank_id: str
    category: str
    difficulty: str
    interviewer_style: str | None = None
    question_text: str
    source: str
    evidence_refs: list = Field(default_factory=list)
    jd_requirement_refs: list = Field(default_factory=list)
    experience_refs: list = Field(default_factory=list)
    why_asked: str | None = None
    expected_evidence: list = Field(default_factory=list)
    followup_paths: list = Field(default_factory=list)
    sample_answer: str | None = None
    risk_flags: list = Field(default_factory=list)
    sort_order: int = 0
    reference_answer: ReferenceAnswerRead | None = None


class BankRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    profile_id: str
    mission_id: str | None = None
    name: str
    item_count: int = 0
    items: list[ItemRead] = Field(default_factory=list)


class SuggestionRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    question: str
    suggestion: str
    evidence_refs: list = Field(default_factory=list)
    grounding: str | None = None


@router.post("/profiles/{profile_id}/question-banks", response_model=BankRead, status_code=201)
def create_bank(profile_id: UUID, payload: BankCreateRequest, db: Session = Depends(get_db)):
    bank = svc.create_bank(db, profile_id, name=payload.name, mission_id=payload.mission_id)
    return svc.bank_read(bank)


@router.get("/profiles/{profile_id}/question-banks", response_model=list[BankRead])
def list_banks(profile_id: UUID, db: Session = Depends(get_db)):
    return [svc.bank_read(bank) for bank in svc.list_banks(db, profile_id)]


@router.get("/question-banks/{bank_id}", response_model=BankRead)
def read_bank(bank_id: UUID, db: Session = Depends(get_db)):
    return svc.bank_read(svc.get_bank(db, bank_id))


@router.post("/question-banks/{bank_id}/items", response_model=ItemRead, status_code=201)
def create_bank_item(bank_id: UUID, payload: ItemCreateRequest, db: Session = Depends(get_db)):
    item = svc.add_item(
        db,
        bank_id,
        question_text=payload.question_text,
        category=payload.category,
        difficulty=payload.difficulty,
        interviewer_style=payload.interviewer_style,
        source=payload.source,
        jd_requirement_refs=payload.jd_requirement_refs,
        experience_refs=payload.experience_refs,
        why_asked=payload.why_asked,
        expected_evidence=payload.expected_evidence,
        followup_paths=payload.followup_paths,
        sample_answer=payload.sample_answer,
        risk_flags=payload.risk_flags,
    )
    return svc.item_read(item)


class GenerateBankRequest(BaseModel):
    mission_id: UUID | None = None
    target_resume_id: UUID | None = None
    raw_jd: str | None = Field(default=None, max_length=20_000)
    name: str | None = None


@router.post("/profiles/{profile_id}/question-banks/generate", response_model=BankRead, status_code=201)
def generate_bank(profile_id: UUID, payload: GenerateBankRequest, db: Session = Depends(get_db)):
    """按真实上下文（JD 要点 + 已确认岗位简历 + 技能）生成三分类题库。"""
    bank = svc.generate_bank_from_context(
        db,
        profile_id,
        mission_id=payload.mission_id,
        target_resume_id=payload.target_resume_id,
        raw_jd=payload.raw_jd,
        name=payload.name,
    )
    return svc.bank_read(bank)


@router.get("/question-items/{item_id}", response_model=ItemRead)
def read_item(item_id: UUID, db: Session = Depends(get_db)):
    return svc.item_read(svc.get_item(db, item_id))


@router.post("/question-items/{item_id}/reference-answer", response_model=ReferenceAnswerRead)
def generate_reference_answer(
    item_id: UUID,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    row = svc.generate_reference_answer(db, item_id, force=force)
    return {
        "id": str(row.id),
        "answer_text": row.answer_text,
        "grounding": row.grounding,
        "evidence_refs": list(row.evidence_refs or []),
    }


@router.post("/question-items/{item_id}/resume-suggestions", response_model=list[SuggestionRead])
def resume_suggestions(item_id: UUID, db: Session = Depends(get_db)):
    return svc.suggest_resume_optimizations(db, item_id)


class RealQuestionCreateRequest(BaseModel):
    question_text: str = Field(min_length=1)
    category: str | None = None
    difficulty: str = "MEDIUM"
    interviewer_style: str | None = None
    bank_id: UUID | None = None
    mission_id: UUID | None = None


@router.post("/profiles/{profile_id}/question-items/real", response_model=ItemRead, status_code=201)
def create_real_question(profile_id: UUID, payload: RealQuestionCreateRequest, db: Session = Depends(get_db)):
    """录入真实面试题（source=REAL_INTERVIEW）；未指定题库时落到该档案的通用题库。"""
    bank = None
    if payload.bank_id is not None:
        bank = svc.get_bank(db, payload.bank_id)
    else:
        banks = svc.list_banks(db, profile_id)
        bank = next((b for b in banks if payload.mission_id is not None and b.mission_id == payload.mission_id), None)
        if bank is None:
            bank = next((b for b in banks if b.mission_id is None), None)
    if bank is None:
        bank = svc.create_bank(db, profile_id, name="真实面试题", mission_id=payload.mission_id)
    item = svc.add_item(
        db,
        bank.id,
        question_text=payload.question_text,
        category=payload.category,
        difficulty=payload.difficulty,
        interviewer_style=payload.interviewer_style,
        source="REAL_INTERVIEW",
    )
    return svc.item_read(item)
