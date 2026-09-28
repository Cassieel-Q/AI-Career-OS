"""Product-layer gates for Evidence OS (Zero Fabrication)."""
from __future__ import annotations

import hashlib
import re
from typing import Any

# Patterns that look like metric estimation language (EN + common CN)
_METRIC_ESTIMATE_PATTERNS = [
    re.compile(r"\b(estimate|estimated|roughly|approx(?:imately)?|around|about)\s+\d", re.I),
    re.compile(r"\b(assume|assumed|guess(?:ed)?|ballpark)\b.*\d", re.I),
    re.compile(r"(估算|大概|大约|估计|差不多).{0,8}\d"),
    re.compile(r"\+\s*\d+%\s*(?:lift|increase|growth)", re.I),
]

_ATS_PASS_PATTERNS = [
    re.compile(r"\b(will|would)\s+pass\s+(the\s+)?ats\b", re.I),
    re.compile(r"\bats\s+(pass|success)\s*(rate|score|probability|%\b)", re.I),
    re.compile(r"(通过|过)ATS.*(概率|率|分)"),
]


class GateViolation(Exception):
    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field}


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_no_metric_estimate(text: str, field: str = "text") -> None:
    for pat in _METRIC_ESTIMATE_PATTERNS:
        if pat.search(text or ""):
            raise GateViolation(
                "METRIC_ESTIMATE_FORBIDDEN",
                "Metric language looks estimated; only user-confirmed metrics are allowed.",
                field=field,
            )


def assert_metric_confirmed(metric: dict[str, Any] | None) -> None:
    if metric is None:
        return
    if not isinstance(metric, dict):
        raise GateViolation("METRIC_SHAPE", "metric must be an object", field="metric")
    if metric.get("source_confirmed") is not True:
        raise GateViolation(
            "METRIC_NOT_CONFIRMED",
            "metric.source_confirmed must be true before storing a metric.",
            field="metric.source_confirmed",
        )
    val = metric.get("value")
    if val is None or (isinstance(val, str) and not val.strip()):
        raise GateViolation("METRIC_EMPTY", "metric.value is required when metric is set", field="metric.value")


def assert_claim_confirmable(claim: Any) -> None:
    status = getattr(claim, "verification_status", None) or claim.get("verification_status")
    evidence_ids = getattr(claim, "evidence_ids", None) or claim.get("evidence_ids") or []
    if status == "confirmed" and not evidence_ids:
        raise GateViolation(
            "CONFIRM_WITHOUT_EVIDENCE",
            "confirmed claims require at least one evidence_id.",
            field="evidence_ids",
        )


def filter_confirmed_only(claims: list[Any]) -> list[Any]:
    out = []
    for c in claims:
        status = getattr(c, "verification_status", None) or c.get("verification_status")
        if status == "confirmed":
            out.append(c)
    return out


def assert_final_uses_confirmed_only(bullets: list[dict], claims_by_id: dict) -> list[str]:
    blockers: list[str] = []
    for b in bullets:
        cid = b.get("claim_id")
        claim = claims_by_id.get(str(cid)) or claims_by_id.get(cid)
        if claim is None:
            blockers.append(f"bullet references missing claim {cid}")
            continue
        status = getattr(claim, "verification_status", None)
        if status != "confirmed":
            blockers.append(f"claim {cid} is {status}, not confirmed")
    return blockers


def assert_approval_hash(stored_hash: str | None, provided_hash: str, current_text: str) -> None:
    current = hash_text(current_text)
    if stored_hash and stored_hash != current:
        raise GateViolation(
            "TEXT_DRIFT",
            "Resume text changed since hash was computed; re-approve after refresh.",
            field="full_text_hash",
        )
    if provided_hash != current:
        raise GateViolation(
            "HASH_MISMATCH",
            "Approval hash does not match current resume text.",
            field="full_text_hash",
        )


def assert_render_allowed(version_status: str, has_approval: bool, audit_safe: bool) -> None:
    if not audit_safe:
        raise GateViolation("AUDIT_FAILED", "Cannot render until claim-audit is audit_safe.", field="audit_safe")
    if version_status != "approved" and not has_approval:
        raise GateViolation(
            "APPROVAL_REQUIRED",
            "User approval (hash-bound) is required before render.",
            field="status",
        )


def sanitize_eval_label(kind: str, score: float) -> str:
    """Heuristic-only labels — never claim ATS pass probability."""
    band = "low"
    if score >= 0.75:
        band = "high"
    elif score >= 0.45:
        band = "medium"
    return f"heuristic_{kind}_{band}"


def assert_no_ats_pass_claim(text: str) -> None:
    for pat in _ATS_PASS_PATTERNS:
        if pat.search(text or ""):
            raise GateViolation(
                "ATS_PASS_CLAIM_FORBIDDEN",
                "Do not claim ATS pass rates or that a resume will pass ATS.",
                field="notes",
            )
