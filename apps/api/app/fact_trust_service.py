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
from .fact_trust_schemas import (
    CONTROLLED_FIELDS,
    FactAttestCreate,
    FactAttestRead,
    FactFieldChange,
    FactItem,
    FactListRead,
)

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


def _signature_text(fact_key: str, record) -> str:
    """内部签名文本：**含起止时间**（P1-B），与页面展示文本分离。

    展示文本（``_iter_facts`` 的 text）继续承担 UI 呈现，签名只用于判定
    「旧的核对是否还对应当前事实」。用 ``\\x1f`` 分隔字段，避免不同字段的
    拼接产生歧义；纯空白差异不触发失效。
    """
    kind, _, _raw = fact_key.partition(":")
    if kind == "experience":
        values = [str(record.title or ""), str(record.organization or ""), str(record.dates or ""), str(record.description or "")]
    else:
        values = [str(record.name or ""), str(record.proficiency or "")]
    return "\x1f".join(value.strip() for value in values)


def _fact_record(profile: models.UserProfile, fact_key: str):
    """按 fact_key 找回源记录（experience 或 skill 行）。"""
    kind, _, raw_id = fact_key.partition(":")
    collections = {"experience": profile.experiences or [], "skill": profile.skills or []}
    for item in collections.get(kind, []):
        if str(item.id) == raw_id:
            return item
    return None


def _display_text(profile: models.UserProfile, fact_key: str) -> str:
    return next((text for key, _t, _i, _s, text in _iter_facts(profile) if key == fact_key), "")


def _field_values(profile: models.UserProfile, fact_key: str) -> dict[str, str]:
    """受控修正可改字段的当前值（P1-A）：前端据以展示旧值并组装修改框。"""
    record = _fact_record(profile, fact_key)
    if record is None:
        return {}
    return {field: str(getattr(record, field) or "") for field in CONTROLLED_FIELDS.get(fact_key.partition(":")[0], ())}


def _current_signatures(profile: models.UserProfile) -> dict[str, str]:
    """当前全部事实的内部签名（fact_key → signature_text）。"""
    signatures: dict[str, str] = {}
    for exp in profile.experiences or []:
        signatures[f"experience:{exp.id}"] = _signature_text(f"experience:{exp.id}", exp)
    for skill in profile.skills or []:
        signatures[f"skill:{skill.id}"] = _signature_text(f"skill:{skill.id}", skill)
    return signatures


def lock_legacy_signatures(db: Session, profile: models.UserProfile) -> int:
    """把旧格式核对记录（无 signature_text）的签名补写为**当前**值。

    必须在**改动源事实之前**调用（见 ``update_draft_profile`` / ``attest_fact``）：
    先锁定改动前的状态，之后的字段变化（含起止时间）才会让签名失配。
    这是保守迁移——不新增核对记录、不升级任何状态，只是把旧记录的覆盖范围
    固定下来。由调用方负责提交（本函数不 commit）。
    """
    signatures = _current_signatures(profile)
    now = datetime.now(timezone.utc)
    changed = 0
    for row in db.scalars(
        select(models.FactAttestation).where(models.FactAttestation.profile_id == profile.id)
    ).all():
        if row.signature_text is None and row.fact_key in signatures:
            row.signature_text = signatures[row.fact_key]
            row.updated_at = now
            changed += 1
    return changed


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
                field_values=_field_values(profile, fact_key),
            )
        )

    return FactListRead(
        profile_id=profile_id,
        facts=facts,
        attested_count=attested,
        rejected_count=rejected,
        pending_count=pending,
    )


def _apply_field_updates(
    db: Session,
    profile: models.UserProfile,
    fact_key: str,
    field_updates: dict[str, str],
) -> list[FactFieldChange]:
    """受控字段修正（FINAL FREEZE P1-A）：只写回白名单字段，返回新旧值对照。

    设计边界：

    - 已确认档案不允许整体 ``PUT``，但允许在这里修正单项事实——「修正」与
      「写回」是同一次用户确认动作（``attest_fact`` 显式提交）。
    - 只开放 :data:`CONTROLLED_FIELDS` 列出的字段，杜绝把整份档案换成新内容。
    - 修正的是源记录本身；岗位简历版本由用户在影响面里逐份选择更新，
      历史投递快照不受影响（快照存的是独立 JSON，见 ``delivery_version_service``）。
    """
    kind, _, _raw = fact_key.partition(":")
    allowed = CONTROLLED_FIELDS.get(kind, ())
    if not allowed:
        raise _http(422, "这类事实不支持字段修正")
    unknown = sorted(set(field_updates) - set(allowed))
    if unknown:
        raise _http(422, f"不支持修正这些字段：{'、'.join(unknown)}；只支持 {'、'.join(allowed)}")

    record = _fact_record(profile, fact_key)
    if record is None:
        raise _http(404, "未找到这条事实")

    limits = {"title": 255, "organization": 255, "dates": 255, "name": 255, "description": 4_000}
    changes: list[FactFieldChange] = []
    for field, value in field_updates.items():
        text = str(value or "").strip()
        limit = limits.get(field, 255)
        if len(text) > limit:
            raise _http(422, f"字段 {field} 超过长度限制（{limit} 字）")
        old_value = str(getattr(record, field) or "").strip()
        if text == old_value:
            continue  # 没有实际变化，不写也不记
        changes.append(FactFieldChange(field=field, old_value=old_value, new_value=text))
        setattr(record, field, text if text or field == "description" else None)
        if hasattr(record, "source_type"):
            record.source_type = "USER_ENTERED"
        if hasattr(record, "updated_at"):
            record.updated_at = datetime.now(timezone.utc)
    if changes:
        db.add(record)
    return changes


