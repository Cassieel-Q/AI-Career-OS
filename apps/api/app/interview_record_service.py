"""Interview records library: hand-written Q&A + standalone evaluate."""

from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import models
from .interview_provider import (
    InterviewProviderConnectionError,
    InterviewProviderError,
    InterviewProviderInvalidResponseError,
    InterviewProviderNotConfiguredError,
    InterviewProviderTimeoutError,
    get_interview_provider,
)
from .interview_record_schemas import (
    InterviewRecordCompanyGroup,
    InterviewRecordCreate,
    InterviewRecordItemCreate,
    InterviewRecordItemRead,
    InterviewRecordListRead,
    InterviewRecordPatch,
    InterviewRecordRead,
)
from .proof_schemas import InterviewEvaluation


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _company_key(company: str) -> str:
    return quote(company.strip(), safe="")


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise _http(404, "档案不存在")
    return row


def _record_query():
    return select(models.InterviewRecord).options(selectinload(models.InterviewRecord.items))


def _get_record(db: Session, record_id: UUID) -> models.InterviewRecord:
    row = db.scalar(_record_query().where(models.InterviewRecord.id == record_id))
    if row is None:
        raise _http(404, "面试记录不存在")
    return row


def _item_read(item: models.InterviewRecordItem) -> InterviewRecordItemRead:
    return InterviewRecordItemRead(
        id=item.id,
        record_id=item.record_id,
        sort_order=item.sort_order,
        question=item.question,
        context=item.context,
        my_answer=item.my_answer,
        evaluation=dict(item.evaluation) if isinstance(item.evaluation, dict) else item.evaluation,
        created_at=item.created_at,
    )


def _record_read(row: models.InterviewRecord) -> InterviewRecordRead:
    items = sorted(row.items or [], key=lambda item: (item.sort_order, str(item.id)))
    evaluated = row.status == "EVALUATED" or any(
        isinstance(item.evaluation, dict) and item.evaluation for item in items
    )
    return InterviewRecordRead(
        id=row.id,
        profile_id=row.profile_id,
        mission_id=row.mission_id,
        company=row.company,
        role=row.role,
        interview_round=row.interview_round,
        interviewed_on=row.interviewed_on,
        notes=row.notes,
        status=row.status,
        strong_points=list(row.strong_points or []),
        weak_points=list(row.weak_points or []),
        gap_type=row.gap_type,
        gap_why=row.gap_why,
        recommended_next_action=row.recommended_next_action,
        coaching=dict(row.coaching) if isinstance(row.coaching, dict) else row.coaching,
        items=[_item_read(item) for item in items],
        created_at=row.created_at,
        updated_at=row.updated_at,
        evaluated=evaluated,
    )


def _group_companies(records: list[InterviewRecordRead]) -> list[InterviewRecordCompanyGroup]:
    buckets: dict[str, list[InterviewRecordRead]] = {}
    for record in records:
        buckets.setdefault(record.company, []).append(record)
    groups: list[InterviewRecordCompanyGroup] = []
    for company, items in buckets.items():
        items_sorted = sorted(items, key=lambda r: (r.interviewed_on, r.created_at), reverse=True)
        rounds = []
        for item in items_sorted:
            if item.interview_round not in rounds:
                rounds.append(item.interview_round)
        groups.append(
            InterviewRecordCompanyGroup(
                company=company,
                company_key=_company_key(company),
                record_count=len(items_sorted),
                latest_interviewed_on=items_sorted[0].interviewed_on if items_sorted else None,
                rounds=rounds,
                records=items_sorted,
            )
        )
    groups.sort(key=lambda g: (g.latest_interviewed_on or date.min, g.company), reverse=True)
    return groups


def list_interview_records(db: Session, profile_id: UUID) -> InterviewRecordListRead:
    _profile(db, profile_id)
    rows = list(
        db.scalars(
            _record_query()
            .where(models.InterviewRecord.profile_id == profile_id)
            .order_by(models.InterviewRecord.interviewed_on.desc(), models.InterviewRecord.created_at.desc())
        ).unique()
    )
    records = [_record_read(row) for row in rows]
    return InterviewRecordListRead(records=records, companies=_group_companies(records))


def _replace_items(db: Session, row: models.InterviewRecord, items: list[InterviewRecordItemCreate]) -> None:
    row.items.clear()
    db.flush()
    for index, payload in enumerate(items):
        order = payload.sort_order if payload.sort_order is not None else index
        row.items.append(
            models.InterviewRecordItem(
                sort_order=order,
                question=payload.question,
                context=payload.context,
                my_answer=payload.my_answer,
                evaluation=None,
            )
        )


def create_interview_record(db: Session, profile_id: UUID, payload: InterviewRecordCreate) -> InterviewRecordRead:
    _profile(db, profile_id)
    if payload.mission_id is not None:
        mission = db.get(models.JobMission, payload.mission_id)
        if mission is None or mission.profile_id != profile_id:
            raise _http(404, "关联的岗位准备不存在")
    row = models.InterviewRecord(
        profile_id=profile_id,
        mission_id=payload.mission_id,
        company=payload.company,
        role=payload.role,
        interview_round=payload.interview_round,
        interviewed_on=payload.interviewed_on,
        notes=payload.notes,
        status="DRAFT",
        strong_points=[],
        weak_points=[],
    )
    db.add(row)
    db.flush()
    _replace_items(db, row, payload.items)
    db.commit()
    return _record_read(_get_record(db, row.id))


def get_interview_record(db: Session, record_id: UUID) -> InterviewRecordRead:
    return _record_read(_get_record(db, record_id))


