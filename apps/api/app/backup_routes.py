"""本地模式 / 数据备份与恢复路由。"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import backup_service as backup
from . import local_mode
from . import models
from .database import get_db

router = APIRouter(prefix="/api/v1")


def _model_configured() -> bool:
    """模型是否已可用：页面保存的配置，或旧版 .env 环境变量。"""
    from .model_config_service import try_llm_settings

    return try_llm_settings("resume") is not None


def _local_status() -> dict:
    resolved = local_mode.resolve_database_url()
    root = local_mode.data_root()
    explicit = os.getenv("DATABASE_URL", "").strip()
    return {
        "local_mode": root is not None,
        "data_dir": str(root) if root else None,
        "default_data_dir": str(local_mode.default_data_root()),
        "database_url_scheme": resolved.split("://", 1)[0] if resolved else None,
        "using_dataset": bool(root) and resolved != explicit,
        "active_dataset_id": local_mode.active_dataset_id(root) if root else None,
        "model_configured": _model_configured(),
        "backup_supported": resolved.startswith("sqlite"),
    }


@router.get("/local/status")
def read_local_status() -> dict:
    return _local_status()


@router.get("/local/datasets")
def read_datasets() -> dict:
    return {"local_mode": local_mode.data_root() is not None, "datasets": backup.list_datasets()}


@router.post("/local/datasets/{dataset_id}/activate")
def activate_dataset(dataset_id: str) -> dict:
    root = local_mode.data_root()
    if root is None:
        raise HTTPException(409, "本地数据集模式未启用（启动时请设置 AI_CAREER_DATA_DIR）。")
    path = local_mode.dataset_db_path(dataset_id, root)
    if not path.exists():
        raise HTTPException(404, f"数据集不存在：{dataset_id}")
    local_mode.set_active_dataset(dataset_id, root)
    return {"active_dataset_id": dataset_id, "database_file": str(path)}


@router.get("/backup/export")
def export_backup(label: str = "本地数据集") -> Response:
    url = local_mode.resolve_database_url()
    if not url.startswith("sqlite"):
        raise HTTPException(409, "当前不是 SQLite 数据集，暂不支持在线导出备份。")
    filename, blob = backup.build_archive(url, dataset_label=label)
    return Response(
        blob,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=backup.zip; filename*=UTF-8''{filename}",
            "X-Backup-Size": str(len(blob)),
        },
    )


@router.post("/backup/inspect")
async def inspect_backup(file: UploadFile = File(...)) -> dict:
    blob = await file.read()
    try:
        return backup.inspect_archive(blob)
    except local_mode.DatasetError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/backup/restore")
async def restore_backup(file: UploadFile = File(...), label: str | None = None) -> dict:
    if local_mode.data_root() is None:
        raise HTTPException(409, "恢复需要本地数据集模式（启动时设置 AI_CAREER_DATA_DIR）。")
    blob = await file.read()
    try:
        return backup.restore_as_new_dataset(blob, label=label)
    except local_mode.DatasetError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/backup/summary")
def backup_summary(db: Session = Depends(get_db)) -> dict:
    """当前数据集的关键记录计数（统计基于真实记录，不用样例冒充）。"""
    counts: dict[str, int] = {}
    for name in backup.COUNTED_TABLES:
        model = getattr(models, _model_name(name), None)
        if model is None:
            continue
        try:
            counts[name] = int(db.scalar(select(func.count()).select_from(model)) or 0)
        except Exception:  # noqa: BLE001 - 表可能尚未迁移，跳过即可
            continue
    return {"counts": counts, "status": _local_status()}


def _model_name(table: str) -> str:
    return {
        "user_profiles": "UserProfile",
        "education": "Education",
        "experiences": "Experience",
        "profile_skills": "ProfileSkill",
        "certifications": "Certification",
        "application_profiles": "ApplicationProfile",
        "job_missions": "JobMission",
        "target_resumes": "TargetResume",
        "target_resume_bullets": "TargetResumeBullet",
        "resume_studio_documents": "ResumeStudioDocument",
        "job_applications": "JobApplication",
        "candidate_jobs": "CandidateJob",
        "interview_records": "InterviewRecord",
        "resume_claims": "ResumeClaim",
        "job_descriptions": "JobDescription",
        "web_form_records": "WebFormRecord",
    }[table]
