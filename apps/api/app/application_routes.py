"""投递台（Job Applications）与岗位广场（Job Plaza）聚合。

- JobApplication：一家公司一个岗位一条投递动作记录，状态可前进、也可退回上一阶段。
- Plaza：跨岗位聚合浏览 + 准备度评分 + 一键加入投递台。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .greeting_service import build_greetings
from .job_insight_service import cached_insight


router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

APPLICATION_STATUSES = (
    "PENDING",      # 待投递
    "APPLIED",      # 已投递
    "SCREENING",    # 筛选中
    "ASSESSMENT",   # 测评 / 笔试
    "INTERVIEW",    # 面试
    "OFFER",        # Offer
    "CLOSED",       # 已结束
)

# 状态转移规则：只允许前进；CLOSED（已结束/拒信）可从任意活跃状态进入；
# CLOSED 之后锁定为终态。这是「漏斗只有一个口径」的保证。
APPLICATION_FORWARD: dict[str, set[str]] = {
    "PENDING":    {"APPLIED", "CLOSED"},
    "APPLIED":    {"SCREENING", "ASSESSMENT", "INTERVIEW", "OFFER", "CLOSED"},
    "SCREENING":  {"ASSESSMENT", "INTERVIEW", "OFFER", "CLOSED"},
    "ASSESSMENT": {"INTERVIEW", "OFFER", "CLOSED"},
    "INTERVIEW":  {"OFFER", "CLOSED"},
    "OFFER":      {"CLOSED"},
    "CLOSED":     set(),
}

# workflow_state → 准备度评分（0–100）
_PREP_SCORE: dict[str, int] = {
    "JD_REQUIRED": 5,
    "JOB_ANALYZING": 5,
    "ROLE_UNDERSTOOD": 15,
    "RESUME_REQUIRED": 25,
    "RESUME_SELECTED": 25,
    "EXPERIENCE_SELECTION_REQUIRED": 40,
    "EXPERIENCES_CONFIRMED": 40,
    "RESUME_STRATEGY_REQUIRED": 55,
    "RESUME_STRATEGY_CONFIRMED": 55,
    "TARGET_RESUME_DRAFT": 70,
    "TARGET_RESUME_CONFIRMED": 82,
    "STRESS_TEST_REQUIRED": 85,
    "STRENGTHENING_REQUIRED": 85,
    "PROOF_IN_PROGRESS": 85,
    "CLAIM_REEVALUATION_REQUIRED": 85,
    "RESUME_UPGRADE_AVAILABLE": 85,
    "INTERVIEW_PREP_READY": 92,
    "INTERVIEW_PREP": 88,
    "INTERVIEW_IN_PROGRESS": 96,
    "INTERVIEW_DEBRIEF_READY": 96,
    "OUTCOME": 96,
}

# 投递状态 → 推进阶段（用于与 tracker 对齐展示）
APPLICATION_STAGE: dict[str, str] = {
    "PENDING": "PREPARING",
    "APPLIED": "APPLIED",
    "SCREENING": "APPLIED",
    "ASSESSMENT": "APPLIED",
    "INTERVIEW": "INTERVIEW",
    "OFFER": "INTERVIEW",
    "CLOSED": "COMPLETED",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    mission_id: UUID | None = None
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    channel: str = Field(default="官网", max_length=64)
    status: str = Field(default="PENDING", max_length=24)
    applied_at: date | None = None
    next_action: str | None = None
    notes: str | None = None
    jd_source: str | None = Field(default=None, max_length=512)


class ApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    channel: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=24)
    applied_at: date | None = None
    next_action: str | None = None
    notes: str | None = None
    jd_source: str | None = Field(default=None, max_length=512)
    greeting_short: str | None = None
    greeting_long: str | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    profile_id: str
    mission_id: str | None = None
    company: str
    role: str
    location: str | None = None
    channel: str
    status: str
    stage: str
    applied_at: date | None = None
    next_action: str | None = None
    notes: str | None = None
    jd_source: str | None = None
    # --- 投递版本绑定：回答「我当初投的是哪份简历」---
    resume_version_id: str | None = None
    resume_version: int | None = None
    studio_revision: int | None = None
    pdf_snapshot_path: str | None = None
    has_pdf_snapshot: bool = False
    # --- 打招呼话术 ---
    greeting_short: str | None = None
    greeting_long: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationsRead(BaseModel):
    total: int = 0
    pending: int = 0
    applied: int = 0
    interviewing: int = 0
    offer: int = 0
    applications: list[ApplicationRead] = Field(default_factory=list)


class PlazaItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mission_id: str
    profile_id: str
    company: str
    role: str
    location: str | None = None
    seniority: str = "UNKNOWN"
    workflow_state: str = "JD_REQUIRED"
    prep_score: int = 0
    # --- 025_job_insight：岗位关键词 + 简历×岗位匹配度（读缓存，不触发模型） ---
    keywords: list[str] = Field(default_factory=list)
    job_summary: str = ""
    analysis_source: str = "NONE"
    match_score: int | None = None
    match_verdict: str | None = None
    match_verdict_label: str | None = None
    match_source: str = "NONE"
    resume_ready: bool = False
    target_resume_confirmed: bool = False
    application_id: str | None = None
    application_status: str | None = None
    updated_at: datetime | None = None


class PlazaRead(BaseModel):
    total: int = 0
    applied: int = 0
    ready: int = 0
    items: list[PlazaItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


def _application_read(row: models.JobApplication) -> ApplicationRead:
    version_number = row.resume_version.version if row.resume_version is not None else None
    return ApplicationRead(
        id=str(row.id),
        profile_id=str(row.profile_id),
        mission_id=str(row.mission_id) if row.mission_id else None,
        company=row.company,
        role=row.role,
        location=row.location,
        channel=row.channel,
        status=row.status,
        stage=APPLICATION_STAGE.get(row.status, "PREPARING"),
        applied_at=row.applied_at,
        next_action=row.next_action,
        notes=row.notes,
        jd_source=row.jd_source,
        resume_version_id=str(row.resume_version_id) if row.resume_version_id else None,
        resume_version=version_number,
        studio_revision=row.studio_revision,
        pdf_snapshot_path=row.pdf_snapshot_path,
        has_pdf_snapshot=bool(row.pdf_snapshot_path and Path(row.pdf_snapshot_path).exists()),
        greeting_short=row.greeting_short,
        greeting_long=row.greeting_long,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _prep_score(workflow_state: str, *, target_resume_confirmed: bool = False) -> int:
    score = _PREP_SCORE.get((workflow_state or "JD_REQUIRED").upper(), 30)
    # 岗位版本已确认是「简历已备」的硬指标，准备度至少 82。
    if target_resume_confirmed:
        score = max(score, 82)
    return score


_STATUS_INDEX: dict[str, int] = {status: index for index, status in enumerate(APPLICATION_STATUSES)}


def _validate_status_transition(current: str, target: str) -> None:
    """校验投递状态变更：允许前进，也允许退回更早阶段。

    - 相同状态：允许（幂等）。
    - CLOSED 是终态，不允许再变更。
    - 任意活跃状态 → CLOSED：允许（拒信 / 主动结束）。
    - 前进：目标在 APPLICATION_FORWARD[current] 内。
    - 退回：目标阶段序号小于当前阶段序号（误点修正）。
    """
    if current == target:
        return
    if current == "CLOSED":
        raise HTTPException(status_code=422, detail="已结束的投递记录不能再变更状态")
    if target == "CLOSED":
        return
    if target in APPLICATION_FORWARD.get(current, set()):
        return
    if _STATUS_INDEX.get(target, -1) < _STATUS_INDEX.get(current, 0):
        return
    raise HTTPException(status_code=422, detail=f"投递状态不可从「{current}」变更为「{target}」")


# ---------------------------------------------------------------------------
# Applications CRUD
# ---------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/applications", response_model=ApplicationsRead)
def list_applications(profile_id: UUID, db: Session = Depends(get_db)):
    _profile(db, profile_id)
    rows = list(
        db.scalars(
            select(models.JobApplication)
            .where(models.JobApplication.profile_id == profile_id)
            .order_by(models.JobApplication.updated_at.desc())
        ).all()
    )
    applications = [_application_read(row) for row in rows]
    return ApplicationsRead(
        total=len(applications),
        pending=sum(1 for a in applications if a.status == "PENDING"),
        applied=sum(1 for a in applications if a.status in {"APPLIED", "SCREENING", "ASSESSMENT"}),
        interviewing=sum(1 for a in applications if a.status in {"INTERVIEW", "OFFER"}),
        offer=sum(1 for a in applications if a.status == "OFFER"),
        applications=applications,
    )


@router.get("/applications", response_model=ApplicationsRead)
def list_all_applications(db: Session = Depends(get_db)):
    """全局投递记录（跨档案）。

    单用户本地场景下，岗位可能挂在不同档案上；「加入投递台」按岗位所属档案
    建记录，若投递页只按当前档案查询就会看不到。这里提供全局视图兜底。
    """
    rows = list(
        db.scalars(select(models.JobApplication).order_by(models.JobApplication.updated_at.desc())).all()
    )
    applications = [_application_read(row) for row in rows]
    return ApplicationsRead(
        total=len(applications),
        pending=sum(1 for a in applications if a.status == "PENDING"),
        applied=sum(1 for a in applications if a.status in {"APPLIED", "SCREENING", "ASSESSMENT"}),
        interviewing=sum(1 for a in applications if a.status in {"INTERVIEW", "OFFER"}),
        offer=sum(1 for a in applications if a.status == "OFFER"),
        applications=applications,
    )


@router.post("/profiles/{profile_id}/applications", response_model=ApplicationRead, status_code=201)
def create_application(profile_id: UUID, payload: ApplicationCreate, db: Session = Depends(get_db)):
    _profile(db, profile_id)
    status = payload.status.upper()
    if status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=422, detail=f"无效的投递状态：{payload.status}")
    row = models.JobApplication(
        profile_id=profile_id,
        mission_id=payload.mission_id,
        company=payload.company.strip(),
        role=payload.role.strip(),
        location=payload.location,
        channel=payload.channel.strip() or "官网",
        status=status,
        applied_at=payload.applied_at,
        next_action=payload.next_action,
        notes=payload.notes,
        jd_source=payload.jd_source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _application_read(row)


@router.patch("/applications/{application_id}", response_model=ApplicationRead)
def update_application(application_id: UUID, payload: ApplicationUpdate, db: Session = Depends(get_db)):
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        status = str(updates["status"]).upper()
        if status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=422, detail=f"无效的投递状态：{updates['status']}")
        # 状态可前进、也可退回上一阶段（允许误点修正）；CLOSED 为终态。
        _validate_status_transition(row.status, status)
        updates["status"] = status
    for key, value in updates.items():
        if value is None and key not in {"location", "applied_at", "next_action", "notes"}:
            continue
        setattr(row, key, value)
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _application_read(row)


@router.delete("/applications/{application_id}", status_code=204)
def delete_application(application_id: UUID, db: Session = Depends(get_db)):
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    db.delete(row)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# 投递版本绑定（M3：回答「我当初投的是哪份简历」）
# ---------------------------------------------------------------------------


class BindResumeRequest(BaseModel):
    resume_version_id: UUID | None = None
    mission_id: UUID | None = None


def _snapshot_dir() -> Path:
    from .local_mode import ensure_dirs

    directory = ensure_dirs() / "pdf_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@router.post("/applications/{application_id}/bind-resume", response_model=ApplicationRead)
def bind_resume(application_id: UUID, payload: BindResumeRequest, db: Session = Depends(get_db)):
    """把一份岗位定向简历（含 Studio 修订号 + PDF 快照）绑定到投递记录。

    只允许绑定 **Studio 已确认** 的版本：投出去的简历必须是用户确认过的内容。
    快照渲染后存本地文件；之后 Studio 再怎么改，都不影响这份记录指向的证据。
    """
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")

    mission_id = payload.mission_id or row.mission_id
    resume = None
    if payload.resume_version_id:
        resume = db.get(models.TargetResume, payload.resume_version_id)
        if resume is None:
            raise HTTPException(status_code=404, detail="指定的简历版本不存在")
    elif mission_id:
        resume = db.scalar(
            select(models.TargetResume)
            .where(models.TargetResume.mission_id == mission_id, models.TargetResume.status == "CONFIRMED")
            .order_by(models.TargetResume.version.desc())
        )
    if resume is None:
        raise HTTPException(status_code=409, detail="还没有可绑定的已确认岗位简历。请先在「岗位简历」页生成并确认改写稿。")

    # 快照：用该简历所属 mission 的 Studio 文档渲染（必须已确认当前修订版）
    from .resume_studio_render import ResumeRenderError, render_document
    from .resume_studio_service import get_or_create_document

    studio = get_or_create_document(db, resume.mission_id)
    if studio.confirmed_revision != studio.revision:
        raise HTTPException(409, "工作台最新修订版还没有确认。请先在 Studio 确认，再绑定投递版本。")
    try:
        rendered = render_document(
            studio.document_json,
            studio.template_id,
            getattr(studio, "layout_config", None),
        )
    except ResumeRenderError as exc:
        raise HTTPException(409, f"PDF 渲染失败：{exc}") from exc
    snapshot_path = _snapshot_dir() / f"{row.id}.pdf"
    snapshot_path.write_bytes(rendered.pdf)

    row.resume_version_id = resume.id
    row.studio_revision = studio.revision
    row.pdf_snapshot_path = str(snapshot_path)
    if mission_id and not row.mission_id:
        row.mission_id = mission_id
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _application_read(row)


@router.get("/applications/{application_id}/resume-snapshot")
def download_resume_snapshot(application_id: UUID, db: Session = Depends(get_db)):
    """下载投递时的 PDF 快照——随时回答「我当初投的是哪份简历」。"""
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if not row.pdf_snapshot_path or not Path(row.pdf_snapshot_path).exists():
        raise HTTPException(404, "这份投递还没有 PDF 快照。可在投递详情里绑定简历版本后自动生成。")
    data = Path(row.pdf_snapshot_path).read_bytes()
    filename = f"{row.company}-{row.role}-投递快照.pdf"
    from urllib.parse import quote

    ascii_fallback = "".join(char for char in filename if char.isascii() and (char.isalnum() or char in "-_ ")).strip() or "snapshot"
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={ascii_fallback}.pdf; filename*=UTF-8''{quote(filename)}.pdf"
        },
    )


# ---------------------------------------------------------------------------
# 打招呼话术（M3：生成草稿，不自动发送）
# ---------------------------------------------------------------------------


@router.post("/applications/{application_id}/greeting", response_model=ApplicationRead)
def generate_greeting(application_id: UUID, db: Session = Depends(get_db)):
    """生成简洁版 + 详细版打招呼话术草稿（覆盖已有草稿；用户可再手动编辑）。"""
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    greetings = build_greetings(db, row)
    row.greeting_short = greetings["short"]
    row.greeting_long = greetings["long"]
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _application_read(row)


# ---------------------------------------------------------------------------
# 求职看板（M3：复用 JobApplication 单一事实来源，不建第二套表）
# ---------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/applications/board")
def application_board(profile_id: UUID, db: Session = Depends(get_db)):
    """看板聚合：按状态分列 + 阶段数量 + 版本使用记录 + 最近面试待办 + 提醒。"""
    _profile(db, profile_id)
    rows = list(
        db.scalars(
            select(models.JobApplication)
            .where(models.JobApplication.profile_id == profile_id)
            .order_by(models.JobApplication.updated_at.desc())
        ).all()
    )
    columns = {status: [] for status in APPLICATION_STATUSES}
    for row in rows:
        columns.setdefault(row.status, []).append(_application_read(row))

    # 版本使用记录：哪些投递绑定了哪些简历版本（同一版本被多次使用也如实列出）
    version_usage: dict[str, dict] = {}
    for row in rows:
        if not row.resume_version_id:
            continue
        key = str(row.resume_version_id)
        entry = version_usage.setdefault(
            key,
            {"resume_version_id": key, "resume_version": row.resume_version.version if row.resume_version else None, "studio_revision": row.studio_revision, "used_by": []},
        )
        entry["used_by"].append({"application_id": str(row.id), "company": row.company, "role": row.role, "status": row.status})

    # 最近面试记录（InterviewRecord 复用既有表，不建第二套事实来源）
    interview_rows = list(
        db.scalars(
            select(models.InterviewRecord)
            .where(models.InterviewRecord.profile_id == profile_id)
            .order_by(models.InterviewRecord.updated_at.desc())
            .limit(5)
        ).all()
    )
    interviews = [
        {
            "id": str(item.id),
            "company": item.company or "",
            "role": item.role or "",
            "interviewed_on": item.interviewed_on.isoformat() if item.interviewed_on else None,
            "interview_round": item.interview_round or "",
            "status": item.status or "",
            "notes": item.notes or "",
        }
        for item in interview_rows
    ]

    # 应用内提醒（明确：这是应用内提醒，不宣称系统推送）
    reminder_rows = list(
        db.scalars(
            select(models.Reminder)
            .where(models.Reminder.profile_id == profile_id, models.Reminder.status == "PENDING")
            .order_by(models.Reminder.due_at.asc().nullslast())
            .limit(10)
        ).all()
    )
    reminders = [
        {"id": str(item.id), "title": item.title, "due_at": item.due_at.isoformat() if item.due_at else None}
        for item in reminder_rows
    ]

    return {
        "total": len(rows),
        "columns": {status: {"count": len(items), "applications": items} for status, items in columns.items()},
        "version_usage": list(version_usage.values()),
        "recent_interviews": interviews,
        "reminders": reminders,
        "reminder_note": "提醒仅在应用内展示，不会发送系统推送。",
    }


# ---------------------------------------------------------------------------
# 提醒 CRUD（M3：应用内提醒，不宣称系统推送）
# ---------------------------------------------------------------------------


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    due_at: datetime | None = None
    notes: str | None = None


class ReminderRead(BaseModel):
    id: str
    title: str
    due_at: datetime | None = None
    status: str
    created_at: datetime | None = None


@router.get("/profiles/{profile_id}/reminders", response_model=list[ReminderRead])
def list_reminders(profile_id: UUID, db: Session = Depends(get_db)):
    _profile(db, profile_id)
    rows = list(
        db.scalars(
            select(models.Reminder)
            .where(models.Reminder.profile_id == profile_id)
            .order_by(models.Reminder.due_at.asc().nullslast())
        ).all()
    )
    return [
        ReminderRead(id=str(row.id), title=row.title, due_at=row.due_at, status=row.status, created_at=row.created_at)
        for row in rows
    ]


@router.post("/profiles/{profile_id}/reminders", response_model=ReminderRead, status_code=201)
def create_reminder(profile_id: UUID, payload: ReminderCreate, db: Session = Depends(get_db)):
    _profile(db, profile_id)
    row = models.Reminder(profile_id=profile_id, title=payload.title.strip(), due_at=payload.due_at)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ReminderRead(id=str(row.id), title=row.title, due_at=row.due_at, status=row.status, created_at=row.created_at)


@router.post("/reminders/{reminder_id}/complete", response_model=ReminderRead)
def complete_reminder(reminder_id: UUID, db: Session = Depends(get_db)):
    row = db.get(models.Reminder, reminder_id)
    if row is None:
        raise HTTPException(status_code=404, detail="提醒不存在")
    row.status = "DONE"
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return ReminderRead(id=str(row.id), title=row.title, due_at=row.due_at, status=row.status, created_at=row.created_at)


# ---------------------------------------------------------------------------
# Plaza（岗位广场）
# ---------------------------------------------------------------------------


@router.get("/plaza", response_model=PlazaRead)
def read_plaza(profile_id: UUID | None = None, db: Session = Depends(get_db)):
    query = select(models.JobMission).where(models.JobMission.status != "ARCHIVED")
    if profile_id is not None:
        query = query.where(models.JobMission.profile_id == profile_id)
    missions = list(db.scalars(query.order_by(models.JobMission.updated_at.desc())).all())

    mission_ids = [m.id for m in missions]
    applications_by_mission: dict[UUID, models.JobApplication] = {}
    if mission_ids:
        app_rows = db.scalars(
            select(models.JobApplication)
            .where(models.JobApplication.mission_id.in_(mission_ids))
            .order_by(models.JobApplication.updated_at.desc())
        ).all()
        for row in app_rows:
            if row.mission_id not in applications_by_mission:
                applications_by_mission[row.mission_id] = row

    target_resumes_by_mission: dict[UUID, bool] = {}
    if mission_ids:
        resume_rows = db.scalars(
            select(models.TargetResume).where(models.TargetResume.mission_id.in_(mission_ids))
        ).all()
        for row in resume_rows:
            if row.status == "CONFIRMED":
                target_resumes_by_mission[row.mission_id] = True

    items: list[PlazaItem] = []
    for mission in missions:
        application = applications_by_mission.get(mission.id)
        confirmed = bool(target_resumes_by_mission.get(mission.id))
        insight = cached_insight(mission)
        items.append(
            PlazaItem(
                mission_id=str(mission.id),
                profile_id=str(mission.profile_id),
                company=mission.company,
                role=mission.role,
                location=mission.location,
                seniority=mission.seniority,
                workflow_state=mission.workflow_state,
                prep_score=_prep_score(mission.workflow_state, target_resume_confirmed=confirmed),
                keywords=insight["keywords"],
                job_summary=insight["summary"],
                analysis_source=insight["analysis_source"],
                match_score=insight["match_score"],
                match_verdict=insight["match_verdict"],
                match_verdict_label=insight["match_verdict_label"],
                match_source=insight["match_source"],
                resume_ready=bool(mission.resume_source),
                target_resume_confirmed=confirmed,
                application_id=str(application.id) if application else None,
                application_status=application.status if application else None,
                updated_at=mission.updated_at,
            )
        )

    return PlazaRead(
        total=len(items),
        applied=sum(1 for i in items if i.application_id),
        ready=sum(1 for i in items if i.target_resume_confirmed),
        items=items,
    )
