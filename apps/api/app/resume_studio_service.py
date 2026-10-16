"""Mission-scoped structured final resume, imported from approved rewrite choices."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .mission_service import _effective_profile_for_mission
from .resume_layout import normalize_layout_config
from .resume_studio_schemas import StudioOperation


def _node(
    text: str | None,
    *,
    source_kind: str,
    source_id: UUID | None = None,
    evidence_refs: list[str] | None = None,
    risk_level: str = "LOW",
    claim_status: str = "CONFIRMED",
    node_id: UUID | None = None,
) -> dict:
    return {
        "id": str(node_id or uuid4()),
        "text": (text or "").strip(),
        "source_kind": source_kind,
        "source_id": str(source_id) if source_id else None,
        "evidence_refs": list(evidence_refs or []),
        "risk_level": risk_level,
        "claim_status": claim_status,
    }


def _entry(source_id: UUID, *, title: dict, subtitle: dict, date: dict, location: dict, bullets: list[dict]) -> dict:
    return {
        "id": str(source_id),
        "status": "INCLUDED",
        "title": title,
        "subtitle": subtitle,
        "date": date,
        "location": location,
        "bullets": bullets,
    }


def _section(kind: str, title: str, entries: list[dict]) -> dict:
    return {"id": str(uuid4()), "kind": kind, "title": _node(title, source_kind="system"), "entries": entries}


def _import_document(profile: models.UserProfile, resume: models.TargetResume, mission: models.JobMission) -> dict:
    basics = {
        "name": _node(profile.full_name, source_kind="profile", source_id=profile.id, risk_level="HIGH"),
        "phone": _node(profile.phone, source_kind="profile", source_id=profile.id, risk_level="HIGH"),
        "email": _node(profile.email, source_kind="profile", source_id=profile.id, risk_level="HIGH"),
        "location": _node(profile.city, source_kind="profile", source_id=profile.id),
    }
    def _education_sort_key(item: models.Education) -> int:
        degree = (item.degree or "")
        if any(keyword in degree for keyword in ("博士", "PhD", "Doctor")):
            return 0
        if any(keyword in degree for keyword in ("硕士", "研究生", "Master", "MBA")):
            return 1
        if any(keyword in degree for keyword in ("本科", "学士", "Bachelor")):
            return 2
        return 3

    education = [
        _entry(
            item.id,
            title=_node(item.institution, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            subtitle=_node(" · ".join(filter(None, [item.degree, item.field_of_study])), source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            date=_node(item.dates, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            location=_node("", source_kind="profile", source_id=item.id),
            bullets=[_node(line, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)]) for line in [*(f"奖项：{honor}" for honor in item.honors or []), *item.relevant_courses]],
        )
        for item in sorted(profile.education, key=_education_sort_key)
    ]
    accepted = [bullet for bullet in resume.bullets if bullet.status in {"ACCEPTED", "EDITED"}]
    by_experience: dict[UUID, list[models.TargetResumeBullet]] = defaultdict(list)
    for bullet in accepted:
        if bullet.source_experience_id:
            by_experience[bullet.source_experience_id].append(bullet)
    order = {str(value): idx for idx, value in enumerate(resume.recommended_experience_order or [])}
    experiences = []
    omitted = {item.experience_id for item in mission.selections if item.decision == "OMIT"}
    for item in sorted(profile.experiences, key=lambda exp: (order.get(str(exp.id), 9999), str(exp.id))):
        if item.id in omitted or item.id not in by_experience:
            continue
        bullets = []
        for bullet in sorted(by_experience[item.id], key=lambda row: (row.sort_order, str(row.id))):
            flags = {str(flag).upper() for flag in bullet.risk_flags or []}
            needs_confirmation = bool(flags & {"GROUNDING:NEEDS_CONFIRMATION", "GROUNDING:UNSUPPORTED", "SYNTHETIC_PROJECT"})
            lines = [line.strip().removeprefix("• ").removeprefix("- ") for line in (bullet.final_text or bullet.suggested_text).splitlines() if line.strip()]
            for index, line in enumerate(lines):
                bullets.append(_node(
                    line,
                    source_kind="target_bullet",
                    source_id=bullet.id,
                    node_id=bullet.id if index == 0 else None,
                    evidence_refs=[str(ref) for ref in bullet.evidence_refs or []],
                    risk_level="HIGH" if needs_confirmation else "LOW",
                    claim_status="NEEDS_CONFIRMATION" if needs_confirmation and "FACT_CONFIRMED" not in flags else "CONFIRMED",
                ))
        experiences.append(_entry(
            item.id,
            title=_node(item.title, source_kind="experience", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            subtitle=_node(item.organization, source_kind="experience", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            date=_node(item.dates, source_kind="experience", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            location=_node("", source_kind="experience", source_id=item.id),
            bullets=bullets,
        ))
    generation = (resume.strategy or {}).get("_generation") or {}
    project_titles = generation.get("bullet_project_titles") or []
    for bullet in sorted(accepted, key=lambda row: (row.sort_order, str(row.id))):
        if bullet.source_experience_id is not None:
            continue
        flags = {str(flag).upper() for flag in bullet.risk_flags or []}
        if "SYNTHETIC_PROJECT" not in flags or "FACT_CONFIRMED" not in flags:
            continue
        raw_title = project_titles[bullet.sort_order] if 0 <= bullet.sort_order < len(project_titles) else None
        raw_title = str(raw_title or bullet.original_text or "")
        title = re.sub(r"^项目草案\s*[:：—-]?\s*", "", raw_title).strip()
        if not title or title.startswith("建议补做"):
            title = "作品集项目"
        points = [line.strip().removeprefix("• ").removeprefix("- ") for line in (bullet.final_text or bullet.suggested_text).splitlines() if line.strip()]
        experiences.append(_entry(
            uuid4(),
            title=_node(title, source_kind="target_bullet", source_id=bullet.id, evidence_refs=[str(ref) for ref in bullet.evidence_refs or []], risk_level="HIGH"),
            subtitle=_node("", source_kind="system"),
            date=_node("", source_kind="system"),
            location=_node("", source_kind="system"),
            bullets=[_node(point, source_kind="target_bullet", source_id=bullet.id, node_id=bullet.id if index == 0 else None, evidence_refs=[str(ref) for ref in bullet.evidence_refs or []]) for index, point in enumerate(points)],
        ))
    skills = [
        _entry(
            item.id,
            title=_node(item.name, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)]),
            subtitle=_node(item.proficiency, source_kind="profile", source_id=item.id),
            date=_node("", source_kind="system"),
            location=_node("", source_kind="system"),
            bullets=[],
        )
        for item in profile.skills
    ]
    certifications = [
        _entry(
            item.id,
            title=_node(item.name, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)]),
            subtitle=_node(item.issuer, source_kind="profile", source_id=item.id),
            date=_node(item.date, source_kind="profile", source_id=item.id, risk_level="HIGH"),
            location=_node("", source_kind="system"),
            bullets=[],
        )
        for item in profile.certifications
    ]
    return {"schema_version": 1, "basics": basics, "sections": [
        _section("education", "教育经历", education),
        _section("experience", "工作与项目经历", experiences),
        _section("skills", "技能", skills),
        _section("certifications", "证书", certifications),
    ]}


def get_or_create_document(db: Session, mission_id: UUID) -> models.ResumeStudioDocument:
    existing = db.scalar(select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission_id))
    if existing:
        return existing
    mission = db.get(models.JobMission, mission_id)
    if mission is None:
        raise HTTPException(404, "岗位任务不存在。")
    resume = db.scalar(select(models.TargetResume).where(models.TargetResume.mission_id == mission_id, models.TargetResume.status == "CONFIRMED").order_by(models.TargetResume.version.desc()))
    if resume is None:
        raise HTTPException(409, "请先确认岗位定向简历。")
    profile = _effective_profile_for_mission(db, mission)
    row = models.ResumeStudioDocument(
        mission_id=mission.id,
        source_target_resume_id=resume.id,
        revision=1,
        language="zh",
        template_id="zh-classic",
        document_json=_import_document(profile, resume, mission),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission_id))
        if concurrent is None:
            raise
        return concurrent
    db.refresh(row)
    return row


def _latest_confirmed_source(db: Session, mission_id: UUID) -> models.TargetResume | None:
    return db.scalar(select(models.TargetResume).where(
        models.TargetResume.mission_id == mission_id,
        models.TargetResume.status == "CONFIRMED",
    ).order_by(models.TargetResume.version.desc()))


def _section_bullet_texts(section: dict) -> list[str]:
    """单个板块里实际会渲染出来的要点文本（跳过被 OMIT 的条目与要点）。"""
    return [
        bullet["text"]
        for entry in section.get("entries") or []
        if entry.get("status") != "OMITTED"
        for bullet in entry.get("bullets") or []
        if bullet.get("claim_status") != "OMITTED" and bullet.get("text")
    ]


def _included_bullet_texts(document: dict) -> list[str]:
    return [
        text
        for section in document.get("sections") or []
        for text in _section_bullet_texts(section)
    ]


def _manual_edit_texts(document: dict) -> list[str]:
    """用户在 Studio 里手工新增/修改过的内容（source_kind == user_entered）。

    重新导入会整体替换文档，这些内容会丢——必须在确认弹窗里如实列出来。
    """
    texts: list[str] = []
    for node in (document.get("basics") or {}).values():
        if isinstance(node, dict) and node.get("source_kind") == "user_entered" and node.get("text"):
            texts.append(node["text"])
    for section in document.get("sections") or []:
        for entry in section.get("entries") or []:
            for field in ("title", "subtitle", "date"):
                node = entry.get(field) or {}
                if node.get("source_kind") == "user_entered" and node.get("text"):
                    texts.append(node["text"])
            for bullet in entry.get("bullets") or []:
                if bullet.get("source_kind") == "user_entered" and bullet.get("text"):
                    texts.append(bullet["text"])
    return texts


def _section_breakdown(old_doc: dict, new_doc: dict) -> list[dict]:
    """按板块对比新旧两版：新增 / 删除 / 修改 / 保持不变，让用户看清每个板块会发生什么。"""
    # 同名板块可能出现多次，用「标题 + 出现序号」配对，避免 dict 覆盖漏掉后半部分。
    def _index(document: dict) -> dict[tuple[str, int], dict]:
        bucket: dict[str, int] = {}
        indexed: dict[tuple[str, int], dict] = {}
        for section in document.get("sections") or []:
            title = (section.get("title") or {}).get("text", "") if isinstance(section.get("title"), dict) else str(section.get("title") or "")
            seq = bucket.get(title, 0)
            bucket[title] = seq + 1
            indexed[(title, seq)] = section
        return indexed

    old_by_title = _index(old_doc)
    new_by_title = _index(new_doc)
    breakdown: list[dict] = []
    for key in list(new_by_title) + [item for item in old_by_title if item not in new_by_title]:
        title = key[0]
        old_section = old_by_title.get(key)
        new_section = new_by_title.get(key)
        if old_section is None and new_section is not None:
            breakdown.append({"section": title, "status": "added", "added": _section_bullet_texts(new_section), "removed": [], "kept": 0})
            continue
        if new_section is None and old_section is not None:
            breakdown.append({"section": title, "status": "removed", "added": [], "removed": _section_bullet_texts(old_section), "kept": 0})
            continue
        old_texts = _section_bullet_texts(old_section or {})
        new_texts = _section_bullet_texts(new_section or {})
        added = [text for text in new_texts if text not in old_texts]
        removed = [text for text in old_texts if text not in new_texts]
        kept = len([text for text in new_texts if text in old_texts])
        breakdown.append(
            {
                "section": title,
                "status": "changed" if added or removed else "unchanged",
                "added": added,
                "removed": removed,
                "kept": kept,
            }
        )
    return breakdown


def source_diff(db: Session, mission_id: UUID) -> dict:
    """Read a newer approved source without changing a user's Studio edits."""
    row = get_or_create_document(db, mission_id)
    latest = _latest_confirmed_source(db, mission_id)
    if latest is None or latest.id == row.source_target_resume_id:
        return {"update_available": False, "current_source_id": str(row.source_target_resume_id)}
    mission = db.get(models.JobMission, mission_id)
    profile = _effective_profile_for_mission(db, mission)
    proposed = _import_document(profile, latest, mission)
    old_texts = _included_bullet_texts(row.document_json)
    new_texts = _included_bullet_texts(proposed)
    manual_edits = _manual_edit_texts(row.document_json)
    return {
        "update_available": True,
        "current_source_id": str(row.source_target_resume_id),
        "new_source_id": str(latest.id),
        "new_source_version": latest.version,
        "added_bullets": [text for text in new_texts if text not in old_texts],
        "removed_bullets": [text for text in old_texts if text not in new_texts],
        "sections": _section_breakdown(row.document_json, proposed),
        # 人工新增/修改过的内容：重新导入会被整体替换，必须提前告知数量与内容。
        "manual_edit_count": len(manual_edits),
        "manual_edit_samples": manual_edits[:8],
        "will_replace_studio_edits": True,
        "will_reset_language": row.language != "zh",
    }


