"""独立题库与参考答案（目标三）。

保留现有 mission 模拟面试流程不动，新增可复用题库：
- 三分类：BASIC / PROJECT_DEEP_DIVE / HR_QUESTIONS；
- 支持岗位（mission）、难度、面试官风格；
- 每题可生成参考答案；真实面试题可录入（source=REAL_INTERVIEW）；
- 可根据真实问题生成简历优化建议。

**事实门控（硬约束）**：参考答案只能使用
1) 状态为已确认的 ResumeClaim；
2) confirmed 的 target resume bullet。
禁止使用 demo / CURATED / 未经确认的面经。门控失败时落 UNKNOWN / NEEDS_CONFIRMATION。

参考回答只用既有事实原文拼接，不新增数字、工具、职责或结果，因此不会编造。
"""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

CATEGORIES = {"BASIC", "PROJECT_DEEP_DIVE", "HR_QUESTIONS"}
DIFFICULTIES = {"EASY", "MEDIUM", "HARD"}
CONFIRMED_CLAIM_STATUSES = {"READY", "CONFIRMED", "SUPPORTED"}
UNKNOWN = "UNKNOWN"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"

_HR_PATTERNS = ("自我介绍", "为什么", "缺点", "优点", "职业规划", "离职", "期望薪资", "加班", "为什么选择", "职业目标", "抗压")
_BASIC_PATTERNS = ("什么是", "概念", "区别", "原理", "流程", "如何理解", "介绍一下")


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


def classify_question(text: str) -> str:
    """按题面把题目归到三分类（用于真实面试题录入的默认分类）。"""
    folded = (text or "").casefold()
    if any(pattern in folded for pattern in _HR_PATTERNS):
        return "HR_QUESTIONS"
    if any(pattern in folded for pattern in _BASIC_PATTERNS):
        return "BASIC"
    return "PROJECT_DEEP_DIVE"


# ---------------------------------------------------------------------------
# 题库 / 题目
# ---------------------------------------------------------------------------


def create_bank(
    db: Session,
    profile_id: UUID,
    *,
    name: str = "默认题库",
    mission_id: UUID | None = None,
) -> models.QuestionBank:
    _profile(db, profile_id)
    if mission_id is not None and db.get(models.JobMission, mission_id) is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    bank = models.QuestionBank(profile_id=profile_id, mission_id=mission_id, name=(name or "默认题库")[:255])
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return bank


def get_bank(db: Session, bank_id: UUID) -> models.QuestionBank:
    bank = db.get(models.QuestionBank, bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="题库不存在")
    return bank


def list_banks(db: Session, profile_id: UUID) -> list[models.QuestionBank]:
    _profile(db, profile_id)
    return list(
        db.scalars(
            select(models.QuestionBank)
            .where(models.QuestionBank.profile_id == profile_id)
            .order_by(models.QuestionBank.created_at, models.QuestionBank.id)
        ).all()
    )


def _validate_category(category: str) -> str:
    value = (category or "").strip().upper()
    if value not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"题目分类必须是 {sorted(CATEGORIES)} 之一")
    return value


def _validate_difficulty(difficulty: str) -> str:
    value = (difficulty or "MEDIUM").strip().upper()
    if value not in DIFFICULTIES:
        raise HTTPException(status_code=422, detail=f"难度必须是 {sorted(DIFFICULTIES)} 之一")
    return value


