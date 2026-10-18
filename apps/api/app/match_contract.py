"""统一的岗位匹配结果契约（可信求职 v1.2 · 指令 2.1 / 2.2）。

一个页面说「值得投递」、另一个页面说「建议先换岗位」的根因，是分数与结论各算各的。
本模块规定：**分档（grade）与建议（recommendation）必须由分数在同一处推导出来**，
模型给的补充建议只在与分档不冲突时才展示。

对外只有一个结果形状::

    {
      "score": int,                    # 0-100
      "grade": "strong|maybe|weak",    # 由 score 推导
      "grade_label": "值得投递|先补齐再投|暂不建议投递",
      "recommendation": str,           # 与 grade 同源，绝不互相矛盾
      "blocking_gaps": [str],          # 硬性要求未命中（不可豁免）
      "supporting_evidence": [str],    # 命中的依据
      "analysis_version": str,         # 结果形状版本
      "rule_version": str,             # 分档与建议规则版本
      "inputs": {...},                 # 输入指纹，用于判定过期
      "generated_at": str,
    }

旧字段（``verdict`` / ``reasons`` / ``gaps`` / ``advice``）保留，值全部来自同一份结论，
避免前端各处自己推导。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

#: 结果形状版本。改动字段语义时必须递增。
MATCH_ANALYSIS_VERSION = "match-contract-v1"

#: 分档与建议规则版本。改分档阈值或建议文案时必须递增。
RULE_VERSION = "bands-2026-10-18"

GRADE_LABEL = {
    "strong": "值得投递",
    "maybe": "先补齐再投",
    "weak": "暂不建议投递",
}

#: 与分档同源的建议文案。分数变，建议必然跟着变。
RECOMMENDATION_BY_GRADE = {
    "strong": "匹配度不错，可以准备投递，并在面试里重点讲命中的要求。",
    "maybe": "先把未命中的要求补齐或找到可讲的例子，再决定是否投递。",
    "weak": "当前简历与这个岗位差距较大，建议先换更匹配的岗位或补强经历。",
}

#: 与分档明显冲突的说法。命中即用标准建议替换，绝不并列展示。
_CONFLICT_PATTERNS: dict[str, tuple[str, ...]] = {
    "strong": ("不建议投递", "暂不投", "先换更匹配", "换更匹配", "不建议投", "放弃这个岗位", "不值得投递"),
    "maybe": ("可以直接投递", "值得投递", "建议立刻投递", "放弃这个岗位", "不建议投递"),
    "weak": ("可以直接投递", "值得投递", "建议立刻投递", "放心投递", "优先投递"),
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,20}|[\u4e00-\u9fa5]{2,6}")


def grade_for_score(score: int) -> str:
    """分档阈值（唯一来源）。"""
    if score >= 70:
        return "strong"
    if score >= 40:
        return "maybe"
    return "weak"


def recommendation_for_grade(grade: str) -> str:
    return RECOMMENDATION_BY_GRADE.get(grade, RECOMMENDATION_BY_GRADE["maybe"])


def advice_conflicts_with_grade(grade: str, advice: str | None) -> bool:
    """模型补充建议是否与分档矛盾。不确定时不算冲突，但也不会覆盖标准建议。"""
    if not advice:
        return False
    text = str(advice)
    return any(pattern in text for pattern in _CONFLICT_PATTERNS.get(grade, ()))


def resolve_advice(grade: str, model_advice: str | None) -> tuple[str, bool]:
    """返回 (最终建议, 是否丢弃了模型建议)。

    模型建议与分档冲突时**丢弃**模型的，用与分档同源的标准建议；
    不冲突时可以展示模型更具体的那句。
    """
    standard = recommendation_for_grade(grade)
    if advice_conflicts_with_grade(grade, model_advice):
        return standard, True
    if model_advice and model_advice.strip():
        return model_advice.strip(), False
    return standard, False


def content_hash(text: str | None) -> str:
    """输入指纹：用于判断分析结果是否过期（不用更新时间猜）。"""
    return hashlib.sha256((text or "").encode("utf-8", "ignore")).hexdigest()[:16]


def build_input_fingerprint(
    *,
    resume_text: str | None,
    jd_text: str | None,
    requirement_names: list[str] | None = None,
    profile_id: str | None = None,
    target_job_id: str | None = None,
) -> dict[str, Any]:
    requirements = [str(name).strip() for name in (requirement_names or []) if str(name).strip()]
    return {
        "resume_hash": content_hash(resume_text),
        "resume_chars": len(resume_text or ""),
        "jd_hash": content_hash(jd_text),
        "requirement_hash": content_hash("\n".join(requirements)),
        "requirement_count": len(requirements),
        "profile_id": str(profile_id) if profile_id else None,
        "target_job_id": str(target_job_id) if target_job_id else None,
    }


def _resume_tokens(resume_text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(resume_text or "") if token.strip()}


#: 要求名里的修饰词：「必须具备 SQL 建模能力」的核心其实是「SQL 建模」。
_MODIFIER_RE = re.compile(r"必须|须|需|要求|具备|熟练掌握|熟练|掌握|能够|优先|相关|良好|以上|的|能力|经验|背景|经历|证书|证明")


def requirement_is_covered(requirement: str, resume_text: str) -> bool:
    """岗位要求在简历里有没有直接依据。"""
    name = str(requirement or "").strip()
    if not name:
        return False
    if name.casefold() in (resume_text or "").casefold():
        return True
    core = _MODIFIER_RE.sub("", name).strip()
    if core and core.casefold() in (resume_text or "").casefold():
        return True
    tokens = _resume_tokens(resume_text)
    if name.casefold() in tokens or (core and core.casefold() in tokens):
        return True
    # 核心词里大部分命中才算覆盖，避免单个通用词误判。
    parts = [part for part in _TOKEN_RE.findall(core or name) if len(part) >= 2]
    if not parts:
        return False
    hits = sum(1 for part in parts if part.casefold() in tokens or part in (resume_text or ""))
    return hits >= max(1, (len(parts) + 1) // 2)


def hard_requirement_names(parsed_jd: dict | None, what_matters: dict | None) -> list[str]:
    """硬性要求名：显式标记为必须 / must-have 的那些。

    识别不出来就返回空列表（宁可漏，也不把普通要求当硬门槛）。
    """
    names: list[str] = []
    hard_markers = ("必须", "硬性", "必备", "要求具备", "must", "must-have", "must_have", "硬性要求")

    def push(value: object, markers: bool) -> None:
        text = str(value or "").strip()
        if not text or text in names:
            return
        if markers:
            names.append(text)

    for source in (dict(parsed_jd or {}), dict(what_matters or {})):
        for bucket in ("requirements", "high_importance_requirements", "must_have", "hard_requirements"):
            items = source.get(bucket) or []
            if isinstance(items, dict):
                items = [items]
            for item in items or []:
                if isinstance(item, dict):
                    label = " ".join(
                        str(item.get(key) or "")
                        for key in ("category", "level", "priority", "kind", "type", "severity")
                    ).casefold()
                    text = item.get("text") or item.get("name")
                    explicit = any(marker in label for marker in hard_markers)
                    raw = f"{item.get('text') or item.get('name') or ''}"
                    if not explicit:
                        explicit = any(marker in str(raw).casefold() for marker in hard_markers)
                    push(text, explicit)
                elif isinstance(item, str):
                    if any(marker in item.casefold() for marker in hard_markers):
                        push(item, True)
    return names


def compute_blocking_gaps(
    *,
    resume_text: str,
    parsed_jd: dict | None,
    what_matters: dict | None,
) -> list[str]:
    """硬性要求里简历完全没有依据的那些——即使技能相关度高也必须展示。"""
    hard = hard_requirement_names(parsed_jd, what_matters)
    if not hard:
        return []
    return [name for name in hard if not requirement_is_covered(name, resume_text)]


def build_match_result(
    *,
    score: Any,
    reasons: list[str] | None,
    gaps: list[str] | None,
    model_advice: str | None,
    source: str,
    resume_text: str | None,
    jd_text: str | None,
    requirement_names: list[str] | None = None,
    parsed_jd: dict | None = None,
    what_matters: dict | None = None,
    profile_id: str | None = None,
    target_job_id: str | None = None,
    resume_source: str | None = None,
) -> dict[str, Any]:
    """把模型或本地规则的输出收成唯一的对外契约。"""
    try:
        value = int(round(float(score)))
    except (TypeError, ValueError):
        value = 0
    value = max(0, min(100, value))

    grade = grade_for_score(value)
    recommendation, dropped = resolve_advice(grade, model_advice)
    evidence = [str(item).strip() for item in (reasons or []) if str(item).strip()]
    gap_items = [str(item).strip() for item in (gaps or []) if str(item).strip()]
    blocking = compute_blocking_gaps(
        resume_text=resume_text or "",
        parsed_jd=parsed_jd,
        what_matters=what_matters,
    )

    payload = {
        # 新契约（唯一权威）
        "score": value,
        "grade": grade,
        "grade_label": GRADE_LABEL.get(grade, "待评估"),
        "recommendation": recommendation,
        "blocking_gaps": blocking,
        "supporting_evidence": evidence,
        "analysis_version": MATCH_ANALYSIS_VERSION,
        "rule_version": RULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # 旧字段：值与上面同源，供存量前端平滑过渡
        "verdict": grade,
        "verdict_label": GRADE_LABEL.get(grade, "待评估"),
        "reasons": evidence,
        "gaps": gap_items,
        "advice": recommendation,
        "source": source,
        "model_advice_dropped": dropped,
        "model_advice": (model_advice or "").strip() or None,
        "resume_source": resume_source,
        "resume_chars": len(resume_text or ""),
    }
    payload["inputs"] = build_input_fingerprint(
        resume_text=resume_text,
        jd_text=jd_text,
        requirement_names=requirement_names,
        profile_id=profile_id,
        target_job_id=target_job_id,
    )
    return payload


def stale_status(cached: dict | None, current_inputs: dict) -> dict[str, Any]:
    """比较当前输入与分析时的输入指纹，判断是否过期。

    只标记不替换：后台绝不偷偷重算或覆盖用户已有的分析结果。
    """
    if not cached:
        return {"stale": False, "reasons": [], "analyzed_at": None}
    stored = dict(cached.get("inputs") or {})
    if not stored:
        # 老结果没有指纹：无法证明它仍然适用，保守标记为「可能过期」。
        return {
            "stale": True,
            "reasons": ["这份分析是在旧版本结果格式下生成的，无法核对当时的输入。"],
            "analyzed_at": cached.get("generated_at"),
        }
    reasons: list[str] = []
    if stored.get("resume_hash") != current_inputs.get("resume_hash"):
        reasons.append("简历原文已经修改，最近的事实改动还没纳入这份分析。")
    if stored.get("jd_hash") != current_inputs.get("jd_hash"):
        reasons.append("岗位描述已经修改，这份分析基于旧版 JD。")
    if stored.get("requirement_hash") != current_inputs.get("requirement_hash"):
        reasons.append("岗位要求解析结果已经变化，这份分析的比对基准已过期。")
    return {
        "stale": bool(reasons),
        "reasons": reasons,
        "analyzed_at": cached.get("generated_at"),
        "current_inputs": current_inputs,
    }


__all__ = [
    "GRADE_LABEL",
    "MATCH_ANALYSIS_VERSION",
    "RECOMMENDATION_BY_GRADE",
    "RULE_VERSION",
    "build_input_fingerprint",
    "build_match_result",
    "compute_blocking_gaps",
    "content_hash",
    "grade_for_score",
    "hard_requirement_names",
    "recommendation_for_grade",
    "requirement_is_covered",
    "resolve_advice",
    "stale_status",
]