def reimport_source(db: Session, mission_id: UUID, expected_revision: int) -> dict:
    row = get_or_create_document(db, mission_id)
    if row.revision != expected_revision:
        raise HTTPException(409, {"message": "简历已更新，请重新检查来源差异。", "latest": read_document(row)})
    latest = _latest_confirmed_source(db, mission_id)
    if latest is None or latest.id == row.source_target_resume_id:
        raise HTTPException(409, "没有更新的已确认改写稿。")
    mission = db.get(models.JobMission, mission_id)
    profile = _effective_profile_for_mission(db, mission)
    proposed = _import_document(profile, latest, mission)
    result = db.execute(update(models.ResumeStudioDocument).where(
        models.ResumeStudioDocument.id == row.id,
        models.ResumeStudioDocument.revision == expected_revision,
    ).values(
        source_target_resume_id=latest.id,
        document_json=proposed,
        revision=expected_revision + 1,
        confirmed_revision=None,
        language="zh",
        template_id="zh-classic",
        updated_at=datetime.now(timezone.utc),
    ))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "简历已在另一处更新，请重新读取。")
    db.commit()
    db.refresh(row)
    return read_document(row)


def read_document(row: models.ResumeStudioDocument) -> dict:
    return {
        "id": str(row.id),
        "mission_id": str(row.mission_id),
        "source_target_resume_id": str(row.source_target_resume_id),
        "schema_version": row.schema_version,
        "revision": row.revision,
        "confirmed_revision": row.confirmed_revision,
        "language": row.language,
        "template_id": row.template_id,
        "layout_config": normalize_layout_config(getattr(row, "layout_config", None)),
        "document": row.document_json,
    }


