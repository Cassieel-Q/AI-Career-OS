"""事实更新的影响面分析（可信求职 v1.2 · 指令 5.1 / 5.2）。

一项目事实（例如把「仅完成原型」改成「实际完成上线」并经过核对）可能同时被
多份岗位简历引用。系统必须能回答：

    「这项事实关联了 3 份岗位简历，其中 2 份可能需要更新。」

并且**绝不自动**重生成或覆盖任何岗位：只给出影响面与差异，由用户选择更新哪一份。

设计原则：
- 只读分析（``analyze_impact``）与写入（``sync_mission``）严格分开；
- 引用判定基于 Studio 文档节点的 ``source_id`` / ``evidence_refs``，不靠文本模糊匹配；
- 同步后节点回到 ``NEEDS_CONFIRMATION``：源事实变了，旧的人工核对不再适用于新文本
  （事实来源 ≠ 用户核对，见 Sprint A）。
"""
from __future__ import annotations

import re
from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import models

#: 经历字段 → Studio 文档里对应的节点字段
_FIELD_MAP: dict[str, dict[str, str]] = {
    "experience": {"title": "title", "organization": "subtitle", "dates": "date"},
    "education": {"institution": "title", "dates": "date"},
    "skill": {"name": "title", "proficiency": "subtitle"},
    "certification": {"name": "title", "issuer": "subtitle", "date": "date"},
}

_SOURCE_LABEL = {
    "experience": "经历",
    "education": "教育",
    "skill": "技能",
    "certification": "证书",
}


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


#: 事实键 ``experience:<uuid>:description:0`` 的前缀 → 记录类型
_ALIASES = {
    "experience": "experience",
    "education": "education",
    "skill": "skill",
    "certification": "certification",
    "experiences": "experience",
    "skills": "skill",
    "certifications": "certification",
}


def normalize_source_kind(value: str) -> str:
    """接受 ``experience`` 或 ``experience:<uuid>:...`` 两种写法，返回记录类型。"""
    key = str(value or "").strip().lower()
    if ":" in key:
        key = key.split(":", 1)[0]
    return _ALIASES.get(key, key)


def parse_fact_key(fact_key: str) -> tuple[str, str]:
    """从事实键里解析 (记录类型, 记录 ID)。"""
    parts = str(fact_key or "").split(":")
    if len(parts) < 2:
        raise _http(422, "事实键格式不正确，无法解析来源。")
    return normalize_source_kind(parts[0]), parts[1]


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def _source_record(db: Session, profile: models.UserProfile, source_kind: str, source_id: UUID):
    table = {
        "experience": "experiences",
        "education": "education",
        "skill": "profile_skills",
        "certification": "certifications",
    }.get(source_kind)
    if table is None:
        raise _http(422, f"不支持的事实来源类型：{source_kind}")
    for collection, kind in (
        (profile.experiences, "experience"),
        (profile.education, "education"),
        (profile.skills, "skill"),
        (profile.certifications, "certification"),
    ):
        if kind != source_kind:
            continue
        for item in collection:
            if item.id == source_id:
                return item
    raise _http(404, "事实来源不属于当前档案。")


def source_texts(source_kind: str, record) -> dict[str, str]:
    """源事实当前的可核对文本（字段 → 文本）。"""
    mapping = _FIELD_MAP.get(source_kind) or {}
    texts: dict[str, str] = {}
    for attribute in mapping:
        value = getattr(record, attribute, None)
        if value:
            texts[attribute] = str(value)
    if source_kind == "experience":
        for index, line in enumerate(str(record.description or "").splitlines()):
            cleaned = line.strip().removeprefix("• ").removeprefix("- ")
            if cleaned:
                texts[f"description:{index}"] = cleaned
    return texts


def _missions_for_profile(db: Session, profile_id: UUID) -> list[models.JobMission]:
    return list(db.scalars(select(models.JobMission).where(models.JobMission.profile_id == profile_id)).all())


def _studio_for(db: Session, mission_id: UUID) -> models.ResumeStudioDocument | None:
    return db.scalar(select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission_id))


def _delivered(db: Session, mission_id: UUID) -> bool:
    return db.scalar(select(models.JobApplication.id).where(
        models.JobApplication.mission_id == mission_id,
        models.JobApplication.resume_version_id.is_not(None),
    ).limit(1)) is not None


def _walk_nodes(document: dict):
    """遍历 Studio 文档中所有文字节点，产出 (节点, 位置描述)。"""
    for key, node in (document.get("basics") or {}).items():
        if isinstance(node, dict):
            yield node, f"基本信息/{key}"
    for section in document.get("sections") or []:
        label = str((section.get("title") or {}).get("text") or section.get("kind") or "")
        yield section["title"], f"{label}/标题"
        for entry in section.get("entries") or []:
            entry_label = str((entry.get("title") or {}).get("text") or "经历")
            for field in ("title", "subtitle", "date", "location"):
                if isinstance(entry.get(field), dict):
                    yield entry[field], f"{label}/{entry_label}/{field}"
            for bullet in entry.get("bullets") or []:
                yield bullet, f"{label}/{entry_label}/要点"


def _referenced(node: dict, source_kind: str, source_id: str) -> bool:
    if str(node.get("source_id") or "") == source_id:
        return True
    if source_id in {str(ref) for ref in node.get("evidence_refs") or []}:
        return True
    return False


