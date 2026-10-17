"""手动导入岗位（BOSS 直聘等）+ 浏览器扩展本地通信路由（M2）。

安全边界：
1. 写接口只接受「本地前端」或「已配对扩展」两种来源；
2. 扩展请求必须携带 ``X-AI-Career-Token``，且 Origin 必须是扩展或本地前端；
3. 请求体超过 ``MAX_BODY_BYTES`` 直接 413，避免超大 payload；
4. 解析只做规则抽取，不执行 JD 里的任何指令；检测到注入只标记告警；
5. 绝不读取 Cookie / 密码 / 验证码 —— 本模块不接受任何凭据字段。
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import extension_auth as ext_auth
from . import manual_import_service as manual
from . import models
from .database import get_db
from .job_ingest_service import content_hash, dedupe_key

router = APIRouter(prefix="/api/v1")

#: 请求体上限：1 MiB。JD 再长也不该超过这个量级，超了直接拒绝而不是慢慢解析。
MAX_BODY_BYTES = 1_048_576

_WS_RE = re.compile(r"\s+")

#: 明确禁止出现在导入内容里的凭据类字段（防误粘贴 / 防扩展越权读取）
_FORBIDDEN_FIELD_RE = re.compile(r"(password|passwd|pwd|secret|cookie|token|api[_-]?key|验证码|短信验证码)", re.I)


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_text: str = Field(min_length=1, max_length=manual.MAX_SOURCE_TEXT)
    source_url: str | None = None
    source_site: str = "UNKNOWN"
    recognition: str = "MANUAL_PASTE"
    provided: dict | None = Field(default=None, description="调用方已明确读到的字段，优先级最高")


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    draft: dict | None = None
    #: 直接给字段（前端编辑后提交）时优先用这组
    company: str | None = None
    role: str | None = None
    location: str | None = None
    salary_text: str | None = None
    education: str | None = None
    experience: str | None = None
    employment_type: str | None = None
    jd: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    #: 同岗位 JD 有变化时是否更新已有记录（默认 False：只报告差异）
    update_duplicates: bool = False
    #: 保存后是否立刻导入为正式岗位（进入匹配分析）
    import_to_mission: bool = False


class PairExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(min_length=4, max_length=16)


def _guard_body_size(request: Request) -> None:
    raw = request.headers.get("content-length")
    if raw and raw.isdigit() and int(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, f"请求体过大（>{MAX_BODY_BYTES // 1024} KiB）。")


def _require_extension(request: Request) -> None:
    """扩展写接口的鉴权：令牌 + 来源白名单。"""
    if not ext_auth.is_paired():
        raise HTTPException(409, "本机尚未配对浏览器扩展，请先在 AI Career OS 的设置页生成配对码。")
    token = request.headers.get("x-ai-career-token", "")
    if not ext_auth.verify(token):
        raise HTTPException(401, "扩展令牌无效或已轮换，请重新配对。")
    if not ext_auth.origin_allowed(request.headers.get("origin")):
        raise HTTPException(403, "不允许的来源。")


def _reject_credentials(text: str) -> None:
    """导入内容里若出现凭据类字段，直接拒绝（扩展也不该读到这些）。"""
    if _FORBIDDEN_FIELD_RE.search(text or ""):
        raise HTTPException(
            422,
            "导入内容疑似包含密码 / Cookie / 令牌 / 验证码等敏感信息，已拒绝保存。请删除后再导入。",
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text_hash(value: str) -> str:
    return hashlib.sha256(_WS_RE.sub("", (value or "").strip()).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- 解析


@router.post("/job-import/parse")
def parse_manual(payload: ParseRequest, request: Request) -> dict:
    """解析粘贴/页面文本（不入库），返回可在前端编辑的结构化草稿。"""
    _guard_body_size(request)
    text = payload.source_text or ""
    if len(text.strip()) < 10:
        raise HTTPException(422, "内容太短，无法识别岗位。请复制完整的岗位信息。")
    _reject_credentials(text)

    draft = manual.parse_job_text(
        source_text=text,
        source_url=payload.source_url or "",
        source_site=payload.source_site or "UNKNOWN",
        recognition=payload.recognition or "MANUAL_PASTE",
        provided=payload.provided,
    )
    draft["original_length"] = len(text)
    return {"status": "OK", "draft": draft}


# --------------------------------------------------------------------------- 保存


def _apply_user_edits(draft: dict, payload: SaveRequest) -> dict:
    """用户确认界面修改后的字段覆盖解析结果（用户永远优先）。"""
    for key in ("company", "role", "location", "salary_text", "education", "experience", "employment_type", "jd", "source_url"):
        value = getattr(payload, key, None)
        if value is not None and str(value).strip():
            draft[key] = str(value).strip()
    if payload.source_site:
        draft["source_site"] = payload.source_site
    if draft.get("employment_type") not in {"INTERN", "FULLTIME", "PARTTIME"}:
        draft["employment_type"] = "UNKNOWN"
    return draft


def _build_text(draft: dict) -> str:
    return "\n".join(
        part
        for part in [
            f"公司：{draft.get('company')}" if draft.get("company") else None,
            f"职位：{draft.get('role')}" if draft.get("role") else None,
            f"地点：{draft.get('location')}" if draft.get("location") else None,
            f"薪资：{draft.get('salary_text')}" if draft.get("salary_text") else None,
            f"学历：{draft.get('education')}" if draft.get("education") else None,
            f"经验：{draft.get('experience')}" if draft.get("experience") else None,
            f"类型：{draft.get('employment_type')}" if draft.get("employment_type") not in (None, "", "UNKNOWN") else None,
            "",
            draft.get("jd") or "",
        ]
        if part is not None
    ).strip()


def _refresh_fingerprints(draft: dict) -> dict:
    text = _build_text(draft)
    draft["text"] = text
    draft["dedupe_key"] = dedupe_key(draft.get("company"), draft.get("role"), draft.get("location"))
    draft["content_hash"] = content_hash(draft.get("role"), draft.get("location"), text)
    draft["needs_confirm"] = [f for f in ("company", "role", "location", "jd") if not (draft.get(f) or "").strip()]
    return draft


def _diff_fields(row: models.CandidateJob, draft: dict) -> list[str]:
    payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    pairs = [
        ("company", row.company, draft.get("company")),
        ("role", row.role, draft.get("role")),
        ("location", row.location, draft.get("location")),
        ("salary_text", payload.get("salary_text"), draft.get("salary_text")),
        ("education", payload.get("education"), draft.get("education")),
        ("experience", payload.get("experience"), draft.get("experience")),
        ("employment_type", payload.get("employment_type"), draft.get("employment_type")),
        ("jd", payload.get("jd_hash"), _text_hash(draft.get("jd") or "")),
    ]
    changed = []
    for name, old, new in pairs:
        if (old or "") != (new or ""):
            changed.append(name)
    return changed


def _save_draft(db: Session, profile_id: UUID, draft: dict, update_duplicates: bool) -> dict:
    profile = db.get(models.UserProfile, profile_id)
    if profile is None:
        raise HTTPException(404, "档案不存在")

    draft = _refresh_fingerprints(dict(draft))
    _reject_credentials(draft.get("jd") or "")
    if not (draft.get("role") or "").strip() and not (draft.get("company") or "").strip():
        raise HTTPException(422, "至少要有岗位名或公司名才能保存，请在上方补齐。")

    key = draft["dedupe_key"]
    existing = db.scalar(
        select(models.CandidateJob).where(
            models.CandidateJob.profile_id == profile_id,
            models.CandidateJob.dedupe_key == key,
        )
    )
    if existing is None:
        existing = db.scalar(
            select(models.CandidateJob).where(
                models.CandidateJob.profile_id == profile_id,
                models.CandidateJob.company == (draft.get("company") or None),
                models.CandidateJob.role == (draft.get("role") or None),
                models.CandidateJob.location == (draft.get("location") or None),
            )
        )
    if existing is not None:
        payload = existing.raw_payload if isinstance(existing.raw_payload, dict) else {}
        changed = _diff_fields(existing, draft)
        if not changed and payload.get("content_hash") == draft["content_hash"]:
            return {
                "status": "DUPLICATE",
                "candidate_id": str(existing.id),
                "company": existing.company,
                "role": existing.role,
                "changed_fields": [],
                "message": "岗位库里已经有一条完全相同的岗位，未重复新增。",
            }
        result = {
            "status": "UPDATED" if update_duplicates else "DUPLICATE",
            "candidate_id": str(existing.id),
            "company": existing.company,
            "role": existing.role,
            "changed_fields": changed,
        }
        if not update_duplicates:
            result["message"] = "岗位已存在，但这次的内容有变化：" + "、".join(changed) + "。勾选「更新已有岗位」后才会覆盖。"
            return result

        # 更新只写内容类字段；用户手动改过 / 已投递 / 已导入的记录不动身份字段与状态
        user_edited = bool(payload.get("edited"))
        if not user_edited:
            existing.company = (draft.get("company") or "").strip() or existing.company
            existing.role = (draft.get("role") or "").strip() or existing.role
            existing.location = (draft.get("location") or "").strip() or existing.location
        existing.source_text = draft.get("text") or existing.source_text
        existing.source_excerpt = (draft.get("jd") or "")[:2000] or existing.source_excerpt
        existing.source_url = (draft.get("source_url") or "")[:1024] or existing.source_url
        existing.collected_at = _now()
        existing.parse_status = "PARSED" if not draft.get("needs_confirm") else "NEEDS_CONFIRM"
        payload.update(
            {
                "salary_text": draft.get("salary_text") or payload.get("salary_text", ""),
                "education": draft.get("education") or payload.get("education", ""),
                "experience": draft.get("experience") or payload.get("experience", ""),
                "employment_type": draft.get("employment_type") or payload.get("employment_type", "UNKNOWN"),
                "source_site": draft.get("source_site") or payload.get("source_site", "UNKNOWN"),
                "source_url": draft.get("source_url") or payload.get("source_url", ""),
                "recognition": draft.get("recognition") or payload.get("recognition", "MANUAL_PASTE"),
                "confidence": draft.get("confidence") or payload.get("confidence", {}),
                "warnings": draft.get("warnings") or payload.get("warnings", []),
                "needs_confirm": draft.get("needs_confirm") or [],
                "content_hash": draft["content_hash"],
                "jd_hash": _text_hash(draft.get("jd") or ""),
                "updated_at": _now().isoformat(),
            }
        )
        existing.raw_payload = payload
        db.commit()
        db.refresh(existing)
        result["message"] = "已更新岗位内容（保留你的备注与投递状态）。"
        result["user_edited_preserved"] = user_edited
        return result

    text = draft.get("text") or ""
    row = models.CandidateJob(
        profile_id=profile_id,
        source_text=text,
        source_hash=_text_hash(text),
        source_kind="PASTE" if (draft.get("recognition") or "") == "MANUAL_PASTE" else "LINK",
        recognition_source="MANUAL",
        source_excerpt=(draft.get("jd") or "")[:2000],
        source_excerpt_hash=_text_hash(draft.get("jd") or ""),
        company=(draft.get("company") or "").strip() or None,
        role=(draft.get("role") or "").strip() or None,
        location=(draft.get("location") or "").strip() or None,
        source_url=(draft.get("source_url") or "")[:1024] or None,
        collected_at=_now(),
        parse_status="PARSED" if not draft.get("needs_confirm") else "NEEDS_CONFIRM",
        dedupe_key=key,
        raw_payload={
            "source": "manual_import",
            "source_site": draft.get("source_site") or "UNKNOWN",
            "recognition": draft.get("recognition") or "MANUAL_PASTE",
            "salary_text": draft.get("salary_text") or "",
            "education": draft.get("education") or "",
            "experience": draft.get("experience") or "",
            "employment_type": draft.get("employment_type") or "UNKNOWN",
            "confidence": draft.get("confidence") or {},
            "warnings": draft.get("warnings") or [],
            "needs_confirm": draft.get("needs_confirm") or [],
            "content_hash": draft["content_hash"],
            "jd_hash": _text_hash(draft.get("jd") or ""),
            "title": " · ".join(v for v in (draft.get("company"), draft.get("role")) if v).strip(" ·"),
        },
        status="CONFIRMED",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "status": "NEW",
        "candidate_id": str(row.id),
        "company": row.company,
        "role": row.role,
        "changed_fields": [],
        "message": "已保存到岗位库。",
    }


@router.post("/profiles/{profile_id}/job-import/save")
def save_manual(profile_id: UUID, payload: SaveRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """保存手动导入的岗位（去重 + 差异提示 + 可选导入正式岗位）。"""
    _guard_body_size(request)
    draft = dict(payload.draft or {})
    if not draft:
        draft = {
            "company": payload.company or "",
            "role": payload.role or "",
            "location": payload.location or "",
            "salary_text": payload.salary_text or "",
            "education": payload.education or "",
            "experience": payload.experience or "",
            "employment_type": payload.employment_type or "UNKNOWN",
            "jd": payload.jd or "",
            "source_url": payload.source_url or "",
            "source_site": payload.source_site or "UNKNOWN",
            "recognition": "MANUAL_PASTE",
        }
    draft = _apply_user_edits(draft, payload)
    if not (draft.get("jd") or "").strip():
        raise HTTPException(422, "岗位描述为空，无法保存。")

    result = _save_draft(db, profile_id, draft, payload.update_duplicates)

    if payload.import_to_mission and result.get("candidate_id"):
        from . import candidate_job_service as candidate_svc

        try:
            imported = candidate_svc.import_candidate(db, UUID(result["candidate_id"]), profile_id)
            result["mission_id"] = imported.get("mission_id")
            result["mission_reused"] = imported.get("reused", False)
        except HTTPException as exc:
            result["mission_error"] = exc.detail
    return result


# --------------------------------------------------------------------------- 扩展通信


@router.get("/extension/status")
def extension_status() -> dict:
    """本地前端查询配对状态（不含令牌）。"""
    token = ext_auth.current_token()
    return {
        "paired": token is not None,
        "token_fingerprint": ext_auth.fingerprint(token) if token else None,
        "pending_codes": ext_auth.pending_codes(),
    }


@router.post("/extension/pair/code")
def extension_pair_code() -> dict:
    """本地前端生成 5 分钟有效的 6 位配对码。"""
    return ext_auth.issue_pair_code()


@router.post("/extension/pair/exchange")
def extension_pair_exchange(payload: PairExchangeRequest, request: Request) -> dict:
    """扩展用配对码换取令牌。失败次数过多返回 429。"""
    _guard_body_size(request)
    token = ext_auth.exchange_code(payload.code)
    if not token:
        raise HTTPException(401, "配对码无效或已过期，请在 AI Career OS 重新生成。")
    return {"token": token, "token_fingerprint": ext_auth.fingerprint(token)}


@router.get("/extension/ping")
def extension_ping(request: Request) -> dict:
    _require_extension(request)
    return {"status": "ok", "service": "ai-career-os"}


@router.post("/extension/job-import/parse")
def extension_parse(payload: ParseRequest, request: Request) -> dict:
    _require_extension(request)
    _guard_body_size(request)
    text = payload.source_text or ""
    if len(text.strip()) < 10:
        raise HTTPException(422, "页面内容太短，无法识别岗位。")
    _reject_credentials(text)
    # 来源如实记录：扩展会按页面域名给出 BOSS_ZHIPIN / OTHER / UNKNOWN。
    # 这里绝不把缺省值补成 BOSS_ZHIPIN——那会让非 BOSS 页面被标成 BOSS 采集（伪造来源）。
    raw_site = (payload.source_site or "").strip()
    draft = manual.parse_job_text(
        source_text=text,
        source_url=payload.source_url or "",
        source_site=raw_site or "UNKNOWN",
        recognition="BROWSER_EXTENSION",
        provided=payload.provided,
    )
    return {"status": "OK", "draft": draft}


class ExtensionSaveRequest(SaveRequest):
    profile_id: str | None = None


@router.post("/extension/job-import/save")
def extension_save(payload: ExtensionSaveRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    _require_extension(request)
    _guard_body_size(request)
    raw_profile = (payload.profile_id or "").strip()
    if not raw_profile:
        # 本地单用户：没有显式档案时取第一个
        first = db.scalars(select(models.UserProfile).order_by(models.UserProfile.created_at)).first()
        if first is None:
            raise HTTPException(404, "本机还没有任何档案，请先打开 AI Career OS 创建。")
        profile_id = first.id
    else:
        from uuid import UUID as _UUID

        try:
            profile_id = _UUID(raw_profile)
        except ValueError as exc:
            raise HTTPException(422, "profile_id 不是合法的 UUID。") from exc

    draft = dict(payload.draft or {})
    if not draft:
        draft = {
            "company": payload.company or "",
            "role": payload.role or "",
            "location": payload.location or "",
            "salary_text": payload.salary_text or "",
            "education": payload.education or "",
            "experience": payload.experience or "",
            "employment_type": payload.employment_type or "UNKNOWN",
            "jd": payload.jd or "",
            "source_url": payload.source_url or "",
            # 同上：来源如实记录，缺省记为 UNKNOWN，不冒充 BOSS 采集
            "source_site": (payload.source_site or "").strip() or "UNKNOWN",
            "recognition": "BROWSER_EXTENSION",
        }
    draft = _apply_user_edits(draft, payload)
    if not (draft.get("jd") or "").strip():
        raise HTTPException(422, "岗位描述为空，未保存。")

    result = _save_draft(db, profile_id, draft, payload.update_duplicates)

    # 与手动导入保持一致：扩展保存也支持「直接进工作台」（import_to_mission）。
    # 少这一段的话，浏览器里读到的岗位只会停在候选草稿，工作台永远不显示。
    if payload.import_to_mission and result.get("candidate_id"):
        from . import candidate_job_service as candidate_svc

        try:
            imported = candidate_svc.import_candidate(db, UUID(result["candidate_id"]), profile_id)
            result["mission_id"] = imported.get("mission_id")
            result["mission_reused"] = imported.get("reused", False)
        except HTTPException as exc:
            result["mission_error"] = exc.detail
    return result


__all__ = ["router"]