def _find_node(document: dict, node_id: str) -> dict | None:
    for node in (document.get("basics") or {}).values():
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    for section in document.get("sections") or []:
        if section.get("id") == node_id:
            return section
        if section.get("title", {}).get("id") == node_id:
            return section["title"]
        for entry in section.get("entries") or []:
            if entry.get("id") == node_id:
                return entry
            for field in ("title", "subtitle", "date", "location"):
                if entry.get(field, {}).get("id") == node_id:
                    return entry[field]
            for bullet in entry.get("bullets") or []:
                if bullet.get("id") == node_id:
                    return bullet
    return None


def _list_containing(document: dict, node_id: str) -> list[dict] | None:
    for section in document.get("sections") or []:
        if any(entry.get("id") == node_id for entry in section.get("entries") or []):
            return section["entries"]
        for entry in section.get("entries") or []:
            if any(bullet.get("id") == node_id for bullet in entry.get("bullets") or []):
                return entry["bullets"]
    return None


_METRIC = re.compile(r"\d|[%％]|(?:主导|负责|led|increased|reduced|grew)", re.IGNORECASE)

# 与 ResumeForge 对齐：正文残留这类未完成标记时应拦截导出（宁可少拦、不可误拦，只认确定性的占位符）。
_PLACEHOLDER_RESIDUE = re.compile(r"【[^】]*(?:待补|待确认|待补充|待核实|待完善)[^】]*】|待补充|待核实|待完善|待补全")


