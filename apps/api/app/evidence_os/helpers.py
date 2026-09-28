"""Pure helpers for JD ingest (no DB)."""
from __future__ import annotations

import re

_COMPETENCY_KW: list[tuple[str, list[str]]] = [
    ("model_evaluation", ["evaluation", "eval", "offline eval", "online eval", "a/b", "ab test", "llm-as-judge"]),
    ("agents", ["agent", "agents", "tool use", "tool-calling", "multi-agent", "orchestration"]),
    ("rag", ["rag", "retrieval", "vector", "embedding", "knowledge base"]),
    ("guardrails", ["guardrail", "safety", "policy", "red team", "jailbreak", "moderation"]),
    ("latency_cost", ["latency", "p95", "throughput", "cost", "token", "infra cost"]),
    ("roadmap", ["roadmap", "prioriti", "backlog", "okrs", "okr"]),
    ("xfn", ["cross-functional", "stakeholder", "engineering", "design", "go-to-market", "gtm"]),
    ("metrics", ["metric", "kpi", "north star", "retention", "conversion"]),
    ("prompting", ["prompt", "prompt engineering", "system prompt"]),
    ("data", ["data pipeline", "analytics", "instrumentation", "telemetry"]),
]

_HARD_MARKERS = ["must have", "required", "minimum", "必须", "硬性", "必备"]
_PREF_MARKERS = ["nice to have", "preferred", "bonus", "加分", "优先"]


def split_requirements(raw: str) -> list[str]:
    lines: list[str] = []
    for line in re.split(r"[\n\r]+", raw):
        t = re.sub(r"^[\s\-\*\u2022\d\.\)\(]+", "", line).strip()
        if len(t) >= 12:
            lines.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for t in lines:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out[:80]


def priority_for(text: str) -> str:
    low = text.lower()
    if any(m in low for m in _HARD_MARKERS):
        return "hard_gate"
    if any(m in low for m in _PREF_MARKERS):
        return "preferred"
    return "core"


def competencies_for(text: str) -> tuple[list[str], list[str]]:
    low = text.lower()
    comps: list[str] = []
    kws: list[str] = []
    for cid, words in _COMPETENCY_KW:
        for w in words:
            if w in low:
                comps.append(cid)
                kws.append(w)
                break
    return comps, kws
