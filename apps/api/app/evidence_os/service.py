from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from . import gates, models, schemas
from .enums import MatchStatus, RequirementPriority, VerificationStatus, VersionStatus

from .helpers import competencies_for, priority_for, split_requirements


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_list(vals: list[UUID] | None) -> list[str]:
    return [str(v) for v in (vals or [])]


def create_source(db: Session, profile_id: UUID, body: schemas.SourceCreate) -> models.EosSource:
    row = models.EosSource(
        profile_id=profile_id,
        source_type=body.source_type,
        locator=body.locator,
        notes=body.notes or "",
        captured_at=body.captured_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_evidence(db: Session, profile_id: UUID, body: schemas.EvidenceCreate) -> models.EosEvidence:
    gates.assert_no_metric_estimate(body.fact_text, field="fact_text")
    metric: dict[str, Any] | None = None
    if body.metric is not None:
        metric = body.metric.model_dump() if hasattr(body.metric, "model_dump") else dict(body.metric)
        gates.assert_metric_confirmed(metric)
        gates.assert_no_metric_estimate(str(metric.get("value", "")), field="metric.value")
    row = models.EosEvidence(
        profile_id=profile_id,
        fact_text=body.fact_text.strip(),
        evidence_type=body.evidence_type,
        org_or_project=body.org_or_project,
        identity_lock=body.identity_lock,
        metric=metric,
        source_ids=_uuid_list(body.source_ids),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_claim(db: Session, profile_id: UUID, body: schemas.ClaimCreate) -> models.EosClaim:
    gates.assert_no_metric_estimate(body.candidate_wording, field="candidate_wording")
    gates.assert_no_metric_estimate(body.source_fact, field="source_fact")
    payload = body.model_dump()
    gates.assert_claim_confirmable(payload)
    row = models.EosClaim(
        profile_id=profile_id,
        source_fact=body.source_fact.strip(),
        candidate_wording=body.candidate_wording.strip(),
        verification_status=body.verification_status,
        responsibility_level=body.responsibility_level,
        boundary=body.boundary or "",
        interview_details=body.interview_details or "",
        risk_notes=body.risk_notes or [],
        evidence_ids=_uuid_list(body.evidence_ids),
        competency_ids=list(body.competency_ids or []),
        last_verified_at=_utcnow() if body.verification_status == VerificationStatus.CONFIRMED else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_claim(db: Session, claim: models.EosClaim, body: schemas.ClaimUpdate) -> models.EosClaim:
    data = body.model_dump(exclude_unset=True)
    if "candidate_wording" in data and data["candidate_wording"] is not None:
        gates.assert_no_metric_estimate(data["candidate_wording"], field="candidate_wording")
        claim.candidate_wording = data["candidate_wording"].strip()
    if "verification_status" in data and data["verification_status"] is not None:
        claim.verification_status = data["verification_status"]
        if claim.verification_status == VerificationStatus.CONFIRMED:
            claim.last_verified_at = _utcnow()
    if "responsibility_level" in data and data["responsibility_level"] is not None:
        claim.responsibility_level = data["responsibility_level"]
    if "boundary" in data and data["boundary"] is not None:
        claim.boundary = data["boundary"]
    if "interview_details" in data and data["interview_details"] is not None:
        claim.interview_details = data["interview_details"]
    if "risk_notes" in data and data["risk_notes"] is not None:
        claim.risk_notes = data["risk_notes"]
    if "evidence_ids" in data and data["evidence_ids"] is not None:
        claim.evidence_ids = _uuid_list(data["evidence_ids"])
    if "competency_ids" in data and data["competency_ids"] is not None:
        claim.competency_ids = list(data["competency_ids"])
    gates.assert_claim_confirmable(claim)
    db.commit()
    db.refresh(claim)
    return claim


def list_claims(db: Session, profile_id: UUID) -> list[models.EosClaim]:
    return (
        db.query(models.EosClaim)
        .filter(models.EosClaim.profile_id == profile_id)
        .order_by(models.EosClaim.created_at.desc())
        .all()
    )



def ingest_jd(db: Session, profile_id: UUID, body: schemas.JdCreate) -> models.EosJd:
    jd = models.EosJd(
        profile_id=profile_id,
        title=body.title or "Untitled role",
        company=body.company,
        raw_text=body.raw_text,
        language=body.language or "en",
        source_url=body.source_url,
    )
    db.add(jd)
    db.flush()
    for i, line in enumerate(split_requirements(body.raw_text)):
        comps, kws = competencies_for(line)
        db.add(
            models.EosRequirement(
                jd_id=jd.id,
                raw_text=line,
                normalized_text=line.lower(),
                priority=priority_for(line),
                keywords=kws,
                competency_ids=comps,
                sort_order=i,
            )
        )
    db.commit()
    db.refresh(jd)
    return jd


def get_jd_with_requirements(db: Session, jd_id: UUID) -> tuple[models.EosJd | None, list[models.EosRequirement]]:
    jd = db.query(models.EosJd).filter(models.EosJd.id == jd_id).first()
    if not jd:
        return None, []
    reqs = (
        db.query(models.EosRequirement)
        .filter(models.EosRequirement.jd_id == jd_id)
        .order_by(models.EosRequirement.sort_order)
        .all()
    )
    return jd, reqs


def _claim_covers(claim: models.EosClaim, req: models.EosRequirement) -> str:
    blob = f"{claim.candidate_wording} {claim.source_fact} {' '.join(claim.competency_ids)}".lower()
    hits = 0
    for kw in req.keywords or []:
        if kw and kw.lower() in blob:
            hits += 1
    for cid in req.competency_ids or []:
        if cid in (claim.competency_ids or []) or cid.replace("_", " ") in blob:
            hits += 1
    # soft text overlap on first significant tokens
    tokens = [t for t in re.findall(r"[a-zA-Z\u4e00-\u9fff]{4,}", req.normalized_text or "") if t]
    token_hits = sum(1 for t in tokens[:8] if t.lower() in blob)
    if hits >= 2 or token_hits >= 3:
        return MatchStatus.COVERED if claim.verification_status == VerificationStatus.CONFIRMED else MatchStatus.WEAK
    if hits == 1 or token_hits >= 1:
        return MatchStatus.WEAK
    return MatchStatus.MISSING


def run_match(db: Session, profile_id: UUID, jd_id: UUID) -> schemas.MatchRunResult:
    jd, reqs = get_jd_with_requirements(db, jd_id)
    if not jd or jd.profile_id != profile_id:
        raise gates.GateViolation("JD_NOT_FOUND", "JD not found for this profile", field="jd_id")
    claims = list_claims(db, profile_id)
    # clear prior rows for this jd
    db.query(models.EosMatchRow).filter(models.EosMatchRow.jd_id == jd_id).delete()
    rows_out: list[models.EosMatchRow] = []
    counts = {"covered": 0, "weak": 0, "missing": 0, "needs_excavation": 0}
    for req in reqs:
        best_status = MatchStatus.MISSING
        best_claims: list[str] = []
        best_evidence: list[str] = []
        rationale = "No overlapping claim found."
        questions: list[str] = []
        for claim in claims:
            st = _claim_covers(claim, req)
            if st == MatchStatus.COVERED:
                best_status = MatchStatus.COVERED
                best_claims = [str(claim.id)]
                best_evidence = list(claim.evidence_ids or [])
                rationale = "Confirmed claim overlaps requirement keywords/competencies."
                break
            if st == MatchStatus.WEAK and best_status != MatchStatus.COVERED:
                best_status = MatchStatus.WEAK
                best_claims = [str(claim.id)]
                best_evidence = list(claim.evidence_ids or [])
                rationale = "Partial overlap; claim not confirmed or thin evidence."
        if best_status == MatchStatus.MISSING:
            if req.priority in (RequirementPriority.HARD_GATE, RequirementPriority.CORE):
                best_status = MatchStatus.NEEDS_EXCAVATION
                questions = [
                    f"Have you done work related to: {req.raw_text[:120]}?",
                    "If yes, which org/project and what was your ownership boundary?",
                    "What evidence can confirm it (PRD, repo, metric artifact)?",
                ]
                rationale = "Core/hard requirement with no claim overlap — excavate before writing."
            else:
                rationale = "No overlap; preferred/nice-to-have left unmatched."
        key = best_status.value if hasattr(best_status, "value") else str(best_status)
        if key in counts:
            counts[key] += 1
        row = models.EosMatchRow(
            profile_id=profile_id,
            jd_id=jd_id,
            requirement_id=req.id,
            match_status=key,
            claim_ids=best_claims,
            evidence_ids=best_evidence,
            rationale=rationale,
            excavation_questions=questions,
        )
        db.add(row)
        rows_out.append(row)
    db.commit()
    for r in rows_out:
        db.refresh(r)
    return schemas.MatchRunResult(
        jd_id=jd_id,
        rows=[schemas.MatchRowOut.model_validate(r) for r in rows_out],
        covered=counts["covered"],
        weak=counts["weak"],
        missing=counts["missing"],
        needs_excavation=counts["needs_excavation"],
    )


def position_and_draft(
    db: Session,
    profile_id: UUID,
    body: schemas.PositionRequest,
) -> models.EosResumeVersion:
    claims = list_claims(db, profile_id)
    by_id = {str(c.id): c for c in claims}
    selected: list[models.EosClaim]
    if body.claim_ids:
        selected = [by_id[str(i)] for i in body.claim_ids if str(i) in by_id]
    else:
        # auto: confirmed claims linked in match rows for this JD
        match_rows = (
            db.query(models.EosMatchRow)
            .filter(models.EosMatchRow.jd_id == body.jd_id, models.EosMatchRow.profile_id == profile_id)
            .all()
        )
        ids: list[str] = []
        for mr in match_rows:
            if mr.match_status in (MatchStatus.COVERED, MatchStatus.WEAK):
                ids.extend(mr.claim_ids or [])
        # unique preserve
        seen = set()
        selected = []
        for i in ids:
            if i in seen or i not in by_id:
                continue
            seen.add(i)
            selected.append(by_id[i])

    confirmed = gates.filter_confirmed_only(selected)
    excluded = []
    bullets = []
    for c in selected:
        if c.verification_status != VerificationStatus.CONFIRMED:
            excluded.append(
                {
                    "claim_id": str(c.id),
                    "reason": f"status={c.verification_status}; final draft uses confirmed only",
                    "text": c.candidate_wording,
                }
            )
            continue
        gates.assert_no_metric_estimate(c.candidate_wording, field="candidate_wording")
        bullets.append(
            {
                "claim_id": str(c.id),
                "section": "experience",
                "text": c.candidate_wording,
                "verification_status": c.verification_status,
            }
        )

    if body.positioning_mode == "ambitious" and len(confirmed) < 2:
        # ambitious still cannot invent; only reorder/emphasize confirmed
        pass

    title = body.title or f"Resume for JD {body.jd_id}"
    lines = [title, "", "Experience"]
    for b in bullets:
        lines.append(f"- {b['text']}")
    if excluded:
        lines.append("")
        lines.append("# Excluded (not confirmed — not in final)")
        for e in excluded:
            lines.append(f"# - {e['text']} ({e['reason']})")
    full_text = "\n".join(lines)
    full_hash = gates.hash_text(full_text)

    ver = models.EosResumeVersion(
        profile_id=profile_id,
        jd_id=body.jd_id,
        positioning_mode=body.positioning_mode,
        title=title,
        full_text=full_text,
        full_text_hash=full_hash,
        status=VersionStatus.DRAFT,
        bullets=bullets,
        excluded=excluded,
        audit_safe=False,
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)
    return ver


def audit_version(db: Session, version: models.EosResumeVersion) -> schemas.AuditResult:
    claims = list_claims(db, version.profile_id)
    by_id = {str(c.id): c for c in claims}
    blockers = gates.assert_final_uses_confirmed_only(list(version.bullets or []), by_id)
    warnings: list[str] = []
    try:
        gates.assert_no_metric_estimate(version.full_text or "", field="full_text")
    except gates.GateViolation as e:
        blockers.append(e.message)
    try:
        gates.assert_no_ats_pass_claim(version.full_text or "")
    except gates.GateViolation as e:
        blockers.append(e.message)
    for b in version.bullets or []:
        cid = str(b.get("claim_id"))
        claim = by_id.get(cid)
        if claim and not (claim.evidence_ids or []):
            blockers.append(f"claim {cid} has no evidence_ids")
        if claim and claim.verification_status == VerificationStatus.CONFIRMED and not claim.boundary:
            warnings.append(f"claim {cid} confirmed but boundary empty — interview risk")
    audit_safe = len(blockers) == 0
    version.audit_safe = audit_safe
    version.status = VersionStatus.AWAITING_APPROVAL if audit_safe else VersionStatus.DRAFT
    version.full_text_hash = gates.hash_text(version.full_text or "")
    db.commit()
    return schemas.AuditResult(version_id=version.id, audit_safe=audit_safe, blockers=blockers, warnings=warnings)


def approve_version(db: Session, version: models.EosResumeVersion, body: schemas.ApproveRequest) -> models.EosApproval:
    if not version.audit_safe:
        raise gates.GateViolation("AUDIT_FAILED", "Run claim-audit successfully before approve.", field="audit_safe")
    gates.assert_approval_hash(version.full_text_hash, body.full_text_hash, version.full_text or "")
    appr = models.EosApproval(
        version_id=version.id,
        full_text_hash=body.full_text_hash,
        approver="user",
    )
    version.status = VersionStatus.APPROVED
    db.add(appr)
    db.commit()
    db.refresh(appr)
    return appr


def render_version(db: Session, version: models.EosResumeVersion) -> schemas.RenderResult:
    has_appr = (
        db.query(models.EosApproval)
        .filter(
            models.EosApproval.version_id == version.id,
            models.EosApproval.full_text_hash == gates.hash_text(version.full_text or ""),
        )
        .first()
        is not None
    )
    gates.assert_render_allowed(version.status, has_appr, version.audit_safe)
    version.status = VersionStatus.RENDERED
    db.commit()
    return schemas.RenderResult(
        version_id=version.id,
        status=version.status,
        full_text=version.full_text,
        message="Rendered after hash-bound approval. Heuristic evals available separately.",
    )


def run_heuristic_evals(db: Session, version: models.EosResumeVersion, jd_id: UUID | None = None) -> list[models.EosEvalReport]:
    jd_id = jd_id or version.jd_id
    text = (version.full_text or "").lower()
    reports: list[models.EosEvalReport] = []

    # keyword coverage vs JD requirements
    score_kw = 0.0
    missing: list[str] = []
    if jd_id:
        _, reqs = get_jd_with_requirements(db, jd_id)
        if reqs:
            hit = 0
            for r in reqs:
                ok = False
                for kw in r.keywords or []:
                    if kw and kw.lower() in text:
                        ok = True
                        break
                if not ok:
                    for t in re.findall(r"[a-zA-Z]{5,}", r.normalized_text or "")[:3]:
                        if t in text:
                            ok = True
                            break
                if ok:
                    hit += 1
                else:
                    missing.append(r.raw_text[:100])
            score_kw = hit / max(len(reqs), 1)
    label = gates.sanitize_eval_label("keyword_coverage", score_kw)
    gates.assert_no_ats_pass_claim(label)
    r1 = models.EosEvalReport(
        version_id=version.id,
        kind="keyword_coverage",
        score=round(score_kw, 4),
        label=label,
        is_heuristic=True,
        missing_items=missing[:20],
        notes="Heuristic lexical coverage only — not an ATS pass prediction.",
    )
    db.add(r1)
    reports.append(r1)

    # evidence coverage: fraction of bullets with claim.evidence_ids
    claims = {str(c.id): c for c in list_claims(db, version.profile_id)}
    bullets = version.bullets or []
    with_ev = 0
    for b in bullets:
        c = claims.get(str(b.get("claim_id")))
        if c and (c.evidence_ids or []):
            with_ev += 1
    score_ev = (with_ev / max(len(bullets), 1)) if bullets else 0.0
    r2 = models.EosEvalReport(
        version_id=version.id,
        kind="evidence_coverage",
        score=round(score_ev, 4),
        label=gates.sanitize_eval_label("evidence_coverage", score_ev),
        is_heuristic=True,
        missing_items=[],
        notes="Share of final bullets backed by evidence_ids.",
    )
    db.add(r2)
    reports.append(r2)

    # parsing / formatting risk heuristics
    risk = 0.0
    notes = []
    if "\t" in (version.full_text or ""):
        risk += 0.3
        notes.append("tabs present")
    if len(re.findall(r"[|│]", version.full_text or "")) > 5:
        risk += 0.2
        notes.append("many pipe characters")
    score_fmt = max(0.0, 1.0 - risk)
    r3 = models.EosEvalReport(
        version_id=version.id,
        kind="formatting_risk",
        score=round(score_fmt, 4),
        label=gates.sanitize_eval_label("formatting_risk", score_fmt),
        is_heuristic=True,
        missing_items=notes,
        notes="Higher score = lower formatting risk. Heuristic only.",
    )
    db.add(r3)
    reports.append(r3)

    db.commit()
    for r in reports:
        db.refresh(r)
    return reports