def patch_interview_record(db: Session, record_id: UUID, payload: InterviewRecordPatch) -> InterviewRecordRead:
    row = _get_record(db, record_id)
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)
    if data.get("mission_id") is not None:
        mission = db.get(models.JobMission, data["mission_id"])
        if mission is None or mission.profile_id != row.profile_id:
            raise _http(404, "关联的岗位准备不存在")
    for key, value in data.items():
        setattr(row, key, value)
    if items is not None:
        parsed = [InterviewRecordItemCreate.model_validate(item) for item in items]
        if not parsed:
            raise _http(422, "请至少保留一道题和回答")
        _replace_items(db, row, parsed)
        row.status = "DRAFT"
        row.strong_points = []
        row.weak_points = []
        row.gap_type = None
        row.gap_why = None
        row.recommended_next_action = None
        row.coaching = None
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _record_read(_get_record(db, row.id))


def _provider_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InterviewProviderNotConfiguredError):
        return _http(503, "未配置 OPENAI_API_KEY，无法评分。请在后端环境变量中配置后重试。")
    if isinstance(exc, InterviewProviderTimeoutError):
        return _http(504, "评分服务超时，请稍后重试。")
    if isinstance(exc, InterviewProviderConnectionError):
        return _http(502, "无法连接评分服务，请稍后重试。")
    if isinstance(exc, InterviewProviderInvalidResponseError):
        return _http(502, "评分服务返回了无法解析的结果，请重试。")
    if isinstance(exc, InterviewProviderError):
        return _http(502, f"评分失败：{exc}")
    return _http(500, "评分时发生未知错误")


def _heuristic_coaching(*, strong_points: list[str], weak_points: list[str], recommended: str | None, role: str | None) -> dict[str, object]:
    role_label = role or "目标岗位"
    questions = [f"围绕「{point}」，下一次面试你会怎么补一句可核验细节？" for point in weak_points[:4]]
    if not questions:
        questions = [
            "这道题的结果指标是什么？有没有可核验的数字或对比？",
            "你个人主导了哪一段？和同事的分工边界在哪里？",
            "如果重来一次，你会改哪一个决策？为什么？",
        ]
    steps = [
        "把每道弱项题改写成 STAR：情境、任务、行动、结果。",
        "为结果补上可核验证据（指标、文档、demo、复盘记录）。",
        f"对照 {role_label} 的常见追问，准备 2 个一句话收口。",
    ]
    return {
        "title": "根据本次回答继续补强",
        "summary": recommended
        or "优先补齐薄弱点中的证据与表达结构，再准备一轮限时口述。",
        "questions": questions,
        "steps": steps,
        "learning": weak_points[:5] or ["结构化表达", "证据闭环", "决策取舍"],
        "expected_outputs": [
            "每道弱项题的改写版口述稿",
            "对应证据清单（数字 / 链接 / 文档名）",
            "一面/二面可复用的收口句",
        ],
        "strong_points": strong_points[:6],
        "weak_points": weak_points[:6],
        "generated_by": "heuristic",
    }


def evaluate_interview_record(db: Session, record_id: UUID, provider=None) -> InterviewRecordRead:
    row = _get_record(db, record_id)
    items = sorted(row.items or [], key=lambda item: (item.sort_order, str(item.id)))
    if not items:
        raise _http(422, "这条记录没有问答，无法评分")

    try:
        provider = provider or get_interview_provider()
    except InterviewProviderNotConfiguredError as exc:
        raise _provider_http_error(exc) from exc

    if not hasattr(provider, "evaluate_answer"):
        raise _http(503, "当前评分提供方不支持无 claim 评价，请升级 interview provider。")

    all_strong: list[str] = []
    all_weak: list[str] = []
    gap_votes: list[str] = []
    recommendations: list[str] = []
    gap_whys: list[str] = []
    scores: list[int] = []

    for item in items:
        try:
            evaluation: InterviewEvaluation = provider.evaluate_answer(
                question=item.question,
                answer=item.my_answer,
                context=item.context,
                company=row.company,
                role=row.role,
            )
        except Exception as exc:
            raise _provider_http_error(exc) from exc
        dumped = evaluation.model_dump(mode="json")
        item.evaluation = dumped
        for point in evaluation.strong_points or []:
            text = str(point).strip()
            if text and text not in all_strong:
                all_strong.append(text)
        for point in evaluation.weak_points or []:
            text = str(point).strip()
            if text and text not in all_weak:
                all_weak.append(text)
        if evaluation.gap_type is not None:
            gap_votes.append(evaluation.gap_type.value if hasattr(evaluation.gap_type, "value") else str(evaluation.gap_type))
        if evaluation.recommended_next_action:
            recommendations.append(evaluation.recommended_next_action.strip())
        if evaluation.why:
            gap_whys.append(evaluation.why.strip())
        if isinstance(evaluation.score, int):
            scores.append(evaluation.score)

    # majority gap_type
    gap_type = None
    if gap_votes:
        gap_type = max(set(gap_votes), key=gap_votes.count)

    recommended = recommendations[0] if recommendations else None
    if not recommended and all_weak:
        recommended = f"优先补强：{'；'.join(all_weak[:3])}"

    row.strong_points = all_strong[:8]
    row.weak_points = all_weak[:8]
    row.gap_type = gap_type
    row.gap_why = gap_whys[0] if gap_whys else (
        f"本场平均得分 {sum(scores)/len(scores):.1f}/10" if scores else None
    )
    row.recommended_next_action = recommended
    row.coaching = _heuristic_coaching(
        strong_points=all_strong,
        weak_points=all_weak,
        recommended=recommended,
        role=row.role,
    )
    row.status = "EVALUATED"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _record_read(_get_record(db, row.id))
