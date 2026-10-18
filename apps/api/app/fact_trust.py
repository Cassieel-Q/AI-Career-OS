"""事实可信度契约与确定性闸门。

本模块把三件长期被混为一谈的事拆成独立维度：

A. **事实来源** ``FactSource`` —— 这条事实是从哪里来的。
   - ``SOURCE_EXTRACTED``：系统从用户原始材料（简历 / 档案）里提取到。
   - ``USER_PROVIDED``：用户后来主动补充。
   - ``AI_PROPOSED``：AI 建议的内容，尚未形成可信事实。

B. **用户核对** ``VerificationStatus`` —— 用户是否亲自确认过它属实。
   - ``UNREVIEWED``：未核对。
   - ``USER_ATTESTED``：用户明确确认属实。
   - ``REJECTED``：用户否认或删除。

C. **文案采纳** —— 用户是否采用了某句 AI 改写。它独立于 A 和 B：
   用户采用一句改写，只说明他接受这个**表达**，不代表他核实了里面的**事实**。

因此「提取到」「采纳改写」「核实事实」三者互不推导。任何把其中一项自动升级为
另一项的代码都是缺陷。

确定性闸门（``screen_text`` / ``screen_reference_wording``）用于拦截把无依据内容
写成候选人第一人称陈述的输出。它是**保守**的：判断不确定时一律降级，绝不默默放行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable, Sequence


class FactSource(StrEnum):
    """事实来源维度。"""

    SOURCE_EXTRACTED = "SOURCE_EXTRACTED"
    USER_PROVIDED = "USER_PROVIDED"
    AI_PROPOSED = "AI_PROPOSED"


class VerificationStatus(StrEnum):
    """用户核对维度。"""

    UNREVIEWED = "UNREVIEWED"
    USER_ATTESTED = "USER_ATTESTED"
    REJECTED = "REJECTED"


#: 覆盖率阈值。低于该值的陈述片段视为「含无依据内容」。
COVERAGE_THRESHOLD = 0.45

#: 极短片段不做覆盖率判断（bigram 基数太小，误伤严重）。
MIN_CLAIM_CHARS = 6

#: 高风险动作/结果词：出现在陈述里但证据语料中完全找不到时，视为编造。
HIGH_RISK_TERMS: tuple[str, ...] = (
    "主导",
    "带领",
    "牵头",
    "上线",
    "落地",
    "投产",
    "发布上线",
    "搭建",
    "从0到1",
    "从零到一",
    "提升",
    "提高",
    "增长",
    "降低",
    "节省",
    "缩短",
    "转化率",
    "留存率",
    "日活",
    "月活",
    "复购",
    "营收",
    "变现",
    "商业化",
    "获奖",
    "第一名",
    "专利",
    "论文",
)

_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "二": 2,
    "两": 2,
    "贰": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}
_CN_UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
_CN_SCALES = {"万": 10_000, "亿": 100_000_000}

_ARABIC_RE = re.compile(r"\d+(?:\.\d+)?")
_CN_NUMBER_RE = re.compile(r"[零〇一二两三四五六七八九十百千万亿壹贰叁肆伍陆柒捌玖拾佰仟]+")
_PUNCT_RE = re.compile(r"[\s，。；、：,.!?！？；:（）()\[\]【】《》\"'`~—\-_/\\|]+")
_SPLIT_RE = re.compile(r"[。；;！!？?\n]+")


# --------------------------------------------------------------------------
# 文本归一与切分
# --------------------------------------------------------------------------


def normalize_text(text: object) -> str:
    """去掉标点空白，只保留参与比对的字符。"""
    if text is None:
        return ""
    return _PUNCT_RE.sub("", str(text))


def split_sentences(text: str) -> list[str]:
    """按中文句读切分；过短或空片段丢弃。"""
    parts = [part.strip() for part in _SPLIT_RE.split(str(text or ""))]
    return [part for part in parts if len(normalize_text(part)) >= 2]


# --------------------------------------------------------------------------
# 数值抽取（同时识别阿拉伯数字与中文数字）
# --------------------------------------------------------------------------


def _parse_cn_number(token: str) -> int | None:
    """把「十二」「三十」「一百二十」「三万」解析成整数。解析不了返回 None。"""
    if not token:
        return None
    total = 0
    section = 0
    last_digit: int | None = None
    for char in token:
        if char in _CN_DIGITS:
            last_digit = _CN_DIGITS[char]
            continue
        if char in _CN_UNITS:
            # 「十二」= 1*10 + 2，「一百二十」= 1*100 + 2*10
            section += (last_digit if last_digit is not None else 1) * _CN_UNITS[char]
            last_digit = None
            continue
        if char in _CN_SCALES:
            total += (section + (last_digit or 0)) * _CN_SCALES[char]
            section = 0
            last_digit = None
            continue
        return None
    return total + section + (last_digit or 0)


def extract_numeric_values(text: object) -> set[int]:
    """抽取文本里出现过的所有数量值（阿拉伯数字与中文数字归一为整数集合）。"""
    raw = str(text or "")
    values: set[int] = set()
    for token in _ARABIC_RE.findall(raw):
        try:
            value = float(token)
        except ValueError:
            continue
        if value.is_integer():
            values.add(int(value))
        else:
            values.add(int(round(value * 100)))
    for token in _CN_NUMBER_RE.findall(raw):
        # 纯「一二」这类助词/数量词会污染结果，只接受带单位或 >= 2 位的写法。
        parsed = _parse_cn_number(token)
        if parsed is None or parsed <= 0:
            continue
        if len(token) == 1 and parsed < 2:
            continue
        values.add(parsed)
    return values


# --------------------------------------------------------------------------
# 覆盖率：确定性「这句话有没有依据」
# --------------------------------------------------------------------------


def _bigrams(text: str) -> set[str]:
    norm = normalize_text(text)
    if len(norm) < 2:
        return {norm} if norm else set()
    return {norm[i : i + 2] for i in range(len(norm) - 1)}


def coverage_score(claim: str, corpus: str) -> float:
    """候选陈述相对证据语料的字符 bigram 覆盖率，0.0 - 1.0。"""
    claim_bigrams = _bigrams(claim)
    if not claim_bigrams:
        return 1.0
    corpus_bigrams = _bigrams(corpus)
    return len(claim_bigrams & corpus_bigrams) / len(claim_bigrams)


@dataclass
class ScreeningResult:
    """一段陈述的事实筛查结果。"""

    supported: bool
    coverage: float
    reasons: list[str] = field(default_factory=list)
    unsupported_sentences: list[str] = field(default_factory=list)
    missing_numbers: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "supported": self.supported,
            "coverage": round(self.coverage, 3),
            "reasons": self.reasons,
            "unsupported_sentences": self.unsupported_sentences,
            "missing_numbers": self.missing_numbers,
        }


def screen_text(text: object, corpus: object, *, threshold: float = COVERAGE_THRESHOLD) -> ScreeningResult:
    """对一段候选人陈述做事实筛查。

    三条确定性规则，任一命中即判定 unsupported：

    1. 出现证据语料中不存在的数量值（阿拉伯数字与中文数字都查）。
    2. 出现证据语料中完全不存在的高风险动作/结果词（上线、提升、主导 ……）。
    3. 某个句子的字符 bigram 覆盖率低于阈值，说明它引入了语料里没有的内容。

    规则保守：语料为空时直接判定 unsupported —— 没有证据就不能写事实。
    """
    statement = str(text or "").strip()
    evidence = str(corpus or "")
    if not statement:
        return ScreeningResult(supported=True, coverage=1.0)
    if not normalize_text(evidence):
        return ScreeningResult(
            supported=False,
            coverage=0.0,
            reasons=["缺少可核对的事实语料，不能生成候选人陈述。"],
            unsupported_sentences=[statement],
        )

    reasons: list[str] = []
    unsupported: list[str] = []

    evidence_values = extract_numeric_values(evidence)
    missing_numbers = sorted(extract_numeric_values(statement) - evidence_values)
    if missing_numbers:
        reasons.append(f"陈述中出现证据里没有的数量值：{missing_numbers}。")
        unsupported.append(statement)

    norm_evidence = normalize_text(evidence)
    hit_terms = [term for term in HIGH_RISK_TERMS if term in statement and normalize_text(term) not in norm_evidence]
    if hit_terms:
        reasons.append(f"陈述中使用了证据里没有的高风险动作或结果词：{sorted(set(hit_terms))}。")
        if statement not in unsupported:
            unsupported.append(statement)

    sentences = split_sentences(statement) or [statement]
    coverages = [coverage_score(sentence, evidence) for sentence in sentences]
    worst = min(coverages) if coverages else 0.0
    for sentence, score in zip(sentences, coverages):
        if len(normalize_text(sentence)) >= MIN_CLAIM_CHARS and score < threshold and sentence not in unsupported:
            unsupported.append(sentence)
            reasons.append(f"以下句子与可核对事实的重合度仅 {score:.0%}：{sentence[:40]}")

    return ScreeningResult(
        supported=not unsupported,
        coverage=worst,
        reasons=reasons,
        unsupported_sentences=unsupported,
        missing_numbers=missing_numbers,
    )


def screen_reference_wording(
    wording: object,
    corpus: object,
    *,
    threshold: float = COVERAGE_THRESHOLD,
) -> ScreeningResult:
    """筛查「可使用的示范表达」。语义同 :func:`screen_text`，保留独立入口便于定制阈值。"""
    return screen_text(wording, corpus, threshold=threshold)


# --------------------------------------------------------------------------
# 降级渲染：证据不足时给出「已知事实 / 待补 / 方法」，不产出第一人称成稿
# --------------------------------------------------------------------------

_BLOCKED_NOTICE = "当前可核对事实不足以生成完整示范回答；下面是已有的事实、还缺的信息和建议的表达结构。"


def render_degraded_reference(
    *,
    known_facts: Sequence[object] | None = None,
    missing_facts: Sequence[object] | None = None,
    answer_structure: Sequence[object] | None = None,
    reason: str | None = None,
) -> str:
    """把结构化内容渲染成安全文本。

    只呈现已知事实、待补充项与回答方法，**绝不**补造第一人称经历。
    """
    lines: list[str] = [reason or _BLOCKED_NOTICE, ""]

    def _text_of(item: object) -> str:
        if isinstance(item, dict):
            for key in ("text", "fact", "aspect", "question", "step", "label"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return ""
        return str(item).strip()

    known = [_text_of(item) for item in (known_facts or [])]
    known = [item for item in known if item]
    lines.append("【已知事实】")
    if known:
        lines.extend(f"- {item}" for item in known)
    else:
        lines.append("- 暂无可引用的已确认事实。")
    lines.append("")

    missing = [_text_of(item) for item in (missing_facts or [])]
    missing = [item for item in missing if item]
    lines.append("【还需要你补充】")
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- 暂无。")
    lines.append("")

    structure = [_text_of(item) for item in (answer_structure or [])]
    structure = [item for item in structure if item]
    lines.append("【建议回答结构】")
    if structure:
        lines.extend(f"{index}. {item}" for index, item in enumerate(structure, start=1))
    else:
        lines.append("1. 背景与目标")
        lines.append("2. 你的具体动作")
        lines.append("3. 关键取舍")
        lines.append("4. 可核对的结果")
    lines.append("")
    lines.append("补充上述信息后，系统才会生成可使用的示范表达。")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 旧状态迁移：保守，绝不把「已解析」升级为「用户已核实」
# --------------------------------------------------------------------------

#: 旧枚举 → 事实来源。无法区分来源时按「从原始材料提取」处理。
_LEGACY_SOURCE_MAP: dict[str, FactSource] = {
    "EXTRACTED": FactSource.SOURCE_EXTRACTED,
    "SOURCE_EXTRACTED": FactSource.SOURCE_EXTRACTED,
    "SUPPORTED": FactSource.SOURCE_EXTRACTED,
    "DEFENDABLE": FactSource.SOURCE_EXTRACTED,
    "USER_PROVIDED": FactSource.USER_PROVIDED,
    "EDITED": FactSource.USER_PROVIDED,
    "AI_PROPOSED": FactSource.AI_PROPOSED,
    "SUGGESTED": FactSource.AI_PROPOSED,
    "UNSUPPORTED": FactSource.AI_PROPOSED,
}

#: 旧枚举 → 核对状态。注意 CONFIRMED / ACCEPTED / READY **都不会**变成 USER_ATTESTED：
#: 系统无法用这些状态证明存在一次明确的用户核对行为。
_LEGACY_VERIFICATION_MAP: dict[str, VerificationStatus] = {
    "UNREVIEWED": VerificationStatus.UNREVIEWED,
    "NEEDS_CONFIRMATION": VerificationStatus.UNREVIEWED,
    "CONFIRMED": VerificationStatus.UNREVIEWED,
    "ACCEPTED": VerificationStatus.UNREVIEWED,
    "READY": VerificationStatus.UNREVIEWED,
    "REJECTED": VerificationStatus.REJECTED,
    "USER_ATTESTED": VerificationStatus.USER_ATTESTED,
}


def legacy_source(value: object, *, default: FactSource = FactSource.SOURCE_EXTRACTED) -> FactSource:
    if isinstance(value, FactSource):
        return value
    key = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return _LEGACY_SOURCE_MAP.get(key, default)


def legacy_verification(value: object) -> VerificationStatus:
    """迁移旧状态到核对维度。

    **保守原则**：除已有的 ``USER_ATTESTED`` 与 ``REJECTED`` 外，一切旧状态
    （包括 ``CONFIRMED``、``ACCEPTED``）都落到 ``UNREVIEWED``。批量把自动确认
    升级为「用户已核实」是本模块要杜绝的行为。
    """
    if isinstance(value, VerificationStatus):
        return value
    key = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return _LEGACY_VERIFICATION_MAP.get(key, VerificationStatus.UNREVIEWED)


def is_attested(value: object) -> bool:
    """只有明确的 USER_ATTESTED 才算「用户已核实」。"""
    return legacy_verification(value) is VerificationStatus.USER_ATTESTED


def merge_grounding(parts: Iterable[object]) -> str:
    """把多份来源文本拼成一条证据语料，供覆盖率计算使用。"""
    chunks: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (dict, list, tuple)):
            import json

            chunks.append(json.dumps(part, ensure_ascii=False, default=str))
        else:
            text = str(part).strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks)