def _placeholder_residue(text: str | None) -> str | None:
    match = _PLACEHOLDER_RESIDUE.search(text or "")
    return match.group(0) if match else None


def _risk_for_text(text: str, previous: str = "LOW") -> str:
    return "HIGH" if previous == "HIGH" or _METRIC.search(text) else "LOW"


def export_checks(document: dict) -> list[dict]:
    """导出前自检。

    「事实核对」已下线：未核对的内容不再拦截导出，只以 ``warn`` 返回提示
    （信息不丢，供调用方自行决定是否展示）。仍然 ``block`` 的只剩两类
    内容质量问题：正文残留占位标记、以及一条要点都没有的空简历。
    """
    checks: list[dict] = []
    rendered_bullets = 0

    def inspect(node: dict, location: str = "") -> None:
        if node.get("claim_status") == "OMITTED":
            return
        status = node.get("claim_status")
        if status in {"NEEDS_CONFIRMATION", "BLOCKED_MISSING"}:
            checks.append({
                "level": "warn",
                "code": "unconfirmed_fact",
                "node_id": node["id"],
                "message": "这项内容尚未核对事实；不影响导出，建议投递前自行确认。",
            })
        residue = _placeholder_residue(node.get("text"))
        if residue:
            where = f"（{location}）" if location else ""
            checks.append({"level": "block", "code": "placeholder_residue", "node_id": node["id"], "message": f"正文还残留未完成标记「{residue}」，请先补全或删除再导出。{where}".strip()})

    for node in (document.get("basics") or {}).values():
        if isinstance(node, dict):
            inspect(node, "基本信息")
    for section in document.get("sections") or []:
        section_label = str((section.get("title") or {}).get("text") or section.get("kind") or "")
        inspect(section["title"], section_label)
        for entry in section.get("entries") or []:
            if entry.get("status") == "OMITTED":
                continue
            entry_label = str((entry.get("title") or {}).get("text") or "经历")
            for field in ("title", "subtitle", "date", "location"):
                inspect(entry[field], f"{section_label} / {entry_label}")
            for bullet in entry.get("bullets") or []:
                inspect(bullet, f"{section_label} / {entry_label}")
                if bullet.get("claim_status") != "OMITTED" and bullet.get("text"):
                    rendered_bullets += 1
    if rendered_bullets == 0:
        checks.append({"level": "block", "code": "empty_resume", "message": "请先加入至少一条经历要点。"})
    return checks