def add_item(
    db: Session,
    bank_id: UUID,
    *,
    question_text: str,
    category: str | None = None,
    difficulty: str = "MEDIUM",
    interviewer_style: str | None = None,
    source: str = "MODEL",
    evidence_refs: list | None = None,
) -> models.QuestionItem:
    bank = get_bank(db, bank_id)
    text = (question_text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="题目内容不能为空")
    resolved_category = _validate_category(category or classify_question(text))
    resolved_source = "REAL_INTERVIEW" if (source or "").upper() == "REAL_INTERVIEW" else "MODEL"
    max_order = max((item.sort_order for item in bank.items), default=-1)
    item = models.QuestionItem(
        bank_id=bank.id,
        category=resolved_category,
        difficulty=_validate_difficulty(difficulty),
        interviewer_style=(interviewer_style or None),
        question_text=text,
        source=resolved_source,
        evidence_refs=list(evidence_refs or []),
        sort_order=max_order + 1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_item(db: Session, item_id: UUID) -> models.QuestionItem:
    item = db.get(models.QuestionItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return item


# ---------------------------------------------------------------------------
# 事实门控：允许使用的证据
# ---------------------------------------------------------------------------


def _confirmed_claims(db: Session, profile_id: UUID) -> list[models.ResumeClaim]:
    rows = db.scalars(
        select(models.ResumeClaim).where(models.ResumeClaim.profile_id == profile_id)
    ).all()
    return [
        row
        for row in rows
        if (row.readiness_status or "").upper() in CONFIRMED_CLAIM_STATUSES
    ]


def _profile_id_for_bank(db: Session, bank: models.QuestionBank) -> UUID:
    return bank.profile_id


def _confirmed_target_bullets(db: Session, profile_id: UUID, mission_id: UUID | None) -> list[models.TargetResumeBullet]:
    if mission_id is None:
        return []
    studio = db.scalar(
        select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission_id)
    )
    resumes = db.scalars(
        select(models.TargetResume).where(models.TargetResume.mission_id == mission_id)
    ).all()
    allowed_ids: set[UUID] = set()
    for resume in resumes:
        is_confirmed = (resume.status or "").upper() == "CONFIRMED" or (
            studio is not None and studio.confirmed_revision == resume.version
        )
        if is_confirmed:
            allowed_ids.add(resume.id)
    if not allowed_ids:
        return []
    return list(
        db.scalars(
            select(models.TargetResumeBullet).where(models.TargetResumeBullet.target_resume_id.in_(allowed_ids))
        ).all()
    )


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def generate_reference_answer(db: Session, item_id: UUID, *, force: bool = False) -> models.ReferenceAnswer:
    """基于已确认事实生成参考答案；无证据落 UNKNOWN / NEEDS_CONFIRMATION。"""
    item = get_item(db, item_id)
    bank = get_bank(db, item.bank_id)
    profile_id = _profile_id_for_bank(db, bank)

    claims = _confirmed_claims(db, profile_id)
    bullets = _confirmed_target_bullets(db, profile_id, bank.mission_id)

    # 关键词匹配：题面里出现的词能对上事实文本的，优先纳入；没有交集则用全部已确认事实。
    tokens = [t for t in re.split(r"[\s，,。；;：:、/（）()「」]+", item.question_text or "") if len(t) >= 2]
    matched_claims = [c for c in claims if any(t in (c.claim or "") or t in (c.current_text or "") for t in tokens)]
    matched_bullets = [b for b in bullets if any(t in (b.final_text or b.suggested_text or b.original_text or "") for t in tokens)]
    evidence_claims = matched_claims or claims
    evidence_bullets = matched_bullets or bullets

    evidence_refs: list[str] = []
    parts: list[str] = []
    if evidence_bullets:
        bullet_text = _clean(
            "；".join(
                (b.final_text or b.suggested_text or b.original_text or "").strip()
                for b in evidence_bullets[:5]
            )
        )
        if bullet_text:
            parts.append(f"结合已确认的岗位简历要点作答：{bullet_text}")
        evidence_refs.extend(str(b.id) for b in evidence_bullets[:5])
    if evidence_claims:
        claim_text = _clean("；".join((c.claim or "").strip() for c in evidence_claims[:5]))
        if claim_text:
            parts.append(f"可引用的事实主张：{claim_text}")
        evidence_refs.extend(str(c.id) for c in evidence_claims[:5])

    if not parts:
        grounding = UNKNOWN
        answer_text = "暂无已确认的简历事实可以支撑这道题。请先在「事实台账 / 岗位简历」里确认相关经历与要点，再生成参考答案（本功能不编造数字、工具、职责或结果）。"
    else:
        grounding = "TARGET_RESUME" if evidence_bullets else "BULLETS"
        answer_text = "；".join(parts) + "。请按 STAR 结构用自己的话展开，不要添加未记录的数据或成果。"

    if not force:
        existing = db.scalar(
            select(models.ReferenceAnswer).where(models.ReferenceAnswer.question_item_id == item.id)
        )
        if existing is not None:
            existing.answer_text = answer_text
            existing.grounding = grounding
            existing.evidence_refs = evidence_refs
            db.commit()
            db.refresh(existing)
            return existing

    row = models.ReferenceAnswer(
        question_item_id=item.id,
        answer_text=answer_text,
        grounding=grounding,
        evidence_refs=evidence_refs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def suggest_resume_optimizations(db: Session, item_id: UUID) -> list[dict]:
    """根据真实面试题，给出简历优化建议（问题 → 建议 → 关联到已确认要点）。"""
    item = get_item(db, item_id)
    bank = get_bank(db, item.bank_id)
    claims = _confirmed_claims(db, bank.profile_id)
    bullets = _confirmed_target_bullets(db, bank.profile_id, bank.mission_id)

    suggestions: list[dict] = []
    if bullets:
        suggestions.append(
            {
                "kind": "bullet",
                "question": item.question_text,
                "suggestion": "围绕这道面试题，把岗位上对应的简历要点补充量化结果或个人动作，答案会更可信。",
                "evidence_refs": [str(b.id) for b in bullets[:3]],
            }
        )
    if claims:
        suggestions.append(
            {
                "kind": "claim",
                "question": item.question_text,
                "suggestion": "确认这道题对应的事实主张已在台账中核对（状态为已确认），避免现场答得比简历更强。",
                "evidence_refs": [str(c.id) for c in claims[:3]],
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "kind": "gap",
                "question": item.question_text,
                "suggestion": "目前没有已确认的简历事实对应这道题，属于需要补强的方向：先补一段相关经历/项目，或在简历中明确写过。",
                "evidence_refs": [],
                "grounding": NEEDS_CONFIRMATION,
            }
        )
    return suggestions


# ---------------------------------------------------------------------------
# 读出
# ---------------------------------------------------------------------------


def item_read(item: models.QuestionItem) -> dict:
    answers = sorted(item.reference_answers or [], key=lambda row: row.created_at or 0) if item.reference_answers else []
    latest = answers[-1] if answers else None
    return {
        "id": str(item.id),
        "bank_id": str(item.bank_id),
        "category": item.category,
        "difficulty": item.difficulty,
        "interviewer_style": item.interviewer_style,
        "question_text": item.question_text,
        "source": item.source,
        "evidence_refs": list(item.evidence_refs or []),
        "sort_order": item.sort_order,
        "reference_answer": (
            {
                "id": str(latest.id),
                "answer_text": latest.answer_text,
                "grounding": latest.grounding,
                "evidence_refs": list(latest.evidence_refs or []),
            }
            if latest is not None
            else None
        ),
    }


def bank_read(bank: models.QuestionBank) -> dict:
    return {
        "id": str(bank.id),
        "profile_id": str(bank.profile_id),
        "mission_id": str(bank.mission_id) if bank.mission_id else None,
        "name": bank.name,
        "item_count": len(bank.items or []),
        "items": [item_read(item) for item in (bank.items or [])],
    }


__all__ = [
    "CATEGORIES",
    "DIFFICULTIES",
    "classify_question",
    "create_bank",
    "get_bank",
    "list_banks",
    "add_item",
    "get_item",
    "generate_reference_answer",
    "suggest_resume_optimizations",
    "item_read",
    "bank_read",
]
