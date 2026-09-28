"""Honest interview-intel annotation for Interview Pack topics.

Pure helpers (no DB, no LLM) that decide, per interview-pack topic, which *real* interview
write-ups (牛客面经 imported as CURATED packs) may be cited, and what note the user sees.

Rules:
- Only real write-ups are cited. Synthetic/demo packs (DEMO_* ids, SYNTHETIC* / DEMO_ONLY
  provenance, company_relevance == SYNTHETIC_DEMO) are never cited and never mined for questions.
- Refs are built from the identifiers intel records actually carry after retrieval
  (``skill_id`` + ``source_refs``), with legacy ``id`` / ``source`` / ``ref`` / ``intel_ref`` as fallback.
- Only SAME-company real write-ups count as "该公司真实面经". Other companies' write-ups
  (retrieved as ROLE_FAMILY / GENERIC fillers) are shown only as
  「同类岗位参考（来自 X 公司）」 naming their real source company, never as the target company's.
- A topic without a matching same-company write-up gets 「暂无该公司真实面经，以下按 JD 推断」.
- Internal tags such as ``CURATED`` and the importer header line
  「在已整理的 N 条相关面经中观察到以下信号（CURATED，非合成演示）。」 never reach user-facing text.

This module never fabricates write-up content: every signal/question it returns is copied from the
supplied intel record bodies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .company_aliases import canonical_company
from .interview_intelligence import is_synthetic_pack

NO_REAL_INTEL_NOTE = "暂无该公司真实面经，以下按 JD 推断"
ROLE_FAMILY_PREFIX = "同类岗位参考"
UNKNOWN_SOURCE_COMPANY = "来源公司未注明"

_REF_KEYS = ("id", "source", "ref", "intel_ref")
_REAL_PROVENANCE_MARKERS = ("CURATED", "NIUKE", "NOWCODER", "牛客")
_INTERNAL_TAG_RE = re.compile(r"[（(]\s*CURATED[^）)]*[）)]|\bCURATED(?:_[A-Z0-9_]+)?\b", re.IGNORECASE)
_HEADER_RE = re.compile(r"观察到以下信号|条相关面经中")
_SOURCE_SUFFIX_RE = re.compile(r"\s*[（(]\s*来源面经[^）)]*[）)]\s*$")
_TAGS_SUFFIX_RE = re.compile(r"\s*\[[^\]]*\]\s*$")
_PLACEHOLDER_LINES = {"未提及", "（面经未提供明确 focus）", "(面经未提供明确 focus)", "（无题目）", "(无题目)"}
_TOPIC_PREFIX_RE = re.compile(r"^(能力证明|面试重点|核心能力证明)\s*[：:]\s*")
_TOKEN_SPLIT_RE = re.compile(r"[\s/、，,。；;：:·•|()（）「」『』\[\]【】<>《》\"'“”‘’+&-]+")
_GENERIC_TOKENS = {
    "能力", "证明", "面试", "重点", "经历", "项目", "岗位", "产品", "问题", "经理", "工作", "如何", "什么",
    "以及", "进行", "负责", "相关", "目标", "公司", "说明", "准备", "设计", "用户", "分析", "方案", "思路",
    "场景", "代表", "the", "and", "for", "with",
}
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{3,}")


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(x).strip() for x in value if str(x or "").strip()]
    return []


def is_synthetic_item(item: Mapping[str, object]) -> bool:
    """True for demo/synthetic intel records (respects f0425844c ``is_synthetic_pack``)."""
    skill_id = _text(item.get("skill_id") or item.get("id"))
    provenance = _text(item.get("provenance"))
    if is_synthetic_pack(skill_id, provenance):
        return True
    if _text(item.get("company_relevance")).upper() == "SYNTHETIC_DEMO":
        return True
    blob = " ".join([skill_id, provenance, _text(item.get("name")), _text(item.get("observed_label"))]).upper()
    return "SYNTHETIC" in blob or "DEMO_ONLY" in blob or "DEMO ONLY" in blob or skill_id.upper().startswith("DEMO")


def is_real_item(item: object) -> bool:
    """A real interview write-up record: not synthetic and traceable to a real source."""
    if not isinstance(item, Mapping) or is_synthetic_item(item):
        return False
    if _as_list(item.get("source_refs")):
        return True
    blob = " ".join([_text(item.get("skill_id")), _text(item.get("provenance"))]).upper()
    return any(marker in blob for marker in _REAL_PROVENANCE_MARKERS)


def item_refs(item: Mapping[str, object]) -> list[str]:
    """Identifiers to cite: skill_id, source_refs, then legacy id/source/ref/intel_ref."""
    refs: list[str] = []
    for value in [item.get("skill_id"), *_as_list(item.get("source_refs")), *(item.get(k) for k in _REF_KEYS)]:
        for ref in _as_list(value):
            if ref not in refs:
                refs.append(ref)
    return refs


def source_company(item: Mapping[str, object]) -> str | None:
    """Real source company of an intel record (explicit field, pack name, or CURATED_<CO>_<FAMILY> id)."""
    for key in ("company", "source_company"):
        value = _text(item.get(key))
        if value and value.upper() != "UNKNOWN":
            return value
    name = _text(item.get("name"))
    match = re.match(r"^(.+?)\s+curated\s+", name, re.IGNORECASE)
    if match and match.group(1).strip():
        return match.group(1).strip()
    skill_id = _text(item.get("skill_id"))
    if skill_id.upper().startswith("CURATED_"):
        core = skill_id[len("CURATED_"):]
        family = _text(item.get("role_family")).upper()
        for suffix in ([f"_{family}"] if family else []) + ["_AI_PRODUCT", "_PRODUCT"]:
            if core.upper().endswith(suffix) and len(core) > len(suffix):
                core = core[: -len(suffix)]
                break
        return core or None
    return None


def _same_company(item: Mapping[str, object], target_company: str | None) -> bool:
    target_key = canonical_company(target_company) if target_company and target_company.upper() != "UNKNOWN" else ""
    if not target_key:
        return False
    relevance = _text(item.get("company_relevance")).upper()
    if relevance and relevance != "SAME_COMPANY":
        return False
    src = source_company(item)
    if src:
        return canonical_company(src) == target_key
    return relevance == "SAME_COMPANY"


@dataclass(frozen=True)
class ClassifiedIntel:
    same_company: list[dict[str, object]] = field(default_factory=list)
    role_family: list[dict[str, object]] = field(default_factory=list)


def classify_intel(items: Iterable[object] | None, *, company: str | None) -> ClassifiedIntel:
    """Split real records into target-company write-ups vs other companies' role-family references."""
    same: list[dict[str, object]] = []
    family: list[dict[str, object]] = []
    for raw in items or []:
        if not is_real_item(raw):
            continue
        item = dict(raw)  # type: ignore[arg-type]
        (same if _same_company(item, company) else family).append(item)
    return ClassifiedIntel(same_company=same, role_family=family)