def apply_operation(db: Session, mission_id: UUID, expected_revision: int, raw_operation: StudioOperation | dict) -> dict:
    operation = raw_operation if isinstance(raw_operation, StudioOperation) else StudioOperation.model_validate(raw_operation)
    row = get_or_create_document(db, mission_id)
    if row.revision != expected_revision:
        raise HTTPException(409, {"message": "简历已在另一处更新，请核对最新版本后重试。", "latest": read_document(row)})
    document = deepcopy(row.document_json)
    kind = operation.type

    if kind == "set_text":
        if operation.node_id is None or operation.text is None:
            raise HTTPException(422, "缺少文字节点或内容。")
        node = _find_node(document, str(operation.node_id))
        if node is None or "text" not in node:
            raise HTTPException(404, "文字节点不存在。")
        text = operation.text.strip()
        if not text and node.get("risk_level") == "HIGH":
            node["claim_status"] = "BLOCKED_MISSING"
        elif text != node["text"] and node.get("source_kind") != "system":
            node["claim_status"] = "NEEDS_CONFIRMATION"
        node["risk_level"] = _risk_for_text(text, node.get("risk_level", "LOW"))
        node["text"] = text
    elif kind == "add_entry":
        if operation.section_id is None or not (operation.title or "").strip():
            raise HTTPException(422, "请提供板块与经历名称。")
        section = _find_node(document, str(operation.section_id))
        if section is None or "entries" not in section:
            raise HTTPException(404, "板块不存在。")
        title = operation.title.strip()
        section["entries"].append(_entry(
            uuid4(),
            title=_node(title, source_kind="user_entered", risk_level="HIGH", claim_status="NEEDS_CONFIRMATION"),
            subtitle=_node("", source_kind="user_entered", claim_status="NEEDS_CONFIRMATION"),
            date=_node("", source_kind="user_entered", risk_level="HIGH", claim_status="BLOCKED_MISSING"),
            location=_node("", source_kind="user_entered"),
            bullets=[],
        ))
    elif kind == "add_bullet":
        if operation.entry_id is None or not (operation.text or "").strip():
            raise HTTPException(422, "请提供经历与要点内容。")
        entry = _find_node(document, str(operation.entry_id))
        if entry is None or "bullets" not in entry:
            raise HTTPException(404, "经历不存在。")
        text = operation.text.strip()
        entry["bullets"].append(_node(text, source_kind="user_entered", risk_level=_risk_for_text(text), claim_status="NEEDS_CONFIRMATION"))
    elif kind in {"omit", "restore"}:
        if operation.node_id is None:
            raise HTTPException(422, "缺少目标节点。")
        node = _find_node(document, str(operation.node_id))
        if node is None:
            raise HTTPException(404, "目标节点不存在。")
        if "claim_status" not in node and "status" not in node:
            raise HTTPException(422, "只支持省略文字、经历或要点。")
        key = "claim_status" if "claim_status" in node else "status"
        if kind == "omit" and node.get(key) != "OMITTED":
            node["previous_status"] = node[key]
            node[key] = "OMITTED"
        elif kind == "restore" and node.get(key) == "OMITTED":
            node[key] = node.pop("previous_status", "NEEDS_CONFIRMATION" if key == "claim_status" else "INCLUDED")
    elif kind == "move":
        if operation.node_id is None:
            raise HTTPException(422, "缺少移动节点。")
        group = _list_containing(document, str(operation.node_id))
        if group is None:
            raise HTTPException(404, "只支持同一板块中的经历或要点排序。")
        item = next(value for value in group if value["id"] == str(operation.node_id))
        if operation.before_id is not None and not any(value["id"] == str(operation.before_id) for value in group):
            raise HTTPException(422, "排序目标必须位于同一板块。")
        if operation.before_id == operation.node_id:
            raise HTTPException(422, "不能将条目移动到自身之前。")
        group.remove(item)
        if operation.before_id is None:
            group.append(item)
        else:
            index = next(index for index, value in enumerate(group) if value["id"] == str(operation.before_id))
            group.insert(index, item)
    elif kind == "confirm_fact":
        if operation.node_id is None:
            raise HTTPException(422, "缺少事实节点。")
        node = _find_node(document, str(operation.node_id))
        if node is None or "claim_status" not in node:
            raise HTTPException(404, "事实节点不存在。")
        if node.get("claim_status") == "OMITTED":
            raise HTTPException(422, "已省略内容无需确认。")
        if not node.get("text"):
            raise HTTPException(422, "请先填写事实内容。")
        node["claim_status"] = "CONFIRMED"
        node["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    elif kind == "set_evidence":
        if operation.node_id is None or operation.evidence_refs is None:
            raise HTTPException(422, "缺少来源节点或引用。")
        node = _find_node(document, str(operation.node_id))
        if node is None or "evidence_refs" not in node:
            raise HTTPException(404, "来源节点不存在。")
        mission = db.get(models.JobMission, mission_id)
        profile = _effective_profile_for_mission(db, mission)
        valid_ids = {str(item.id) for collection in (profile.education, profile.experiences, profile.skills, profile.certifications) for item in collection}
        refs = [str(ref) for ref in operation.evidence_refs]
        if any(ref not in valid_ids for ref in refs):
            raise HTTPException(422, "来源引用不属于当前简历。")
        node["evidence_refs"] = refs
        node["claim_status"] = "NEEDS_CONFIRMATION"
    elif kind == "set_language":
        if operation.language is None:
            raise HTTPException(422, "缺少语言。")
        row.language = operation.language
        row.template_id = f"{operation.language}-classic"
    elif kind == "set_template":
        if not operation.template_id:
            raise HTTPException(422, "缺少模板。")
        from .resume_studio_templates import get_template
        template = get_template(operation.template_id)
        if template["language"] != row.language:
            raise HTTPException(422, "请先完成当前简历语言的内容。")
        row.template_id = operation.template_id
    elif kind == "set_layout":
        if not operation.layout_config:
            raise HTTPException(422, "缺少版式配置。")
        row.layout_config = normalize_layout_config({**(row.layout_config or {}), **operation.layout_config})

    result = db.execute(
        update(models.ResumeStudioDocument)
        .where(models.ResumeStudioDocument.id == row.id, models.ResumeStudioDocument.revision == expected_revision)
        .values(
            document_json=document,
            revision=expected_revision + 1,
            confirmed_revision=None,
            language=row.language,
            template_id=row.template_id,
            layout_config=row.layout_config,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        db.expire_all()
        fresh = db.get(models.ResumeStudioDocument, row.id)
        raise HTTPException(409, {"message": "简历已在另一处更新，请核对最新版本后重试。", "latest": read_document(fresh)})
    db.commit()
    db.refresh(row)
    return read_document(row)
