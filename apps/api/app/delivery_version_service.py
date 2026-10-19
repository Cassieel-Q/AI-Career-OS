"""投递版本解析：回答「我当初投的是哪份简历」（可信求职 v1.2 · 指令 5.3）。

面试准备此前默认读取「最新 Studio 修订版」，会把投递之后才新增的经历当成面试官
已经看到的简历内容。本模块把顺序倒过来：

1. 先找该岗位**真正投递出去**的版本（投递记录绑定的 Studio 修订 + 不可变快照）；
2. 没有投递记录时，才退回「当前准备中的版本」，并明确标注
   「尚无正式投递版本，当前使用准备中的简历。」；
3. 多次投递时，允许明确指定用哪一次。

只读 + 快照写入两类能力，不做任何自动生成或覆盖。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

NO_DELIVERY_LABEL = "尚无正式投递版本，当前使用准备中的简历。"


def content_hash(document: dict) -> str:
    """正文内容的稳定哈希：用于证明快照未被改写。"""
    payload = json.dumps(document or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snapshot_dir() -> Path:
    from .local_mode import ensure_dirs

    directory = ensure_dirs() / "delivery_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def record_snapshot(
    db: Session,
    mission: models.JobMission,
    studio: models.ResumeStudioDocument,
    *,
    application_id: UUID | None = None,
    source: str = "STUDIO_CONFIRM",
    pdf_bytes: bytes | None = None,
    filename: str | None = None,
) -> models.DeliverySnapshot:
    """写入一次正式投递版本的不可变快照。

    同一 ``application_id`` + 同一修订号只保留一条（幂等），避免重复绑定产生多份快照。
    """
    document = studio.document_json or {}
    row = None
    if application_id is not None:
        row = db.scalar(select(models.DeliverySnapshot).where(
            models.DeliverySnapshot.application_id == application_id,
            models.DeliverySnapshot.studio_revision == studio.revision,
        ))
    pdf_path: str | None = None
    if pdf_bytes:
        # 正文快照是主证据，PDF 文件只是附件：磁盘不可写时不能让确认/绑定失败。
        try:
            target = _snapshot_dir() / f"{mission.id}-v{studio.revision}-{abs(hash((str(application_id), source))) % 10**8}.pdf"
            target.write_bytes(pdf_bytes)
            pdf_path = str(target)
        except OSError:
            pdf_path = None
    if row is None:
        row = models.DeliverySnapshot(
            profile_id=mission.profile_id,
            mission_id=mission.id,
            application_id=application_id,
            studio_revision=studio.revision,
            document_json=document,
            content_hash=content_hash(document),
            pdf_path=pdf_path,
            filename=filename,
            source=source,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.document_json = document
        row.content_hash = content_hash(document)
        row.pdf_path = pdf_path or row.pdf_path
        row.filename = filename or row.filename
        row.source = source
    return row


def _bullets_from_document(document: dict) -> list[dict]:
    bullets: list[dict] = []
    for section in document.get("sections") or []:
        for entry in section.get("entries") or []:
            if entry.get("status") == "OMITTED":
                continue
            for bullet in entry.get("bullets") or []:
                if bullet.get("claim_status") == "OMITTED" or not bullet.get("text"):
                    continue
                bullets.append({
                    "source_experience_id": entry.get("id"),
                    "text": bullet["text"],
                    "status": bullet.get("claim_status"),
                    "evidence_refs": bullet.get("evidence_refs") or [],
                })
    return bullets


def _delivered_applications(db: Session, mission_id: UUID) -> list[models.JobApplication]:
    """该岗位已经绑定投递版本的投递记录（按投递时间倒序）。"""
    rows = db.scalars(select(models.JobApplication).where(
        models.JobApplication.mission_id == mission_id,
        models.JobApplication.resume_version_id.is_not(None),
    )).all()
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(row: models.JobApplication) -> str:
        if row.applied_at is not None:
            return row.applied_at.isoformat()
        created = getattr(row, "created_at", None)
        return created.isoformat() if created is not None else epoch.isoformat()

    return sorted(rows, key=sort_key, reverse=True)


def list_delivery_versions(db: Session, mission_id: UUID) -> list[dict]:
    """列出该岗位可用的投递版本，供用户明确选择（指令 5.3：多次投递可选）。"""
    versions: list[dict] = []
    for application in _delivered_applications(db, mission_id):
        snapshot = db.scalar(select(models.DeliverySnapshot).where(
            models.DeliverySnapshot.application_id == application.id,
        ).order_by(models.DeliverySnapshot.created_at.desc()))
        versions.append({
            "application_id": str(application.id),
            "status": application.status,
            "applied_at": application.applied_at.isoformat() if application.applied_at else None,
            "channel": application.channel,
            "studio_revision": application.studio_revision,
            "has_snapshot": snapshot is not None,
            "snapshot_id": str(snapshot.id) if snapshot else None,
            # 正文哈希：用于校验「投出去的那一版」此后没有被改写（只读元数据，不含正文）。
            "content_hash": snapshot.content_hash if snapshot else None,
            "label": f"{application.applied_at.isoformat() if application.applied_at else '未记录日期'} 投递 · 修订版 v{application.studio_revision or '—'}",
        })
    return versions


def resolve_interview_resume(
    db: Session,
    mission: models.JobMission | None,
    *,
    application_id: UUID | None = None,
) -> dict | None:
    """解析面试准备应该使用的简历版本。

    返回结构里的 ``source`` 决定 UI 文案：
    - ``delivered_snapshot``：使用投递快照（最可信，面试官看到的就是这份）；
    - ``delivered_application``：投递记录存在但没有正文快照（退回当前 Studio，标注修订号）；
    - ``studio_current``：尚未投递，使用当前准备中的版本（带 ``NO_DELIVERY_LABEL``）；
    - ``target_resume``：连 Studio 都没有，退回旧版定向简历。
    """
    if mission is None:
        return None

    applications = _delivered_applications(db, mission.id)
    chosen = None
    if application_id is not None:
        chosen = next((row for row in applications if row.id == application_id), None)
        if chosen is None:
            chosen = db.get(models.JobApplication, application_id)
    elif applications:
        chosen = applications[0]

    studio = db.scalar(select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission.id))

    if chosen is not None:
        snapshot = db.scalar(select(models.DeliverySnapshot).where(
            models.DeliverySnapshot.application_id == chosen.id,
        ).order_by(models.DeliverySnapshot.created_at.desc()))
        if snapshot is None:
            # 兼容「先确认修订版生成快照、后建投递记录」的顺序：
            # 同一修订号的快照就是这次投递出去的内容。
            query = select(models.DeliverySnapshot).where(
                models.DeliverySnapshot.mission_id == mission.id,
            ).order_by(models.DeliverySnapshot.created_at.desc())
            candidates = db.scalars(query).all()
            snapshot = next((row for row in candidates if row.studio_revision == chosen.studio_revision), None)
        if snapshot is not None:
            document = snapshot.document_json or {}
            applied = chosen.applied_at.isoformat() if chosen.applied_at else (snapshot.created_at.date().isoformat() if snapshot.created_at else "")
            return {
                "source": "delivered_snapshot",
                "label": f"使用 {applied} 实际投递的版本（Studio 修订 v{snapshot.studio_revision}）",
                "warning": None,
                "application_id": str(chosen.id),
                "snapshot_id": str(snapshot.id),
                "studio_revision": snapshot.studio_revision,
                "delivered_at": applied,
                "content_hash": snapshot.content_hash,
                "has_pdf": bool(snapshot.pdf_path and Path(snapshot.pdf_path).exists()),
                "bullets": _bullets_from_document(document),
                "versions": list_delivery_versions(db, mission.id),
                "delivered": True,
            }
        # 有投递记录但没有正文快照：退回当前 Studio，但明确说明绑定的是哪个修订
        if studio is not None:
            return {
                "source": "delivered_application",
                "label": f"这次投递绑定的是 Studio 修订 v{chosen.studio_revision or '—'}（快照缺失，当前展示工作台内容）",
                "warning": "这份投递没有保存正文快照，当前展示的是工作台最新版本，可能与投递时略有差异。",
                "application_id": str(chosen.id),
                "snapshot_id": None,
                "studio_revision": chosen.studio_revision,
                "delivered_at": chosen.applied_at.isoformat() if chosen.applied_at else None,
                "content_hash": content_hash(studio.document_json or {}),
                "has_pdf": bool(chosen.pdf_snapshot_path and Path(chosen.pdf_snapshot_path).exists()),
                "bullets": _bullets_from_document(studio.document_json or {}),
                "versions": list_delivery_versions(db, mission.id),
                "delivered": True,
            }

    if studio is not None:
        confirmed = studio.confirmed_revision == studio.revision
        if confirmed:
            document = studio.document_json or {}
            return {
                "source": "resume_studio",
                "label": NO_DELIVERY_LABEL,
                "warning": NO_DELIVERY_LABEL,
                "delivered": False,
                "application_id": None,
                "snapshot_id": None,
                "studio_revision": studio.revision,
                "confirmed": True,
                "delivered_at": None,
                "content_hash": content_hash(document),
                "has_pdf": False,
                "bullets": _bullets_from_document(document),
                "versions": list_delivery_versions(db, mission.id),
            }
        # 有未确认的编辑：优先用「最后一次确认」留下的快照，
        # 否则退回旧版定向简历 —— 未确认的编辑不得进入面试（沿用原有安全约定）。
        history = db.scalars(select(models.DeliverySnapshot).where(
            models.DeliverySnapshot.mission_id == mission.id,
            models.DeliverySnapshot.studio_revision == studio.confirmed_revision,
        ).order_by(models.DeliverySnapshot.created_at.desc())).all()
        if history:
            snapshot = history[0]
            return {
                "source": "resume_studio",
                "label": NO_DELIVERY_LABEL,
                "warning": NO_DELIVERY_LABEL,
                "delivered": False,
                "application_id": None,
                "snapshot_id": str(snapshot.id),
                "studio_revision": snapshot.studio_revision,
                "confirmed": True,
                "delivered_at": None,
                "content_hash": snapshot.content_hash,
                "has_pdf": bool(snapshot.pdf_path and Path(snapshot.pdf_path).exists()),
                "bullets": _bullets_from_document(snapshot.document_json or {}),
                "versions": list_delivery_versions(db, mission.id),
            }

    resumes = [row for row in (mission.target_resumes or []) if str(row.status).upper() == "CONFIRMED"]
    if not resumes:
        return None
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    resume = sorted(resumes, key=lambda row: (row.version, row.updated_at or epoch), reverse=True)[0]
    return {
        "source": "target_resume",
        "label": NO_DELIVERY_LABEL,
        "warning": NO_DELIVERY_LABEL,
        "delivered": False,
        "application_id": None,
        "snapshot_id": None,
        "studio_revision": None,
        "resume_version": resume.version,
        "version": resume.version,
        "positioning_statement": resume.positioning_statement,
        "delivered_at": None,
        "content_hash": None,
        "has_pdf": False,
        "bullets": [
            {
                "source_experience_id": str(bullet.source_experience_id) if bullet.source_experience_id else None,
                "text": bullet.final_text or bullet.suggested_text,
                "status": bullet.status,
                "evidence_refs": list(bullet.evidence_refs or []),
            }
            for bullet in resume.bullets
            if bullet.status in {"ACCEPTED", "EDITED"}
        ],
        "versions": [],
    }
