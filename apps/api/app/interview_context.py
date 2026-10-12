"""第一阶段：面试上下文解析器 ``InterviewContextResolver``。

把「一句用户消息 + 当前页面上下文」解析成结构化面试上下文，供后续
``MissionInterviewContext`` 加载与固定流程 Agent 使用。

输入：
- 用户消息、当前路由、当前 mission_id、当前 target_resume_id、当前 profile_id、会话历史。

输出（``ResolvedContext``）：
- intent / company / role / mission_id / target_resume_id / context_confidence
  / needs_clarification / reason（+ jd_in_message / raw_jd / candidates / missing_context）。

六条规则：
1. 用户已经粘贴完整 JD 时，不得要求重新录入岗位；
2. 用户提到公司和岗位时，优先查找已有 mission；
3. 数据库找不到岗位时，使用本轮 JD 作为临时岗位上下文继续回答；
4. 相同公司有多个岗位时，列出候选，不要随机选择；
5. 用户说「我的简历」时，优先使用当前 mission 绑定的 target resume；
6. 没有岗位版简历时，明确提示「当前岗位没有绑定岗位版简历」，但继续用已确认个人资料和本轮 JD 工作。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .company_aliases import canonical_company

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

INTENTS = (
    "INTERVIEW_PREP",
    "MOCK_INTERVIEW",
    "QUESTION_BANK",
    "RESUME_MATCH",
    "JOB_LOOKUP",
    "GENERAL_CAREER",
)

CONFIDENCE_EXPLICIT_MISSION = 0.95
CONFIDENCE_JD_ONLY = 0.75
CONFIDENCE_COMPANY_ONLY = 0.6
CONFIDENCE_AMBIGUOUS = 0.35
CONFIDENCE_NONE = 0.2

_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "MOCK_INTERVIEW": ("模拟面试", "模拟一下", "面试演练", "陪我练", "模拟一轮", "mock", "mock interview"),
    "QUESTION_BANK": ("题库", "面经题", "真题", "常见问题", "面试题", "列出问题", "出题", "问题清单"),
    "RESUME_MATCH": ("简历匹配", "简历和岗位", "简历对不对", "匹配度", "简历改成", "改简历", "优化简历", "简历怎么改"),
    "INTERVIEW_PREP": (
        "面试准备", "准备面试", "要面试", "面试怎么准备", "面试", "面试官", "面试题怎么答",
        "面试问题", "面试攻略", "一面", "二面", "三面", "hr面", "终面", "群面",
    ),
    "JOB_LOOKUP": ("岗位", "jd", "职位", "招聘", "这个岗", "什么要求", "招什么"),
}

_CRASH_PREP_KEYWORDS = (
    "今天", "今晚", "马上", "待会", "等下", "一小时后", "一个小时后", "半小时后",
    "下午", "明天一早", "明天早上", "紧急",
)

_JD_SIGNAL_RE = re.compile(
    r"(岗位职责|工作职责|职位描述|任职要求|任职资格|岗位要求|我们希望你|职位要求|工作内容|"
    r"岗位描述|Job Description|Responsibilities|Requirements|你需要做|你将负责)",
    re.IGNORECASE,
)

_COMPANY_LINE_RE = re.compile(r"(?:公司名称|公司|招聘方|Company)\s*[:：]\s*([^\n，,。;；]{2,40})")
_ROLE_LINE_RE = re.compile(
    r"(?:岗位名称|职位名称|招聘岗位|岗位|职位|应聘岗位|Role|Position)\s*[:：]\s*([^\n，,。;；]{2,40})"
)
_ROLE_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z]{2,14}(?:工程师|架构师|经理|主管|专员|总监|实习生|分析师|设计师|"
    r"产品经理|运营|开发|测试|算法|研发|研究员|顾问|助理))"
)
# 拉丁字母公司名（如 ByteDance / Google），用于「帮我准备 X 的面试」这类句式。
_EN_COMPANY_RE = re.compile(r"\b([A-Z][A-Za-z0-9&.\-]{2,})\b")
_EN_STOPWORDS = {"JD", "AI", "HR", "CEO", "SQL", "PPT", "OK", "I", "The", "A"}


@dataclass
class ResolvedContext:
    intent: str
    company: str | None = None
    role: str | None = None
    mission_id: str | None = None
    target_resume_id: str | None = None
    context_confidence: float = CONFIDENCE_NONE
    needs_clarification: bool = False
    reason: str = ""
    jd_in_message: bool = False
    raw_jd: str | None = None
    candidates: list[dict] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    crash_prep: bool = False
    route: str | None = None

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "company": self.company,
            "role": self.role,
            "mission_id": self.mission_id,
            "target_resume_id": self.target_resume_id,
            "context_confidence": self.context_confidence,
            "needs_clarification": self.needs_clarification,
            "reason": self.reason,
            "jd_in_message": self.jd_in_message,
            "raw_jd": self.raw_jd,
            "candidates": self.candidates,
            "missing_context": self.missing_context,
            "crash_prep": self.crash_prep,
            "route": self.route,
        }


# ---------------------------------------------------------------------------
# 纯函数判定
# ---------------------------------------------------------------------------


def looks_like_jd(text: str) -> bool:
    """粗判用户是否粘贴了完整 JD（规则 1：已粘贴就不要再要求重新录入岗位）。"""
    body = (text or "")
    if len(body) < 80:
        return False
    signals = len(_JD_SIGNAL_RE.findall(body))
    bullet_lines = sum(1 for line in body.splitlines() if line.strip().startswith(("·", "-", "•", "*", "1.", "2.", "3.")))
    return signals >= 1 and (len(body) >= 200 or bullet_lines >= 4)


def detect_intent(text: str, *, route: str | None = None) -> str:
    body = (text or "").casefold()
    # 简历 + 匹配/优化：优先判为 RESUME_MATCH（避免被泛化的「岗位」抢走）。
    if "简历" in body and any(word in body for word in ("匹配", "改", "优化", "对不对", "合适")):
        return "RESUME_MATCH"
    for intent in ("MOCK_INTERVIEW", "QUESTION_BANK", "RESUME_MATCH", "INTERVIEW_PREP", "JOB_LOOKUP"):
        if any(keyword in body for keyword in _INTENT_KEYWORDS[intent]):
            return intent
    if route and "interview" in route.casefold():
        return "INTERVIEW_PREP"
    return "GENERAL_CAREER"


def is_crash_prep(text: str) -> bool:
    """短时准备模式：用户说「今天/今晚/马上要面试」。"""
    body = (text or "").casefold()
    if "面试" not in body:
        return False
    return any(keyword in body for keyword in _CRASH_PREP_KEYWORDS)


def _looks_like_company_name(line: str) -> bool:
    """JD 首行是否像公司名（避免把「帮我准备面试」当成公司）。"""
    text = (line or "").strip()
    if not (2 <= len(text) <= 24):
        return False
    if any(word in text for word in ("帮", "请", "想", "要", "准备", "面试", "岗位", "职位", "简历", "分析", "看看")):
        return False
    if _JD_SIGNAL_RE.search(text):
        return False
    return True


def extract_identity_from_text(text: str) -> tuple[str | None, str | None]:
    """从文本里轻量抽取公司 / 岗位名（不编造：抽不到就返回 None）。"""
    body = (text or "")
    company = None
    role = None
    hit = _COMPANY_LINE_RE.search(body)
    if hit:
        company = hit.group(1).strip()
    hit = _ROLE_LINE_RE.search(body)
    if hit:
        role = hit.group(1).strip()
    if role is None:
        hit = _ROLE_SUFFIX_RE.search(body)
        if hit:
            role = hit.group(1).strip()
    if company is None:
        for match in _EN_COMPANY_RE.finditer(body):
            candidate = match.group(1)
            if candidate in _EN_STOPWORDS:
                continue
            company = candidate
            break
    return company, role


# ---------------------------------------------------------------------------
# 主解析
# ---------------------------------------------------------------------------


def _profile_missions(db: Session, profile_id: UUID | None) -> list[models.JobMission]:
    if profile_id is None:
        return []
    return list(
        db.scalars(
            select(models.JobMission)
            .where(models.JobMission.profile_id == profile_id, models.JobMission.status != "ARCHIVED")
            .order_by(models.JobMission.updated_at.desc())
        ).all()
    )


def _match_company(mission_company: str | None, wanted: str | None) -> bool:
    if not wanted:
        return False
    mc = canonical_company(mission_company)
    wc = canonical_company(wanted)
    if not mc or not wc:
        return False
    return mc == wc or mc in wc or wc in mc


def _latest_target_resume(db: Session, mission_id: UUID) -> models.TargetResume | None:
    rows = list(
        db.scalars(
            select(models.TargetResume)
            .where(models.TargetResume.mission_id == mission_id)
            .order_by(models.TargetResume.version.desc())
        ).all()
    )
    if not rows:
        return None
    for row in rows:
        if (row.status or "").upper() == "CONFIRMED":
            return row
    return rows[0]


def resolve_interview_context(
    db: Session,
    *,
    message: str,
    route: str | None = None,
    mission_id: str | None = None,
    target_resume_id: str | None = None,
    profile_id: str | None = None,
    history: list[dict] | None = None,
) -> ResolvedContext:
    """把消息 + 页面上下文解析为结构化面试上下文。"""
    text = message or ""
    intent = detect_intent(text, route=route)
    crash = is_crash_prep(text)
    jd_in_message = looks_like_jd(text)
    if intent == "GENERAL_CAREER" and jd_in_message:
        # 直接粘贴完整 JD 且没给明确指令时，默认按面试准备处理（规则 1）。
        intent = "INTERVIEW_PREP"
    ctx = ResolvedContext(intent=intent, route=route, crash_prep=crash, jd_in_message=jd_in_message)

    profile_uuid: UUID | None = None
    if profile_id:
        try:
            profile_uuid = UUID(str(profile_id))
        except (ValueError, TypeError):
            profile_uuid = None

    # 显式传入的 mission / target resume 最高优先级（规则 3：页面已给上下文就别再问）。
    explicit_mission = None
    if mission_id:
        try:
            explicit_mission = db.get(models.JobMission, UUID(str(mission_id)))
        except (ValueError, TypeError):
            explicit_mission = None

    company_from_text, role_from_text = extract_identity_from_text(text)
    if jd_in_message and company_from_text is None and role_from_text is None:
        # 完整 JD 通常没有「公司：」行，尝试从首行拿公司名（严格判定，避免误取请求句）。
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines and _looks_like_company_name(lines[0]):
            company_from_text = lines[0]
        ctx.raw_jd = text

    missions = _profile_missions(db, profile_uuid)
    if not missions and explicit_mission is not None:
        missions = [explicit_mission]

    # ---- 1) 显式 mission_id ------------------------------------------------
    if explicit_mission is not None:
        ctx.mission_id = str(explicit_mission.id)
        ctx.company = explicit_mission.company or company_from_text
        ctx.role = explicit_mission.role or role_from_text
        ctx.context_confidence = CONFIDENCE_EXPLICIT_MISSION
        ctx.reason = "用户当前页面已绑定岗位，直接使用该岗位上下文。"
        ctx.target_resume_id = _resolve_target_resume_id(db, explicit_mission.id, target_resume_id)
        if ctx.target_resume_id is None:
            ctx.missing_context.append("target_resume")
            ctx.reason += " 当前岗位没有绑定岗位版简历，将继续使用已确认个人资料" + ("和本轮 JD。" if jd_in_message else "。")
        return ctx

    # ---- 2) 按公司 / 岗位匹配已有 mission ---------------------------------
    matched: list[models.JobMission] = []
    if company_from_text:
        matched = [m for m in missions if _match_company(m.company, company_from_text)]
    if not matched and role_from_text:
        matched = [m for m in missions if role_from_text and role_from_text in (m.role or "")]
    if not matched:
        # 退一步：在消息里直接找公司名字面命中
        folded = text.casefold()
        matched = [m for m in missions if (m.company or "").strip() and (m.company or "").strip().casefold() in folded]

    # 规则 4：同公司多岗位 → 列候选，不随机选。
    if len(matched) > 1:
        if role_from_text:
            narrowed = [m for m in matched if role_from_text in (m.role or "")]
            if len(narrowed) == 1:
                matched = narrowed
        if len(matched) > 1:
            ctx.candidates = [
                {"mission_id": str(m.id), "company": m.company, "role": m.role, "display_name": m.display_name}
                for m in matched
            ]
            ctx.company = company_from_text or matched[0].company
            ctx.context_confidence = CONFIDENCE_AMBIGUOUS
            ctx.needs_clarification = True
            ctx.reason = f"公司「{ctx.company}」下有多个岗位，需用户确认具体是哪一个。已列出候选，不随机选择。"
            if jd_in_message:
                ctx.raw_jd = text
            return ctx

    if len(matched) == 1:
        mission = matched[0]
        ctx.mission_id = str(mission.id)
        ctx.company = mission.company or company_from_text
        ctx.role = mission.role or role_from_text
        ctx.context_confidence = CONFIDENCE_JD_ONLY if jd_in_message else (CONFIDENCE_COMPANY_ONLY if company_from_text else CONFIDENCE_COMPANY_ONLY)
        ctx.reason = "根据用户提到的公司/岗位匹配到已有岗位。" + ("同时在消息中检测到完整 JD，以消息内 JD 为准。" if jd_in_message else "")
        ctx.target_resume_id = _resolve_target_resume_id(db, mission.id, target_resume_id)
        if ctx.target_resume_id is None:
            ctx.missing_context.append("target_resume")
            ctx.reason += " 该岗位没有绑定岗位版简历，继续使用已确认个人资料。"
        return ctx

    # ---- 3) 找不到 mission → 用本轮 JD 作为临时上下文继续 ----------------
    ctx.company = company_from_text
    ctx.role = role_from_text
    if jd_in_message:
        ctx.raw_jd = text
        ctx.context_confidence = CONFIDENCE_JD_ONLY
        ctx.reason = "数据库中没有找到对应岗位；不要求重新录入，直接使用本轮粘贴的 JD 作为临时岗位上下文继续回答。"
        ctx.missing_context.append("mission")
        if target_resume_id:
            ctx.target_resume_id = target_resume_id
        else:
            ctx.missing_context.append("target_resume")
        return ctx

    if company_from_text or role_from_text:
        ctx.context_confidence = CONFIDENCE_COMPANY_ONLY
        ctx.reason = "只提到公司/岗位名称但未粘贴 JD，且数据库没有匹配岗位；需要用户补充 JD 或确认岗位。"
        ctx.needs_clarification = True
        ctx.missing_context.extend(["mission", "raw_jd"])
        return ctx

    # ---- 4) 没有任何岗位线索 ------------------------------------------------
    ctx.reason = "未检测到岗位线索，按通用求职问题处理。"
    ctx.context_confidence = CONFIDENCE_NONE
    if target_resume_id:
        ctx.target_resume_id = target_resume_id
    return ctx


def _resolve_target_resume_id(db: Session, mission_uuid: UUID, explicit: str | None) -> str | None:
    """规则 5：用户说「我的简历」→ 优先 mission 绑定的 target resume。"""
    if explicit:
        row = db.get(models.TargetResume, _safe_uuid(explicit))
        if row is not None and row.mission_id == mission_uuid:
            return str(row.id)
    row = _latest_target_resume(db, mission_uuid)
    return str(row.id) if row is not None else None


def _safe_uuid(value: str) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


__all__ = [
    "INTENTS",
    "ResolvedContext",
    "resolve_interview_context",
    "looks_like_jd",
    "detect_intent",
    "is_crash_prep",
    "extract_identity_from_text",
]
