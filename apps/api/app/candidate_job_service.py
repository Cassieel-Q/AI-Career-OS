"""候选岗位暂存区（目标一）。

把「粘贴多份 JD → 直接创建正式岗位」改为
「粘贴 → 生成候选草稿 → 用户逐条确认 → 导入正式 JobMission」。

硬约束（对应设计文档 §3.3）：
1. `source_excerpt` 必须能在 `source_text` 中找到（归一化包含）；
2. 比对忽略空格/换行与全半角，但不做同义替换、不改语义；
3. 无法可靠拆分时返回**一份完整草稿**（`recognition_source=WHOLE_TEXT`）；
4. 不允许模型补充原文里没有的公司/岗位/地点（找不到就置空 + warnings）；
5. 每份候选都带 `recognition_source` / `source_excerpt` / `warnings`；
6. 正式导入幂等（靠 `imported_mission_id` + content_hash 回查）；
7. 提供写入口的只有本模块，助手只能产提案（见 write_proposal_service）。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .job_description_service import content_hash
from .mission_schemas import MissionCreate

SOURCE_KINDS = {"PASTE", "FILE_TXT", "FILE_PDF", "FILE_DOCX", "LINK"}
RECOGNITION_SOURCES = {"MODEL_SPLIT", "HEURISTIC_SPLIT", "MANUAL", "WHOLE_TEXT"}
STATUSES = {"DRAFT", "CONFIRMED", "IMPORTED", "REJECTED"}

_WS_RE = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    """归一化仅用于「是否同一段」比对：去空白、全半角统一、大小写统一。

    **不做**同义替换，不改变语义；原文出处（source_excerpt）本身按原样保存。
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text)
    return _WS_RE.sub("", folded).casefold()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def excerpt_in_source(excerpt: str, source_text: str) -> bool:
    """规则 1：摘录必须能在原文中找到（忽略空白/换行，忽略全半角）。"""
    normalized = normalize_for_match(excerpt)
    if not normalized:
        return False
    return normalized in normalize_for_match(source_text)


# ---------------------------------------------------------------------------
# 拆分
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"^(岗位|职位|招聘|公司|【|\[)?[：: ]*(岗位|职位|招聘)[：:]", re.I)
_IDENTITY_PATTERNS = {
    "company": re.compile(r"公司[：:]\s*([^\s，,；;、]+)"),
    "role": re.compile(r"(岗位|职位|职位名称)[：:]\s*([^\s，,；;、]+)"),
    "location": re.compile(r"(地点|工作地点|城市)[：:]\s*([^\s，,；;、]+)"),
}


def split_source_blocks(source_text: str) -> list[str]:
    """启发式把粘贴原文切成若干段（保持行的连续性，保证摘录可回溯）。"""
    text = (source_text or "").strip()
    if not text:
        return []
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if _TITLE_RE.match(stripped) and len(current) > 2:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)

    merged = [("\n".join(block)).strip() for block in blocks]
    merged = [block for block in merged if len(block) >= 20]
    return merged


def _extract_identity(excerpt: str) -> tuple[str, str, str, list[str]]:
    """从摘录里抽公司/岗位/地点；抽不到就留空（规则 4：不臆造）。"""
    warnings: list[str] = []
    company = role = location = ""
    for line in excerpt.splitlines():
        m = _IDENTITY_PATTERNS["company"].search(line)
        if m and not company:
            company = m.group(1)
        m = _IDENTITY_PATTERNS["role"].search(line)
        if m and not role:
            role = m.group(2)
        m = _IDENTITY_PATTERNS["location"].search(line)
        if m and not location:
            location = m.group(2)
    # 兜底：首行常写「公司 - 岗位」或「公司 | 岗位」
    if not role:
        first = next((line.strip() for line in excerpt.splitlines() if line.strip()), "")
        if " - " in first:
            head, tail = first.split(" - ", 1)
            company = company or head.strip()
            role = tail.strip()
        elif "｜" in first or " | " in first:
            parts = re.split(r"[｜|]", first)
            if len(parts) >= 2:
                company = company or parts[0].strip()
                role = parts[1].strip()
    # 校验：不允许出现原文摘录里没有的公司/岗位/地点
    for field, value in (("company", company), ("role", role), ("location", location)):
        if value and not excerpt_in_source(value, excerpt):
            warnings.append(f"{field}_not_in_source")
            if field == "company":
                company = ""
            elif field == "role":
                role = ""
            else:
                location = ""
    if not role:
        warnings.append("role_missing")
    if not company:
        warnings.append("company_missing")
    return company, role, location, warnings


