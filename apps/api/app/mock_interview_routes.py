"""模拟面试路由（第七阶段）：启动 → 逐轮作答 → 追问 → 整体报告。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import mock_interview_service as svc
from .database import get_db


router = APIRouter(prefix="/api/v1")


class MockInterviewStartRequest(BaseModel):
    mission_id: UUID | None = None
    target_resume_id: UUID | None = None
    interview_type: str = "TECHNICAL"
    difficulty: str = "MEDIUM"
    interviewer_style: str | None = None
    rounds: int = 3
    raw_jd: str | None = Field(default=None, max_length=20_000)


class MockInterviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=20_000)


class MockInterviewTurnRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    round_number: int
    question: str
    question_source: str
    answer: str | None = None
    evaluation: dict = Field(default_factory=dict)


class MockInterviewSessionRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    profile_id: str
    mission_id: str | None = None
    target_resume_id: str | None = None
    interview_type: str
    difficulty: str
    interviewer_style: str | None = None
    rounds: int
    current_round: int
    status: str
    config: dict = Field(default_factory=dict)
    report: dict = Field(default_factory=dict)
    turns: list[MockInterviewTurnRead] = Field(default_factory=list)
    pending_question: str | None = None


@router.post("/profiles/{profile_id}/mock-interviews", response_model=MockInterviewSessionRead, status_code=201)
def start_mock_interview(profile_id: UUID, payload: MockInterviewStartRequest, db: Session = Depends(get_db)):
    row = svc.start_mock_interview(
        db,
        profile_id,
        mission_id=payload.mission_id,
        target_resume_id=payload.target_resume_id,
        interview_type=payload.interview_type,
        difficulty=payload.difficulty,
        interviewer_style=payload.interviewer_style,
        rounds=payload.rounds,
        raw_jd=payload.raw_jd,
    )
    return svc.session_read(row)


@router.get("/mock-interviews/{session_id}", response_model=MockInterviewSessionRead)
def read_mock_interview(session_id: UUID, db: Session = Depends(get_db)):
    return svc.session_read(svc.get_session(db, session_id))


@router.post("/mock-interviews/{session_id}/answers", response_model=MockInterviewSessionRead)
def submit_mock_answer(session_id: UUID, payload: MockInterviewAnswerRequest, db: Session = Depends(get_db)):
    row = svc.submit_answer(db, session_id, answer=payload.answer)
    return svc.session_read(row)