def real_same_company_items(items: Iterable[object] | None, *, company: str | None) -> list[dict[str, object]]:
    return classify_intel(items, company=company).same_company


def strip_internal_tags(text: str) -> str:
    cleaned = _INTERNAL_TAG_RE.sub("", text or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def clean_intel_hint(text: object) -> str | None:
    """User-safe hint line, or None for importer header / internal-tag-only lines."""
    raw = _text(text)
    if not raw or _HEADER_RE.search(raw):
        return None
    cleaned = strip_internal_tags(raw)
    if not cleaned or cleaned in _PLACEHOLDER_LINES:
        return None
    return cleaned


def _section_lines(body: str, heading: str) -> list[str]:
    out: list[str] = []
    active = False
    for line in (body or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            active = stripped[3:].strip().casefold().startswith(heading.casefold())
            continue
        if active and stripped.startswith("- "):
            out.append(stripped[2:].strip())
    return out


def write_up_signals(item: Mapping[str, object]) -> list[str]:
    """Interviewer focus signals copied from the write-up body ('Interviewer intent / focus')."""
    out: list[str] = []
    for line in _section_lines(_text(item.get("body")), "Interviewer intent"):
        value = clean_intel_hint(_SOURCE_SUFFIX_RE.sub("", line))
        if value and value not in out:
            out.append(value)
    return out


def write_up_questions(item: Mapping[str, object]) -> list[tuple[str, str]]:
    """(question, tags) pairs copied from the write-up body ('Question patterns')."""
    out: list[tuple[str, str]] = []
    for line in _section_lines(_text(item.get("body")), "Question patterns"):
        tags_match = re.search(r"\[([^\]]*)\]\s*$", line)
        tags = tags_match.group(1) if tags_match else ""
        question = clean_intel_hint(_TAGS_SUFFIX_RE.sub("", line))
        if question and all(question != q for q, _ in out):
            out.append((question, tags))
    return out


def _keep_token(token: str) -> bool:
    if token in _GENERIC_TOKENS:
        return False
    if any("\u4e00" <= ch <= "\u9fff" for ch in token):
        return len(token) >= 2
    return len(token) >= 3  # skip noisy ASCII like "ai"/"pm"


@dataclass(frozen=True)
class _TopicKeys:
    strong: list[str]  # whole phrase / separator-split parts
    bigram_groups: list[list[str]]  # CJK bigrams per long run; need >=2 hits from one run

    def __bool__(self) -> bool:
        return bool(self.strong or self.bigram_groups)


def _topic_tokens(topic: str, capabilities: Iterable[str] = ()) -> _TopicKeys:
    strong: list[str] = []
    groups: list[list[str]] = []
    for raw in [topic, *capabilities]:
        base = _TOPIC_PREFIX_RE.sub("", _text(raw))
        for part in [base, *_TOKEN_SPLIT_RE.split(base)]:
            token = part.strip().casefold()
            if token and _keep_token(token) and token not in strong:
                strong.append(token)
        for run in _CJK_RUN_RE.findall(base):
            grams = [g for g in dict.fromkeys(run[i : i + 2] for i in range(len(run) - 1)) if g not in _GENERIC_TOKENS]
            if len(grams) >= 2:
                groups.append(grams)
    return _TopicKeys(strong, groups)


def _matches(text: str, keys: _TopicKeys, tags: str = "") -> bool:
    """Strong keys may hit text or tags; bigram keys need >=2 distinct hits in the text itself."""
    low = (text or "").casefold()
    tag_low = (tags or "").casefold()
    if any(token in low or (tag_low and token in tag_low) for token in keys.strong):
        return True
    return any(sum(1 for gram in group if gram in low) >= 2 for group in keys.bigram_groups)


def _company_label(company: str | None) -> str:
    if not company:
        return UNKNOWN_SOURCE_COMPANY
    if company.endswith(("公司", "集团")) or "（" in company or "(" in company:
        return f"来自 {company}"
    return f"来自 {company} 公司"


@dataclass(frozen=True)
class TopicIntel:
    intel_refs: list[str]
    note: str
    signals: list[str]
    questions: list[str]
    reference_lines: list[str]
    reference_refs: list[str]

    @property
    def has_real_company_intel(self) -> bool:
        return bool(self.intel_refs)


def topic_intel(
    topic: str,
    *,
    capabilities: Iterable[str] = (),
    classified: ClassifiedIntel,
    company: str | None,
    max_questions: int = 3,
    max_refs: int = 6,
    max_references: int = 2,
) -> TopicIntel:
    tokens = _topic_tokens(topic, capabilities)
    refs: list[str] = []
    signals: list[str] = []
    questions: list[str] = []
    source_urls: set[str] = set()
    if tokens:
        for item in classified.same_company:
            item_signals = [s for s in write_up_signals(item) if _matches(s, tokens)]
            item_questions = [q for q, tags in write_up_questions(item) if _matches(q, tokens, tags)]
            meta_hit = _matches(_text(item.get("competency")), tokens)
            if not (item_signals or item_questions or meta_hit):
                continue
            for ref in item_refs(item):
                if ref not in refs:
                    refs.append(ref)
            source_urls.update(_as_list(item.get("source_refs")))
            signals.extend(s for s in item_signals if s not in signals)
            questions.extend(q for q in item_questions if q not in questions)
    refs = refs[:max_refs]
    questions = questions[:max_questions]
    display = _text(company) or "目标公司"
    if refs:
        count = len(source_urls) or 1
        note = f"参考 {display} 真实面经（{count} 篇牛客面经）"
        if signals:
            note += "：面试官关注 " + "；".join(signals[:3])
        return TopicIntel(refs, note, signals[:3], questions, [], [])

    reference_lines: list[str] = []
    reference_refs: list[str] = []
    for item in classified.role_family:
        if len(reference_lines) >= max_references:
            break
        item_questions = [q for q, tags in write_up_questions(item) if tokens and _matches(q, tokens, tags)]
        item_signals = [s for s in write_up_signals(item) if tokens and _matches(s, tokens)]
        if not (item_questions or item_signals):
            continue
        line = f"{ROLE_FAMILY_PREFIX}（{_company_label(source_company(item))}）"
        detail = item_questions[0] if item_questions else item_signals[0]
        reference_lines.append(f"{line}：{detail}")
        for ref in item_refs(item):
            if ref not in reference_refs:
                reference_refs.append(ref)
    return TopicIntel([], NO_REAL_INTEL_NOTE, [], [], reference_lines, reference_refs[:max_refs])


def _is_intel_note(line: str) -> bool:
    return (
        line.startswith(NO_REAL_INTEL_NOTE)
        or line.startswith(ROLE_FAMILY_PREFIX)
        or (line.startswith("参考 ") and "真实面经" in line)
    )


def _foreign_questions(interview_intel: Iterable[object] | None, classified: ClassifiedIntel) -> set[str]:
    """Questions from other companies' or synthetic packs; never shown unlabeled as target-company intel."""
    same_ids = {_text(item.get("skill_id")) for item in classified.same_company if _text(item.get("skill_id"))}
    own = {q for item in classified.same_company for q, _ in write_up_questions(item)}
    foreign: set[str] = set()
    for raw in interview_intel or []:
        if not isinstance(raw, Mapping):
            continue
        if is_real_item(raw) and _text(raw.get("skill_id")) in same_ids:
            continue
        foreign.update(q for q, _ in write_up_questions(raw))
        for key in ("question_patterns", "questions", "sample_questions"):
            foreign.update(q for q in (clean_intel_hint(x) for x in _as_list(raw.get(key))) if q)
    return foreign - own


def annotate_topics(
    topics: Iterable[Mapping[str, object]],
    interview_intel: Iterable[object] | None,
    *,
    company: str | None,
) -> list[dict[str, object]]:
    """Return topic dicts with honest intel_refs / notes; strips internal tags from user text.

    - ``intel_refs``: only ids of real same-company write-ups matching the topic (plus any
      pre-existing refs that point at those same real write-ups).
    - ``evidence_expected[0]``: the intel note (real signals, or the 暂无 sentence), followed by
      optional 「同类岗位参考（来自 X 公司）」 lines for other companies' write-ups.
    - ``question_patterns``: up to 3 real questions from matching same-company write-ups first.
    """
    classified = classify_intel(interview_intel, company=company)
    allowed = {ref for item in classified.same_company for ref in item_refs(item)}
    foreign_questions = _foreign_questions(interview_intel, classified)
    out: list[dict[str, object]] = []
    for raw in topics or []:
        item = dict(raw)
        topic = strip_internal_tags(_text(item.get("topic")))
        info = topic_intel(
            topic,
            capabilities=_as_list(item.get("capabilities")),
            classified=classified,
            company=company,
        )
        kept = [ref for ref in _as_list(item.get("intel_refs")) if ref in allowed]
        refs = list(dict.fromkeys([*info.intel_refs, *kept]))[:20]
        if refs and not info.intel_refs:
            # A pre-existing (e.g. LLM) ref to a real same-company write-up: keep it, note honestly.
            info = TopicIntel(refs, f"参考 {_text(company) or '目标公司'} 真实面经", [], [], [], [])
        evidence = []
        for line in _as_list(item.get("evidence_expected")):
            cleaned = clean_intel_hint(line)
            if not cleaned or _is_intel_note(cleaned) or cleaned.rstrip("：:") == "面经要点":
                continue
            evidence.append(cleaned)
        evidence = [info.note, *info.reference_lines, *evidence]
        questions = [
            q
            for q in (clean_intel_hint(x) for x in _as_list(item.get("question_patterns")))
            if q and q not in foreign_questions
        ]
        questions = list(dict.fromkeys([*info.questions, *questions]))
        item["topic"] = topic or "面试准备主题"
        item["why"] = strip_internal_tags(_text(item.get("why"))) or "本岗面试很可能追问这个主题。"
        item["intel_refs"] = refs
        item["evidence_expected"] = list(dict.fromkeys(evidence))[:20]
        item["question_patterns"] = questions[:20]
        out.append(item)
    return out
