"""事实核对服务：列出待核对事实、记录用户核对动作、提供已核实事实语料。

核心原则（指令 1.1 / 1.4）：

- 「系统提取到」「用户采纳改写」「用户核实事实」三件事互不推导。
- 只有写入 :class:`app.models.FactAttestation` 且 status 为 ``USER_ATTESTED`` 的
  事实才算已核实；档案状态 ``CONFIRMED`` 不算。
- 历史数据不做批量升级：没有核对记录的事实一律 ``UNREVIEWED``。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .fact_trust import FactSource, VerificationStatus, coverage_score, is_attested
from .fact_trust_schemas import FactAttestCreate, FactAttestRead, FactItem, FactListRead

#: 一段「讲得清楚」的经历通常要覆盖的四个维度。
_ASPECT_PATTERNS: dict[str, tuple[str, ...]] = {
    "个人动作": ("负责", "完成", "搭建", "设计", "推动", "撰写", "整理", "分析", "协调", "组织", "开发", "跟进"),
    "问题或困难": ("问题", "困难", "挑战", "瓶颈", "冲突", "不足", "痛点", "卡点"),
    "方案取舍": ("取舍", "权衡", "对比", "比较", "方案", "选择", "决策", "优先级", "迭代"),
    # 只用明确的结果信号；「完成」「原型」「文档」属于动作或产物，不能证明有可核对的结果。
    "可核对结果": ("结果", "产出", "交付", "上线", "落地", "数据", "提升", "增长", "反馈", "留存", "转化", "%", "％"),
}


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _normalize_status(value: str) -> str | None:
    key = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if key in {"USER_ATTESTED", "ATTESTED"}:
        return VerificationStatus.USER_ATTESTED.value
    if key in {"REJECTED", "REJECT"}:
        return VerificationStatus.REJECTED.value
    if key in {"UNREVIEWED", "PENDING", "RESET"}:
        return VerificationStatus.UNREVIEWED.value
    return None


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    profile = db.get(models.UserProfile, profile_id)
    if profile is None:
        raise _http(404, "档案不存在")
    return profile


def analyze_aspects(text: str) -> tuple[list[str], list[str]]:
    """判断一段经历覆盖了哪些维度、还缺哪些维度。"""
    body = str(text or "")
    present: list[str] = []
    missing: list[str] = []
    for aspect, keywords in _ASPECT_PATTERNS.items():
        if any(keyword in body for keyword in keywords):
            present.append(aspect)
        else:
            missing.append(aspect)
    return present, missing


def _risk_level(missing: list[str], text: str) -> str:
    if len(missing) >= 3 or not str(text or "").strip():
        return "HIGH"
    if missing:
        return "MEDIUM"
    return "LOW"


def _candidate_suggestion(db: Session, profile_id: UUID, original: str) -> str | None:
    """找出与这条经历最贴近的 AI 改写稿（若有）。

    改写稿属于「AI 建议」维度，采纳它不等于核实事实，因此只作展示用途。
    """
    if not str(original or "").strip():
        return None
    rows = db.scalars(
        select(models.ResumeClaim)
        .where(models.ResumeClaim.profile_id == profile_id)
        .order_by(models.ResumeClaim.updated_at.desc())
        .limit(50)
    ).all()
    best: tuple[float, str] | None = None
    for row in rows:
        suggestion = (row.suggested_text or "").strip()
        if not suggestion:
            continue
        score = coverage_score(suggestion, original)
        if best is None or score > best[0]:
            best = (score, suggestion)
    if best is None or best[0] < 0.5:
        return None
    return best[1]


def _iter_facts(profile: models.UserProfile) -> list[tuple[str, str, str | None, str | None, str]]:
    """返回 (fact_key, title, source_id, source_type, text)。"""
    items: list[tuple[str, str, str | None, str | None, str]] = []
    for exp in profile.experiences or []:
        parts = [str(exp.title or ""), str(exp.organization or ""), str(exp.description or "")]
        items.append(
            (
                f"experience:{exp.id}",
                str(exp.title or "未命名经历"),
                str(exp.id),
                getattr(exp, "source_type", None),
                " / ".join(part for part in parts if part.strip()),
            )
        )
    for skill in profile.skills or []:
        items.append(
            (
                f"skill:{skill.id}",
                str(skill.name or "未命名技能"),
                str(skill.id),
                getattr(skill, "source_type", None),
                " / ".join(part for part in (str(skill.name or ""), str(skill.proficiency or "")) if part.strip()),
            )
        )
    return items


def list_facts(db: Session, profile_id: UUID) -> FactListRead:
    profile = _profile(db, profile_id)
    attestations = {
        row.fact_key: row
        for row in db.scalars(
            select(models.FactAttestation).where(models.FactAttestation.profile_id == profile_id)
        ).all()
    }

    facts: list[FactItem] = []
    attested = 0
    rejected = 0
    pending = 0
    for fact_key, title, source_id, source_type, text in _iter_facts(profile):
        row = attestations.get(fact_key)
        status = VerificationStatus((row.status if row and row.status else VerificationStatus.UNREVIEWED.value))
        if status is VerificationStatus.USER_ATTESTED:
            attested += 1
        elif status is VerificationStatus.REJECTED:
            rejected += 1
        else:
            pending += 1
        present, missing = analyze_aspects(text)
        facts.append(
            FactItem(
                fact_key=fact_key,
                title=title,
                original_text=text,
                suggested_text=_candidate_suggestion(db, profile_id, text),
                source_kind=(row.source_kind if row and row.source_kind else FactSource.SOURCE_EXTRACTED.value),
                source_id=source_id,
                source_type=source_type,
                verification_status=status.value,
                verified_at=row.verified_at if row else None,
                present_aspects=present,
                missing_aspects=missing,
                risk=_risk_level(missing, text),
                note=row.note if row else None,
            )
        )

    return FactListRead(
        profile_id=profile_id,
        facts=facts,
        attested_count=attested,
        rejected_count=rejected,
        pending_count=pending,
    )


def attest_fact(db: Session, profile_id: UUID, payload: FactAttestCreate) -> FactAttestRead:
    """记录一次用户核对动作。

    - ``USER_ATTESTED``：写入 verified_at / verified_by，之后该事实可用于生成成稿回答。
    - ``REJECTED``：该事实不得进入参考答案与岗位简历。
    - ``UNREVIEWED``：撤回之前的核对（事实内容变更后需要重新确认）。
    """
    profile = _profile(db, profile_id)
    status = _normalize_status(payload.status)
    if status is None:
        raise _http(422, "核对状态只支持 USER_ATTESTED / REJECTED / UNREVIEWED")

    known_keys = {key for key, *_ in _iter_facts(profile)}
    if payload.fact_key not in known_keys:
        raise _http(404, "未找到这条事实")

    row = db.scalar(
        select(models.FactAttestation).where(
            models.FactAttestation.profile_id == profile_id,
            models.FactAttestation.fact_key == payload.fact_key,
        )
    )
    if row is None:
        row = models.FactAttestation(profile_id=profile_id, fact_key=payload.fact_key)
        db.add(row)

    source_text = next((text for key, _t, _i, _s, text in _iter_facts(profile) if key == payload.fact_key), "")
    now = datetime.now(timezone.utc)
    row.fact_text = (payload.fact_text or source_text or "")[:4_000]
    row.status = status
    row.note = payload.note
    if status == VerificationStatus.USER_ATTESTED.value:
        row.verified_at = now
        row.verified_by = "user"
        row.source_kind = FactSource.USER_PROVIDED.value if payload.fact_text else row.source_kind
    else:
        row.verified_at = None
        row.verified_by = None
    row.updated_at = now

    applied = False
    if payload.apply_to_source and payload.fact_text:
        applied = _apply_to_source(db, profile, payload.fact_key, payload.fact_text)

    try:
        db.commit()
    except Exception as exc:  # pragma: no cover - 提交失败走统一 503
        db.rollback()
        raise _http(503, "事实核对记录保存失败") from exc
    db.refresh(row)

    return FactAttestRead(
        fact_key=row.fact_key,
        status=row.status,
        verification_status=row.status,
        fact_text=row.fact_text,
        source_kind=row.source_kind,
        verified_at=row.verified_at,
        applied_to_source=applied,
        note=row.note,
    )


def _apply_to_source(db: Session, profile: models.UserProfile, fact_key: str, text: str) -> bool:
    """把用户编辑后的事实写回原始经历（只有显式要求时才做）。"""
    kind, _, raw_id = fact_key.partition(":")
    if kind == "experience":
        for exp in profile.experiences or []:
            if str(exp.id) == raw_id:
                exp.description = text
                exp.source_type = "USER_ENTERED"
                exp.updated_at = datetime.now(timezone.utc) if hasattr(exp, "updated_at") else None
                return True
    if kind == "skill":
        for skill in profile.skills or []:
            if str(skill.id) == raw_id:
                skill.name = text[:255]
                skill.source_type = "USER_ENTERED"
                return True
    return False


def invalidate_changed_attestations(db: Session, profile: models.UserProfile) -> int:
    """事实原文被改动后，撤销不再对应的「用户已核实」记录。

    为什么需要它
    ------------
    「档案已确认（CONFIRMED）」只表示档案已就绪、可以继续走流程，**不等于事实被永久锁定**。
    用户随时可能发现自己填错了一段经历的时间或职责，必须能改回去。

    但只要事实文本变了，之前那一次核对就不再针对当前文本——继续让它保持
    ``USER_ATTESTED``，等于**用旧签名给新文本背书**，这正是本轮要消灭的事实可信漏洞。

    因此：改事实可以，改完必须重新核对。这里只做最小动作——把不再对应的记录
    退回 ``UNREVIEWED`` 并清空签名时间与签名人，不删除历史、不影响其它事实。

    由调用方负责在同一事务里提交（本函数不 commit）。
    """
    current = {key: text for key, _title, _sid, _stype, text in _iter_facts(profile)}
    now = datetime.now(timezone.utc)
    changed = 0
    for row in db.scalars(
        select(models.FactAttestation).where(models.FactAttestation.profile_id == profile.id)
    ).all():
        if not is_attested(row.status):
            continue
        text = current.get(row.fact_key)
        if text is None or (row.fact_text or "").strip() != text.strip():
            row.status = VerificationStatus.UNREVIEWED.value
            row.verified_at = None
            row.verified_by = None
            row.note = "事实原文已变更，需要重新核对。"
            row.updated_at = now
            changed += 1
    return changed


def attested_fact_texts(db: Session, profile_id: UUID) -> list[str]:
    """返回用户已核实的事实文本，供参考答案 / 岗位简历的事实语料使用。"""
    rows = db.scalars(
        select(models.FactAttestation).where(
            models.FactAttestation.profile_id == profile_id,
            models.FactAttestation.status == VerificationStatus.USER_ATTESTED.value,
        )
    ).all()
    return [row.fact_text for row in rows if is_attested(row.status) and row.fact_text]


def attested_key_set(db: Session, profile_id: UUID) -> set[str]:
    rows = db.scalars(
        select(models.FactAttestation).where(
            models.FactAttestation.profile_id == profile_id,
            models.FactAttestation.status == VerificationStatus.USER_ATTESTED.value,
        )
    ).all()
    return {row.fact_key for row in rows if is_attested(row.status)}