def analyze_impact(db: Session, profile_id: UUID, source_kind: str, source_id: UUID) -> dict:
    """分析一项事实被哪些岗位简历引用、其中哪些可能需要更新。"""
    profile = db.get(models.UserProfile, profile_id)
    if profile is None:
        raise _http(404, "档案不存在")
    kind = normalize_source_kind(source_kind)
    record = _source_record(db, profile, kind, source_id)
    texts = source_texts(kind, record)
    field_map = _FIELD_MAP.get(kind) or {}
    source_id_str = str(source_id)

    missions_report: list[dict] = []
    for mission in _missions_for_profile(db, profile_id):
        studio = _studio_for(db, mission.id)
        if studio is None:
            continue
        document = studio.document_json or {}
        hits: list[dict] = []
        for node, location in _walk_nodes(document):
            if not _referenced(node, source_kind, source_id_str):
                continue
            kind = "field"
            expected: str | None = None
            attribute = next((attr for attr, node_field in field_map.items() if location.endswith(f"/{node_field}")), None)
            if attribute:
                expected = texts.get(attribute)
            if attribute is None and node.get("source_kind") == "target_bullet":
                kind = "bullet"
            current = str(node.get("text") or "")
            changed = bool(expected) and _normalize(current) != _normalize(expected)
            hits.append({
                "node_id": node.get("id"),
                "location": location,
                "kind": kind,
                "current_text": current,
                "source_text": expected,
                "changed": changed,
                "claim_status": node.get("claim_status"),
            })
        if not hits:
            continue
        field_changed = any(hit["changed"] for hit in hits)
        has_bullet = any(hit["kind"] == "bullet" for hit in hits)
        # 字段对不上 → 明确需要更新；只有改写要点 → 需要人工复核（改写依据变了）
        impact = "CHANGED" if field_changed else ("REVIEW" if has_bullet else "NONE")
        missions_report.append({
            "mission_id": str(mission.id),
            "display_name": mission.display_name,
            "company": mission.company,
            "role": mission.role,
            "studio_revision": studio.revision,
            "confirmed_revision": studio.confirmed_revision,
            "already_delivered": _delivered(db, mission.id),
            "impact": impact,
            "matches": hits,
        })

    total = len(missions_report)
    needs_update = sum(1 for item in missions_report if item["impact"] != "NONE")
    return {
        "source_kind": kind,
        "source_id": str(source_id),
        "source_label": f"{_SOURCE_LABEL.get(kind, kind)}：{(texts.get('title') or texts.get('name') or texts.get('institution') or '')[:60]}",
        "summary": f"这项事实关联了 {total} 份岗位简历，其中 {needs_update} 份可能需要更新。",
        "total_missions": total,
        "needs_update_count": needs_update,
        "missions": missions_report,
        # 明确承诺：系统不会自动改任何一份
        "auto_update": False,
    }


def sync_mission(
    db: Session,
    profile_id: UUID,
    source_kind: str,
    source_id: UUID,
    mission_id: UUID,
    expected_revision: int | None = None,
) -> dict:
    """把一项已核对事实同步到**指定**岗位的简历（用户显式选择，绝不批量）。

    只更新字段类节点（标题/副标题/日期）到源事实当前文本；改写要点不动——
    那是 AI 依据旧事实生成的文案，必须由用户或重新生成决定，系统不代劳。
    更新后节点回到 ``NEEDS_CONFIRMATION``：源事实变了，旧核对不再适用。
    """
    profile = db.get(models.UserProfile, profile_id)
    if profile is None:
        raise _http(404, "档案不存在")
    kind = normalize_source_kind(source_kind)
    record = _source_record(db, profile, kind, source_id)
    texts = source_texts(kind, record)
    field_map = _FIELD_MAP.get(kind) or {}
    studio = _studio_for(db, mission_id)
    if studio is None:
        raise _http(404, "这个岗位还没有工作台简历。")
    if expected_revision is not None and studio.revision != expected_revision:
        raise _http(409, "简历已在另一处更新，请重新查看差异后再同步。")

    document = studio.document_json or {}
    updated: list[dict] = []
    skipped: list[dict] = []
    for node, location in _walk_nodes(document):
        if not _referenced(node, kind, str(source_id)):
            continue
        attribute = next((attr for attr, node_field in field_map.items() if location.endswith(f"/{node_field}")), None)
        if attribute is None:
            skipped.append({"node_id": node.get("id"), "location": location, "reason": "AI 改写要点需要你确认或重新生成，系统不会自动改写。"})
            continue
        expected = texts.get(attribute)
        if not expected:
            continue
        if _normalize(node.get("text")) == _normalize(expected):
            continue
        before = str(node.get("text") or "")
        node["text"] = expected
        node["claim_status"] = "NEEDS_CONFIRMATION"
        updated.append({"node_id": node.get("id"), "location": location, "before": before, "after": expected})

    if not updated:
        return {"mission_id": str(mission_id), "updated": [], "skipped": skipped, "revision": studio.revision, "changed": False}

    # 必须重新赋一个新对象：SQLAlchemy 的 JSON 列不跟踪原地修改，
    # 直接把同一个 dict 赋回去会被判定为「未变更」，导致内容丢失（只改了修订号）。
    studio.document_json = deepcopy(document)
    studio.revision = int(studio.revision or 1) + 1
    flag_modified(studio, "document_json")
    # 内容变了，已确认的正式投递版不再对应当前修订
    studio.confirmed_revision = None
    db.commit()
    db.refresh(studio)
    return {
        "mission_id": str(mission_id),
        "updated": updated,
        "skipped": skipped,
        "revision": studio.revision,
        "changed": True,
        "message": f"已同步 {len(updated)} 处；请重新确认后再导出正式投递版。",
    }