def build_candidates(source_text: str) -> list[dict]:
    """把原文拆成候选草稿（纯函数，便于单测）。"""
    blocks = split_source_blocks(source_text)
    if not blocks:
        blocks = [source_text.strip()] if source_text.strip() else []
    if not blocks:
        return []

    # 兜底：整段没有可切分的边界时，返回一份完整草稿
    whole = len(blocks) == 1 and normalize_for_match(blocks[0]) == normalize_for_match(source_text)
    candidates: list[dict] = []
    for block in blocks:
        if not excerpt_in_source(block, source_text):
            # 理论上升级路径不该发生；真发生则降级为整篇，保证可回溯
            block = source_text.strip()
        company, role, location, warnings = _extract_identity(block)
        recognition = "WHOLE_TEXT" if whole else "HEURISTIC_SPLIT"
        candidates.append(
            {
                "source_excerpt": block,
                "recognition_source": recognition,
                "company": company,
                "role": role,
                "location": location,
                "warnings": warnings,
            }
        )
    return candidates


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


def parse_candidates(
    db: Session,
    profile_id: UUID,
    source_text: str,
    *,
    source_kind: str = "PASTE",
) -> list[models.CandidateJob]:
    """生成候选草稿并落库；同批同段幂等（不重复生产）。"""
    _profile(db, profile_id)
    kind = source_kind if source_kind in SOURCE_KINDS else "PASTE"
    normalized_source_hash = text_hash(normalize_for_match(source_text))
    built = build_candidates(source_text)
    if not built:
        raise HTTPException(status_code=422, detail="没有识别到岗位描述，请确认粘贴内容。")

    created: list[models.CandidateJob] = []
    for draft in built:
        excerpt_hash = text_hash(normalize_for_match(draft["source_excerpt"]))
        existing = db.scalar(
            select(models.CandidateJob).where(
                models.CandidateJob.profile_id == profile_id,
                models.CandidateJob.source_hash == normalized_source_hash,
                models.CandidateJob.source_excerpt_hash == excerpt_hash,
            )
        )
        if existing is not None:
            created.append(existing)
            continue
        row = models.CandidateJob(
            profile_id=profile_id,
            source_text=source_text,
            source_hash=normalized_source_hash,
            source_kind=kind,
            recognition_source=draft["recognition_source"],
            source_excerpt=draft["source_excerpt"],
            source_excerpt_hash=excerpt_hash,
            company=draft["company"] or None,
            role=draft["role"] or None,
            location=draft["location"] or None,
            raw_payload={
                "warnings": draft["warnings"],
                "title": " · ".join(v for v in (draft["company"], draft["role"]) if v).strip(" ·"),
            },
            status="DRAFT",
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    return created


def list_candidates(
    db: Session,
    profile_id: UUID,
    *,
    statuses: list[str] | None = None,
) -> list[models.CandidateJob]:
    _profile(db, profile_id)
    stmt = select(models.CandidateJob).where(models.CandidateJob.profile_id == profile_id)
    if statuses:
        stmt = stmt.where(models.CandidateJob.status.in_(statuses))
    return list(db.scalars(stmt.order_by(models.CandidateJob.created_at, models.CandidateJob.id)).all())


def get_candidate(db: Session, candidate_id: UUID) -> models.CandidateJob:
    row = db.get(models.CandidateJob, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="候选岗位不存在")
    return row


def update_candidate(
    db: Session,
    candidate_id: UUID,
    *,
    company: str | None = None,
    role: str | None = None,
    location: str | None = None,
) -> models.CandidateJob:
    """用户在确认阶段编辑身份字段；不改变原文摘录与溯源。"""
    row = get_candidate(db, candidate_id)
    if row.status in {"IMPORTED", "REJECTED"}:
        raise HTTPException(status_code=409, detail="已导入或已拒绝的候选不能再修改")
    if company is not None:
        row.company = company.strip() or None
    if role is not None:
        row.role = role.strip() or None
    if location is not None:
        row.location = location.strip() or None
    payload = dict(row.raw_payload or {})
    payload["title"] = " · ".join(v for v in (row.company, row.role) if v).strip(" ·")
    payload["edited"] = True
    row.raw_payload = payload
    row.recognition_source = "MANUAL"
    db.commit()
    db.refresh(row)
    return row


def confirm_candidate(db: Session, candidate_id: UUID) -> models.CandidateJob:
    row = get_candidate(db, candidate_id)
    if row.status == "REJECTED":
        raise HTTPException(status_code=409, detail="已拒绝的候选不能确认")
    if row.status == "IMPORTED":
        return row
    row.status = "CONFIRMED"
    db.commit()
    db.refresh(row)
    return row


def reject_candidate(db: Session, candidate_id: UUID) -> models.CandidateJob:
    row = get_candidate(db, candidate_id)
    if row.status == "IMPORTED":
        raise HTTPException(status_code=409, detail="已导入的候选不能拒绝；如需移除请归档对应岗位")
    row.status = "REJECTED"
    db.commit()
    db.refresh(row)
    return row


def _raw_text_for(row: models.CandidateJob) -> str:
    parts = [
        f"公司：{row.company or 'UNKNOWN'}",
        f"岗位：{row.role or 'UNKNOWN'}",
    ]
    if row.location:
        parts.append(f"地点：{row.location}")
    parts.append("")
    parts.append("岗位描述：")
    parts.append((row.source_excerpt or "").strip() or "（岗位描述见原文）")
    return "\n".join(parts)


def import_candidate(db: Session, candidate_id: UUID, profile_id: UUID | None = None) -> dict:
    """把候选导入为正式 JobMission；幂等。

    - 已导入：直接返回既有 mission；
    - 文本命中既有 TargetJob：复用其 mission，不重复建岗；
    - 否则走标准 create_mission。
    """
    from .mission_service import create_mission

    row = get_candidate(db, candidate_id)
    if row.status == "IMPORTED" and row.imported_mission_id:
        mission = db.get(models.JobMission, row.imported_mission_id)
        if mission is not None:
            return {
                "candidate_id": str(row.id),
                "mission_id": str(mission.id),
                "company": mission.company or row.company or "",
                "role": mission.role or row.role or "",
                "status": row.status,
                "reused": True,
            }
    if row.status == "REJECTED":
        raise HTTPException(status_code=409, detail="已拒绝的候选不能导入")

    target_profile_id = profile_id or row.profile_id
    raw_text = _raw_text_for(row)
    if len(raw_text.strip()) < 20:
        raise HTTPException(status_code=422, detail="岗位描述过短，无法导入")

    # 幂等：同 profile 下同一份文本已建过岗，则复用
    digest = content_hash(raw_text)
    existing_target_job = db.scalar(
        select(models.TargetJob).where(
            models.TargetJob.profile_id == target_profile_id,
            models.TargetJob.content_hash == digest,
        )
    )
    if existing_target_job is not None:
        mission = db.scalar(
            select(models.JobMission).where(
                models.JobMission.profile_id == target_profile_id,
                models.JobMission.target_job_id == existing_target_job.id,
            )
        )
        if mission is not None:
            row.status = "IMPORTED"
            row.imported_mission_id = mission.id
            db.commit()
            db.refresh(row)
            return {
                "candidate_id": str(row.id),
                "mission_id": str(mission.id),
                "company": mission.company or row.company or "",
                "role": mission.role or row.role or "",
                "status": row.status,
                "reused": True,
            }

    payload_out: dict | None = None
    # 原始链接要一路带进正式岗位：否则导入后「打开 BOSS 岗位」没有地址可用。
    source_url = (row.source_url or "").strip() or None
    try:
        payload_out = create_mission(  # type: ignore[assignment]
            db, target_profile_id, MissionCreate(raw_text=raw_text, source_url=source_url)
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # 并发/竞态下已被创建：回查复用（幂等）
        payload_out = None

    if payload_out is not None:
        mission_dict = payload_out
        mission_id = mission_dict["id"]
        company = str(mission_dict.get("company") or row.company or "")
        role = str(mission_dict.get("role") or row.role or "")
        reused = False
    else:
        target_job = db.scalar(
            select(models.TargetJob).where(
                models.TargetJob.profile_id == target_profile_id,
                models.TargetJob.content_hash == digest,
            )
        )
        if target_job is not None and source_url and not target_job.source_url:
            target_job.source_url = source_url
        mission_row = db.scalar(
            select(models.JobMission).where(
                models.JobMission.profile_id == target_profile_id,
                models.JobMission.target_job_id == target_job.id,
            )
        ) if target_job else None
        if mission_row is None:
            raise HTTPException(status_code=409, detail="岗位已存在但未找到对应任务，请刷新后重试")
        mission_id = mission_row.id
        company = mission_row.company or row.company or ""
        role = mission_row.role or row.role or ""
        reused = True

    row.status = "IMPORTED"
    row.imported_mission_id = mission_id
    db.commit()
    db.refresh(row)
    return {
        "candidate_id": str(row.id),
        "mission_id": str(mission_id),
        "company": company,
        "role": role,
        "status": row.status,
        "reused": reused,
    }


def candidate_read(row: models.CandidateJob) -> dict:
    payload = row.raw_payload or {}
    return {
        "id": str(row.id),
        "profile_id": str(row.profile_id),
        "source_kind": row.source_kind,
        "recognition_source": row.recognition_source,
        "source_excerpt": row.source_excerpt,
        "company": row.company,
        "role": row.role,
        "location": row.location,
        "status": row.status,
        "imported_mission_id": str(row.imported_mission_id) if row.imported_mission_id else None,
        "warnings": list(payload.get("warnings") or []),
        "title": payload.get("title") or " · ".join(v for v in (row.company, row.role) if v).strip(" · "),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


__all__ = [
    "normalize_for_match",
    "text_hash",
    "excerpt_in_source",
    "split_source_blocks",
    "build_candidates",
    "parse_candidates",
    "list_candidates",
    "get_candidate",
    "update_candidate",
    "confirm_candidate",
    "reject_candidate",
    "import_candidate",
    "candidate_read",
    "SOURCE_KINDS",
    "RECOGNITION_SOURCES",
    "STATUSES",
]