def attest_fact(db: Session, profile_id: UUID, payload: FactAttestCreate) -> FactAttestRead:
    """记录一次用户核对动作；可附带受控字段修正。

    - ``USER_ATTESTED``：写入 verified_at / verified_by，之后该事实可用于生成成稿回答。
    - ``REJECTED``：该事实不得进入参考答案与岗位简历。
    - ``UNREVIEWED``：撤回之前的核对（事实内容变更后需要重新确认）。
    - ``field_updates``（P1-A）：受控修正经历标题 / 组织 / 起止时间 / 描述，
      必须与 ``apply_to_source=True`` 一起提交。修正后本次核对即为新事实的
      核对记录（新 verified_at / 新签名）；不带 field_updates 的普通编辑
      走原有 fact_text 路径，同样在写回后重算签名。
    """
    profile = _profile(db, profile_id)
    status = _normalize_status(payload.status)
    if status is None:
        raise _http(422, "核对状态只支持 USER_ATTESTED / REJECTED / UNREVIEWED")

    known_keys = {key for key, *_ in _iter_facts(profile)}
    if payload.fact_key not in known_keys:
        raise _http(404, "未找到这条事实")

    field_updates = {k: v for k, v in (payload.field_updates or {}).items() if str(v or "").strip()} or None
    if field_updates and not payload.apply_to_source:
        raise _http(422, "字段修正必须写回原始事实（apply_to_source=true）")

    row = db.scalar(
        select(models.FactAttestation).where(
            models.FactAttestation.profile_id == profile_id,
            models.FactAttestation.fact_key == payload.fact_key,
        )
    )
    if row is None:
        row = models.FactAttestation(profile_id=profile_id, fact_key=payload.fact_key)
        db.add(row)

    # 改动源事实之前先锁定旧格式记录的签名（P1-B 保守迁移）。
    lock_legacy_signatures(db, profile)

    now = datetime.now(timezone.utc)
    field_changes: list[FactFieldChange] = []
    if field_updates:
        field_changes = _apply_field_updates(db, profile, payload.fact_key, payload.field_updates or {})

    # 写回后按最新源记录重算展示文本与签名——无论走哪条路径，
    # 存下来的核对记录都必须对应当前事实。
    applied = bool(field_changes)
    if payload.apply_to_source and payload.fact_text and not field_updates:
        applied = _apply_to_source(db, profile, payload.fact_key, payload.fact_text) or applied

    source_text = _display_text(profile, payload.fact_key)
    record = _fact_record(profile, payload.fact_key)
    row.fact_text = ((payload.fact_text if not field_updates else None) or source_text or "")[:4_000]
    if record is not None:
        row.signature_text = _signature_text(payload.fact_key, record)
    row.status = status
    row.note = payload.note
    if status == VerificationStatus.USER_ATTESTED.value:
        row.verified_at = now
        row.verified_by = "user"
        row.source_kind = FactSource.USER_PROVIDED.value if (payload.fact_text or field_updates) else row.source_kind
    else:
        row.verified_at = None
        row.verified_by = None
    row.updated_at = now

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
        applied_fields=[change.field for change in field_changes],
        field_changes=field_changes,
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
    """事实被改动后，撤销不再对应的「用户已核实」记录。

    为什么需要它
    ------------
    「档案已确认（CONFIRMED）」只表示档案已就绪、可以继续走流程，**不等于事实被永久锁定**。
    用户随时可能发现自己填错了一段经历的时间或职责，必须能改回去。

    但只要事实变了，之前那一次核对就不再针对当前事实——继续让它保持
    ``USER_ATTESTED``，等于**用旧签名给新文本背书**，这正是本轮要消灭的事实可信漏洞。

    判定规则（P1-B）：

    - 有 ``signature_text`` 的记录：与当前内部签名（含起止时间）严格比对，
      标题 / 组织 / 时间 / 描述任何一个字段变化都会失配。
    - 旧格式记录（``signature_text`` 为 NULL）：按展示文本比对（旧签名从未
      覆盖时间，只覆盖它记过的文本）；比对一致时把当前签名补写进去，
      把旧记录的覆盖范围固定下来（保守迁移，不升级任何状态）。

    这里只做最小动作——把不再对应的记录退回 ``UNREVIEWED`` 并清空签名时间与
    签名人，不删除历史、不影响其它事实。由调用方负责在同一事务里提交。
    """
    signatures = _current_signatures(profile)
    displays = {key: text for key, _title, _sid, _stype, text in _iter_facts(profile)}
    now = datetime.now(timezone.utc)
    changed = 0
    for row in db.scalars(
        select(models.FactAttestation).where(models.FactAttestation.profile_id == profile.id)
    ).all():
        if not is_attested(row.status):
            continue
        signature = signatures.get(row.fact_key)
        if signature is None:
            # 事实本身没了（经历被删等）——核对自然失效。
            row.status = VerificationStatus.UNREVIEWED.value
            row.verified_at = None
            row.verified_by = None
            row.note = "事实原文已变更，需要重新核对。"
            row.updated_at = now
            changed += 1
            continue
        if row.signature_text is not None:
            valid = row.signature_text.strip() == signature.strip()
        else:
            valid = (row.fact_text or "").strip() == (displays.get(row.fact_key) or "").strip()
            if valid:
                # 旧格式记录：补写当前签名，把覆盖范围固定下来。
                row.signature_text = signature
        if not valid:
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
