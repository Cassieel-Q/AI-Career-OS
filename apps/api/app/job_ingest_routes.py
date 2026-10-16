"""岗位统一入口路由：粘贴 / 公开链接 / 文件 / 真实来源采集 + 筛选 + 去重。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import candidate_job_service as candidate_svc
from . import job_ingest_service as ingest
from . import job_ingest_tasks as tasks
from . import models
from . import webform_browser as browser
from .database import get_db

router = APIRouter(prefix="/api/v1")


class FetchUrlRequest(BaseModel):
    url: str = Field(min_length=4)


class RemoteOkRequest(BaseModel):
    tag: str | None = None
    limit: int = 20


class CollectRequest(BaseModel):
    """一键采集：多关键词 + 城市 + 实习/全职 + 发布时间 + 来源。"""

    model_config = ConfigDict(extra="ignore")

    keywords: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=lambda: ["remoteok"])
    location: str | None = None
    employment_type: str | None = Field(default=None, description="INTERN | FULLTIME | ANY")
    posted_within_days: int | None = None
    limit: int = 20
    greenhouse_boards: list[str] = Field(default_factory=list)
    lever_companies: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, description="整轮采集时间上限（秒），超时后剩余来源不再请求")


class SaveCollectedRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jobs: list[dict] = Field(default_factory=list)
    #: 采集结果被判定为 UPDATED（同岗位 JD 有变化）时，是否更新已有记录。
    update_duplicates: bool = False


#: 排序即 UI 展示顺序：先「不需要配置就能采」的来源。
_SOURCE_ORDER = ["remoteok", "remotive", "greenhouse", "lever", "browser", "paste", "file"]
_SOURCE_LABELS = {
    "paste": ("粘贴完整 JD", "任何平台都可用的兜底方式，正文由用户提供（BOSS / 实习僧 / 脉脉等需登录平台的合规入口）。"),
    "file": ("岗位截图 / PDF / 文档", "PDF / 文本 / Word 可直接解析；图片暂不支持自动 OCR，需手动粘贴。"),
    "browser": ("采集当前招聘网页", "复用本地受控浏览器桥，读取你在浏览器里打开的招聘页面；只读取页面可见内容，不绕过登录与验证码。"),
}


@router.get("/job-ingest/sources")
def list_sources() -> dict:
    """来源清单：能力、筛选方式、是否需要配置、可用预设都如实返回。"""
    items = []
    for source in _SOURCE_ORDER:
        spec = ingest.adapter_spec(source)
        if not spec:
            continue
        label, note = _SOURCE_LABELS.get(source, (spec.get("label", source), spec.get("note", "")))
        items.append(
            {
                "id": source,
                "label": label,
                "mode": spec.get("mode", "adapter"),
                "auto_collect": source not in {"paste"},
                "note": note,
                "capabilities": spec.get("capabilities", {}),
                "filter_mode": spec.get("filter_mode", "local"),
                "requires_config": spec.get("requires_config", False),
                "config_key": spec.get("config_key"),
                "config_placeholder": spec.get("config_placeholder"),
                "presets": spec.get("presets", []),
                "preset_verified_at": spec.get("preset_verified_at"),
                "has_collect": spec.get("has_collect", False),
            }
        )
    return {"sources": items}


@router.get("/job-ingest/adapters")
def list_adapters() -> dict:
    """适配器契约快照（用于自检与文档）：每个来源声明自己的真实能力。"""
    return {
        "schema": ingest.JOB_SCHEMA,
        "result_states": list(tasks.RESULT_STATES),
        "task_states": [tasks.TASK_IDLE, tasks.TASK_RUNNING, tasks.TASK_COMPLETED, tasks.TASK_PARTIAL, tasks.TASK_FAILED, tasks.TASK_CANCELLED],
        "contract": ["source_id", "capabilities", "search_or_collect", "normalize", "validate", "deduplicate", "health_check"],
        "adapters": [ingest.adapter_spec(name) for name in _SOURCE_ORDER if ingest.adapter_spec(name)],
    }


class HealthCheckRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    greenhouse_boards: list[str] = Field(default_factory=list)
    lever_companies: list[str] = Field(default_factory=list)


@router.post("/job-ingest/adapters/{source}/health-check")
def adapter_health_check(source: str, payload: HealthCheckRequest | None = None) -> dict:
    """来源可用性自检：真实发一次请求，失败如实返回 ERROR（不返回演示数据）。"""
    body = payload or HealthCheckRequest()
    if ingest.adapter_spec(source) is None:
        raise HTTPException(404, f"未知来源：{source}")
    return ingest.health_check(source, greenhouse_boards=body.greenhouse_boards, lever_companies=body.lever_companies)


@router.post("/job-ingest/fetch-url")
def fetch_url(payload: FetchUrlRequest) -> dict:
    return ingest.fetch_url_text(payload.url)


@router.post("/job-ingest/extract-file")
async def extract_file(file: UploadFile = File(...)) -> dict:
    blob = await file.read()
    if not blob:
        raise HTTPException(422, "文件为空。")
    text, status = ingest.extract_file_text(file.filename or "", blob)
    note = {
        "PARSED": "已解析文件正文。",
        "PARSE_EMPTY": "文件里没有可提取的文本。",
        "UNSUPPORTED_IMAGE": "图片暂不支持自动 OCR，请把岗位描述复制成文本后粘贴。",
        "UNSUPPORTED_TYPE": "暂不支持该文件类型，请粘贴文本或改用 PDF/txt/docx。",
    }.get(status, "")
    return {"filename": file.filename, "status": status, "text": text, "note": note, "size_bytes": len(blob)}


@router.post("/job-ingest/collect")
def collect_jobs(payload: CollectRequest) -> dict:
    """一键采集：多关键词 + 城市 + 实习/全职 + 发布时间窗口 + 多来源。

    失败时如实返回每个来源的错误，不回退任何演示数据。
    """
    return ingest.run_collection(
        sources=payload.sources,
        keywords=payload.keywords,
        location=payload.location,
        employment_type=payload.employment_type,
        posted_within_days=payload.posted_within_days,
        limit=payload.limit,
        greenhouse_boards=payload.greenhouse_boards,
        lever_companies=payload.lever_companies,
    )


@router.post("/profiles/{profile_id}/job-ingest/collect-runs")
def start_collect_run(profile_id: UUID, payload: CollectRequest) -> dict:
    """启动一次采集任务：立即返回 task_id，前端轮询进度，支持中途取消。"""
    _ensure_profile(str(profile_id))
    request = payload.model_dump()
    # limit 上限，避免一次拉太多把公开接口打爆
    request["limit"] = max(1, min(int(payload.limit or 20), 50))
    request["timeout_seconds"] = payload.timeout_seconds
    return tasks.submit(str(profile_id), request)


@router.get("/job-ingest/collect-runs/{task_id}")
def read_collect_run(task_id: str) -> dict:
    snapshot = tasks.get_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(404, "采集任务不存在或已被清理。")
    return snapshot


@router.post("/job-ingest/collect-runs/{task_id}/cancel")
def cancel_collect_run(task_id: str) -> dict:
    snapshot = tasks.cancel_task(task_id)
    if snapshot is None:
        raise HTTPException(404, "采集任务不存在或已被清理。")
    return snapshot


@router.get("/profiles/{profile_id}/job-ingest/collect-runs")
def list_collect_runs(profile_id: UUID, limit: int = Query(default=10, ge=1, le=50)) -> dict:
    return {"tasks": tasks.recent_tasks(profile_id=str(profile_id), limit=limit)}


@router.post("/job-ingest/collect-remoteok")
def collect_remoteok(payload: RemoteOkRequest) -> dict:
    """（保留兼容） RemoteOK 单关键词采集。"""
    return ingest.collect_remoteok(tag=payload.tag, limit=payload.limit, keywords=[payload.tag] if payload.tag else [])


@router.get("/job-ingest/bridge-status")
def bridge_status() -> dict:
    return browser.health()


@router.post("/job-ingest/collect-browser")
def collect_browser() -> dict:
    """采集「当前招聘网页」——只预览，不入库。

    复用网申填表那套受控浏览器桥；只读取页面已可见内容，
    遇到登录 / 验证码 / 列表页无法可靠读取时返回明确状态，不猜测、不伪造。
    """
    try:
        captured = browser.extract_job()
    except browser.BrowserBridgeError as exc:
        raise HTTPException(503, str(exc)) from exc

    status = captured.get("status") or "EMPTY"
    if status in {"BLOCKED", "LISTING_UNSUPPORTED", "EMPTY", "ERROR"}:
        return {
            "status": status,
            "page_url": captured.get("page_url"),
            "page_title": captured.get("page_title"),
            "note": captured.get("note", ""),
            "job": None,
        }

    job = ingest.normalize_browser_capture(captured)
    return {
        "status": "OK",
        "page_url": captured.get("page_url"),
        "page_title": captured.get("page_title"),
        "note": captured.get("note", ""),
        "confidence": captured.get("confidence", {}),
        "job": job,
    }


@router.post("/profiles/{profile_id}/job-ingest/save-collected")
def save_collected(profile_id: UUID, payload: SaveCollectedRequest, db: Session = Depends(get_db)) -> dict:
    """把采集到的真实岗位保存进候选岗位库（复用既有 parse/confirm/import 链路）。

    - 库里已有且正文一致 → ``DUPLICATE`` 跳过；
    - 库里已有但 JD 有变化 → 默认 ``UPDATED_KEPT`` 跳过，``update_duplicates=True`` 时才更新；
    - 字段缺失/低置信 → 仍然保存，但 ``parse_status = NEEDS_CONFIRM``，导入正式岗位前必须补齐。
    """
    saved: list[dict] = []
    skipped: list[dict] = []
    updated: list[dict] = []
    for job in payload.jobs:
        text = (job.get("text") or "").strip()
        if not text:
            skipped.append({"job": job, "reason": "缺少文本"})
            continue
        duplicates = ingest.find_duplicates(db, profile_id, job.get("company"), job.get("role"), job.get("location"))
        if duplicates:
            incoming_hash = job.get("content_hash") or ingest.content_hash(job.get("role"), job.get("location"), job.get("text"))
            if payload.update_duplicates:
                touched = _apply_update(db, duplicates, job)
                if touched:
                    updated.append({"company": job.get("company"), "role": job.get("role"), "reason": "UPDATED", "targets": touched})
                    continue
            changed = [row for row in duplicates if not _same_hash(db, row, incoming_hash)]
            skipped.append(
                {
                    "company": job.get("company"),
                    "role": job.get("role"),
                    "reason": "UPDATED" if changed else "DUPLICATE",
                    "matches": duplicates,
                }
            )
            continue
        rows = candidate_svc.parse_candidates(db, profile_id, text, source_kind="LINK")
        # 一条采集结果 = 一条候选岗位：保留信息最全的那条，避免同一岗位被拆成多条草稿。
        if len(rows) > 1:
            keep = max(rows, key=lambda row: len(row.source_excerpt or ""))
            for row in rows:
                if row is not keep:
                    db.delete(row)
            rows = [keep]
        source_key = job.get("dedupe_key") or ingest.dedupe_key(job.get("company"), job.get("role"), job.get("location"))
        needs_confirm = list(job.get("needs_confirm") or [])
        # 采集结构里的公司/岗位/地点/JD 比启发式切分更可信，缺项时按来源补齐。
        for row in rows:
            row.source_url = (job.get("source_url") or "")[:1024] or None
            row.collected_at = _now()
            row.parse_status = "NEEDS_CONFIRM" if needs_confirm else "PARSED"
            row.dedupe_key = source_key
            # 采集结构里的公司/岗位/地点比启发式切分更可信：来源给了就用来源的。
            # 旧实现只在启发式结果为空时才补齐，结果 RemoteOK 岗位被启发式切成
            # 「Remote / Independent Contractor」（取自 JD 首行）并一路带进岗位库，
            # 用户在库里看到的是错误公司名与岗位名。
            row.company = (job.get("company") or "").strip() or row.company
            row.role = (job.get("role") or "").strip() or row.role
            row.location = (job.get("location") or "").strip() or row.location
            # 保留来源原文与结构化字段，便于回溯与「待确认」字段后续补齐。
            row.raw_payload = {
                "source": job.get("source"),
                "apply_url": job.get("apply_url") or "",
                "posted_at": job.get("posted_at"),
                "employment_type": job.get("employment_type") or "UNKNOWN",
                "tags": job.get("tags") or [],
                "needs_confirm": needs_confirm,
                "source_url": job.get("source_url") or "",
                "collected_at": job.get("collected_at"),
                "content_hash": job.get("content_hash") or ingest.content_hash(job.get("role"), job.get("location"), job.get("text")),
            }
            # 公司/岗位缺失时暂存待确认标记，导入正式岗位前 UI 会要求补齐。
            if needs_confirm and not (row.company or "").strip():
                row.company = job.get("company") or None
        db.commit()
        saved.append(
            {
                "source": job.get("source"),
                "source_url": job.get("source_url"),
                "company": job.get("company"),
                "role": job.get("role"),
                "location": job.get("location"),
                "parse_status": "NEEDS_CONFIRM" if needs_confirm else "PARSED",
                "needs_confirm": needs_confirm,
                "candidate_ids": [str(row.id) for row in rows],
            }
        )
    db.commit()
    return {
        "saved": saved,
        "updated": updated,
        "skipped": skipped,
        "saved_count": len(saved),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
    }


def _load_duplicate_row(db: Session, kind: str, raw_id: str | None):
    """``find_duplicates`` 返回的是字符串 id，直接喂给 ``Session.get`` 会因为 Uuid 列类型炸掉。"""
    from uuid import UUID as _UUID

    try:
        identifier = _UUID(str(raw_id))
    except (TypeError, ValueError):
        return None
    model = models.CandidateJob if kind == "CANDIDATE" else models.JobMission
    return db.get(model, identifier)


def _same_hash(db: Session, duplicate: dict, incoming_hash: str) -> bool:
    """已有记录与本次采集的正文指纹是否一致（旧记录没有指纹时用同一口径现算）。"""
    if not incoming_hash:
        return True
    row = _load_duplicate_row(db, duplicate.get("kind"), duplicate.get("id"))
    if row is None:
        return False
    if duplicate.get("kind") == "CANDIDATE":
        payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        stored_hash = payload.get("content_hash")
        if not stored_hash:
            # 存量记录（指纹回填之前入库）没有 content_hash：按同一口径现算正文指纹再比。
            stored_hash = ingest.content_hash(row.role, row.location, row.source_text)
        return stored_hash == incoming_hash
    payload = row.resume_source if isinstance(row.resume_source, dict) else {}
    return payload.get("content_hash") == incoming_hash


def _apply_update(db: Session, duplicates: list[dict], job: dict) -> list[dict]:
    """把新采集到的 JD 覆盖到已有候选岗位（只更新内容类字段，不动用户已有的状态）。"""
    touched: list[dict] = []
    incoming_hash = job.get("content_hash") or ingest.content_hash(job.get("role"), job.get("location"), job.get("text"))
    for duplicate in duplicates:
        if duplicate.get("kind") != "CANDIDATE":
            continue
        row = _load_duplicate_row(db, "CANDIDATE", duplicate.get("id"))
        if row is None:
            continue
        if (job.get("role") or "").strip():
            row.role = job.get("role")
        if (job.get("company") or "").strip():
            row.company = job.get("company")
        if (job.get("location") or "").strip():
            row.location = job.get("location")
        row.source_url = (job.get("source_url") or "")[:1024] or None
        row.source_excerpt = (job.get("jd_excerpt") or job.get("text") or "")[:2000] or row.source_excerpt
        row.source_text = job.get("text") or row.source_text
        row.collected_at = _now()
        payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        payload.update(
            {
                "source": job.get("source", payload.get("source")),
                "apply_url": job.get("apply_url") or payload.get("apply_url", ""),
                "posted_at": job.get("posted_at") or payload.get("posted_at"),
                "employment_type": job.get("employment_type") or payload.get("employment_type") or "UNKNOWN",
                "tags": job.get("tags") or payload.get("tags") or [],
                "needs_confirm": job.get("needs_confirm") or [],
                "source_url": job.get("source_url") or payload.get("source_url", ""),
                "collected_at": job.get("collected_at") or payload.get("collected_at"),
                "content_hash": incoming_hash,
            }
        )
        row.raw_payload = payload
        row.parse_status = "NEEDS_CONFIRM" if job.get("needs_confirm") else "PARSED"
        touched.append({"kind": "CANDIDATE", "id": str(row.id)})
    return touched


@router.get("/profiles/{profile_id}/job-ingest/library")
def job_library(
    profile_id: UUID,
    q: str | None = Query(default=None, description="关键词：公司/岗位/原文"),
    company: str | None = None,
    location: str | None = None,
    kind: str | None = Query(default=None, description="candidate | mission"),
    db: Session = Depends(get_db),
) -> dict:
    """统一岗位库视图：候选草稿 + 已保存岗位，支持关键词/公司/地点筛选。"""
    needle = (q or "").strip().lower()

    def matches(company_value: str | None, role_value: str | None, location_value: str | None, text: str) -> bool:
        if company and (company_value or "").strip().lower() != company.strip().lower():
            return False
        if location and location.strip().lower() not in (location_value or "").strip().lower():
            return False
        if needle:
            haystack = " ".join([company_value or "", role_value or "", location_value or "", text or ""]).lower()
            if needle not in haystack:
                return False
        return True

    items: list[dict] = []

    if kind in (None, "candidate"):
        candidates = db.scalars(
            select(models.CandidateJob).where(models.CandidateJob.profile_id == profile_id)
        ).all()
        for row in candidates:
            if not matches(row.company, row.role, row.location, row.source_excerpt or row.source_text):
                continue
            items.append(
                {
                    "kind": "CANDIDATE",
                    "id": str(row.id),
                    "company": row.company,
                    "role": row.role,
                    "location": row.location,
                    "status": row.status,
                    "source_kind": row.source_kind,
                    "source_url": getattr(row, "source_url", None),
                    "collected_at": _iso(getattr(row, "collected_at", None)),
                    "parse_status": getattr(row, "parse_status", None) or "PARSED",
                    "imported_mission_id": str(row.imported_mission_id) if row.imported_mission_id else None,
                    "excerpt": (row.source_excerpt or "")[:400],
                    "needs_confirm": (row.raw_payload or {}).get("needs_confirm", []) if isinstance(row.raw_payload, dict) else [],
                }
            )

    if kind in (None, "mission"):
        missions = db.scalars(select(models.JobMission).where(models.JobMission.profile_id == profile_id)).all()
        for row in missions:
            if not matches(row.company, row.role, row.location, row.parsed_jd.get("raw_text", "") if isinstance(row.parsed_jd, dict) else ""):
                continue
            items.append(
                {
                    "kind": "MISSION",
                    "id": str(row.id),
                    "company": row.company,
                    "role": row.role,
                    "location": row.location,
                    "status": row.status,
                    "workflow_state": row.workflow_state,
                    "source_url": (row.resume_source or {}).get("source_url") if isinstance(row.resume_source, dict) else None,
                    "collected_at": None,
                    "parse_status": "PARSED",
                    "excerpt": "",
                }
            )

    companies = sorted({item["company"] for item in items if item.get("company")})
    locations = sorted({item["location"] for item in items if item.get("location")})
    return {
        "items": items,
        "count": len(items),
        "facets": {"companies": companies, "locations": locations},
    }


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _ensure_profile(profile_id: str) -> None:
    """采集任务在后台线程执行，无法复用 Depends(get_db)，这里单独校验一次 id 合法性。"""
    from uuid import UUID as _UUID

    try:
        _UUID(str(profile_id))
    except ValueError as exc:
        raise HTTPException(422, "profile_id 不是合法的 UUID。") from exc


def _iso(value):
    return value.isoformat() if value is not None else None
