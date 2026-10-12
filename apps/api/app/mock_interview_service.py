"""第七阶段：任务级模拟面试（围绕岗位版简历 + 已确认事实，逐轮追问与评分）。

每一轮：
1. 只显示问题；
2. 用户回答；
3. 识别回答是否使用真实证据；
4. 识别是否遗漏关键要求；
5. 根据当前回答生成追问（**针对刚刚的回答**，不是重复第一轮问题）；
6. 最后一轮再给整体报告。

回答评估固定包含：
answer_coverage / evidence_status / missing_evidence / unsupported_claims /
jd_alignment / next_followup / improvement_tip

硬约束：不能把未经确认的内容补写成标准答案；参考答案只能使用 confirmed claims
与已确认 target resume。
"""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

INTERVIEW_TYPES = {"TECHNICAL", "BEHAVIORAL", "HR", "MANAGER", "MIXED"}
DIFFICULTIES = {"EASY", "MEDIUM", "HARD"}
EVIDENCE_VERIFIED = "VERIFIED"
EVIDENCE_PARTIAL = "PARTIAL"
EVIDENCE_UNSUPPORTED = "UNSUPPORTED"

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}|[\u4e00-\u9fa5]{2,}")


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text or "")}


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------


def _context(db: Session, profile_id: UUID, mission_id: UUID | None, target_resume_id: UUID | None, raw_jd: str | None) -> dict:
    from .mission_interview_context import build_mission_interview_context

    return build_mission_interview_context(
        db,
        profile_id=profile_id,
        mission_id=mission_id,
        target_resume_id=target_resume_id,
        raw_jd=raw_jd,
    )


def _requirement_texts(ctx: dict) -> list[str]:
    out: list[str] = []
    for item in ctx.get("parsed_requirements") or []:
        if isinstance(item, dict):
            text = item.get("text") or item.get("summary") or item.get("requirement") or item.get("name")
            if text:
                out.append(str(text))
        elif isinstance(item, str) and item.strip():
            out.append(item.strip())
    what = ctx.get("what_matters") or {}
    for key in ("must_have", "screening", "requirements"):
        value = what.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("summary") or item.get("requirement")
                    if text:
                        out.append(str(text))
                elif isinstance(item, str) and item.strip():
                    out.append(item.strip())
    return list(dict.fromkeys(out))


def _evidence_pool(ctx: dict) -> tuple[list[dict], list[dict]]:
    target = ctx.get("target_resume") or {}
    verified = list(target.get("relevant_experiences") or [])
    unverified = list(target.get("needs_confirmation") or [])
    claims = (ctx.get("confirmed_claims") or {}).get("confirmed_claims") or []
    for claim in claims:
        verified.append({"bullet_text": claim.get("claim"), "evidence_refs": claim.get("evidence_refs") or []})
    needs = (ctx.get("confirmed_claims") or {}).get("needs_confirmation") or []
    for claim in needs:
        unverified.append({"bullet_text": claim.get("claim"), "evidence_refs": []})
    return verified, unverified


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------


def start_mock_interview(
    db: Session,
    profile_id: UUID,
    *,
    mission_id: UUID | None = None,
    target_resume_id: UUID | None = None,
    interview_type: str = "TECHNICAL",
    difficulty: str = "MEDIUM",
    interviewer_style: str | None = None,
    rounds: int = 3,
    raw_jd: str | None = None,
) -> models.MockInterviewSession:
    _profile(db, profile_id)
    itype = (interview_type or "TECHNICAL").upper()
    if itype not in INTERVIEW_TYPES:
        raise HTTPException(status_code=422, detail=f"面试类型必须是 {sorted(INTERVIEW_TYPES)} 之一")
    diff = (difficulty or "MEDIUM").upper()
    if diff not in DIFFICULTIES:
        raise HTTPException(status_code=422, detail=f"难度必须是 {sorted(DIFFICULTIES)} 之一")
    total_rounds = max(1, min(10, int(rounds or 3)))

    ctx = _context(db, profile_id, mission_id, target_resume_id, raw_jd)
    session = models.MockInterviewSession(
        profile_id=profile_id,
        mission_id=mission_id,
        target_resume_id=target_resume_id,
        interview_type=itype,
        difficulty=diff,
        interviewer_style=(interviewer_style or None),
        rounds=total_rounds,
        current_round=0,
        status="ACTIVE",
        config={
            "mission_id": str(mission_id) if mission_id else None,
            "target_resume_id": str(target_resume_id) if target_resume_id else None,
            "interview_type": itype,
            "difficulty": diff,
            "interviewer_style": interviewer_style,
            "rounds": total_rounds,
            "missing_context": ctx.get("missing_context") or [],
        },
    )
    db.add(session)
    db.flush()

    first = _next_question(ctx, asked=[], round_number=1, interview_type=itype, difficulty=diff)
    db.add(
        models.MockInterviewTurn(
            session_id=session.id,
            round_number=1,
            question=first["question"],
            question_source=first["source"],
        )
    )
    session.current_round = 1
    db.commit()
    db.refresh(session)
    return session


def _next_question(
    ctx: dict,
    *,
    asked: list[str],
    round_number: int,
    interview_type: str,
    difficulty: str,
    focus: str | None = None,
    answer_snippet: str | None = None,
) -> dict:
    """生成下一题：优先真实面经，其次由 JD 要求 / 已确认经历派生。绝不重复已问。"""
    asked_norm = {_normalize(q) for q in asked}

    candidates: list[dict] = []
    intel = ctx.get("interview_intel") or {}
    for item in intel.get("items") or []:
        for q in item.get("questions") or []:
            question = (q.get("question") or "").strip()
            if question:
                candidates.append({"question": question, "source": "REAL_INTERVIEW"})
    for req in _requirement_texts(ctx):
        candidates.append({"question": f"请结合你的经历说明：你如何满足「{req}」？", "source": "JD_DERIVED"})
    verified, _ = _evidence_pool(ctx)
    for item in verified[:4]:
        text = (item.get("bullet_text") or "").strip()
        if text:
            candidates.append({"question": f"简历里写到「{text[:40]}…」，请展开讲讲背景、你的动作和结果。", "source": "RESUME_DEEP_DIVE"})

    # 追问必须针对用户刚刚的回答：先把回答片段带进问题里。
    prefix = f"你刚才提到「{answer_snippet}」。" if answer_snippet else "接着刚才的回答："
    if focus:
        candidates.insert(0, {"question": f"{prefix}请具体说明你如何满足「{focus}」？", "source": "FOLLOWUP"})
    elif answer_snippet:
        candidates.insert(
            0,
            {
                "question": f"{prefix}能举一个具体例子，说明你个人的动作和可验证的结果吗？",
                "source": "FOLLOWUP",
            },
        )

    for candidate in candidates:
        if _normalize(candidate["question"]) not in asked_norm:
            return candidate
    return {
        "question": "请用 2 分钟做一个与这个岗位最相关的自我介绍。",
        "source": "GENERIC",
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "")).casefold()


# ---------------------------------------------------------------------------
# 回答评估（第七阶段核心）
# ---------------------------------------------------------------------------


def evaluate_answer(answer: str, *, ctx: dict) -> dict:
    """评估一次回答：覆盖度 / 证据状态 / 缺失证据 / 未支撑主张 / JD 对齐 / 追问 / 改进建议。"""
    body = (answer or "").strip()
    answer_tokens = _tokens(body)
    numbers = set(_NUMBER_RE.findall(body))

    requirements = _requirement_texts(ctx)
    verified, unverified = _evidence_pool(ctx)

    # 1) 覆盖度：回答命中了哪些 JD 要求
    covered: list[str] = []
    missing: list[str] = []
    for req in requirements:
        req_tokens = _tokens(req)
        overlap = req_tokens & answer_tokens
        if overlap and len(overlap) >= max(1, len(req_tokens) // 3):
            covered.append(req)
        else:
            missing.append(req)

    # 2) 证据状态：回答里有没有用真实（带证据）的经历
    verified_text = " ".join((item.get("bullet_text") or "") for item in verified)
    unverified_text = " ".join((item.get("bullet_text") or "") for item in unverified)
    verified_tokens = _tokens(verified_text)
    unverified_tokens = _tokens(unverified_text)
    hit_verified = bool(verified_tokens & answer_tokens)
    hit_unverified = bool(unverified_tokens & answer_tokens)
    if hit_verified:
        evidence_status = EVIDENCE_VERIFIED
    elif hit_unverified:
        evidence_status = EVIDENCE_PARTIAL
    else:
        evidence_status = EVIDENCE_UNSUPPORTED

    # 3) 未支撑主张：回答中出现、但证据池里没有的数字（不得编造）
    evidence_numbers = set(_NUMBER_RE.findall(verified_text)) | set(_NUMBER_RE.findall(unverified_text))
    unsupported_claims: list[dict] = []
    for number in sorted(numbers - evidence_numbers):
        unsupported_claims.append({"kind": "UNSUPPORTED_NUMBER", "value": number})

    # 4) JD 对齐：覆盖比例
    jd_alignment = round(len(covered) / len(requirements), 2) if requirements else None

    # 5) 下一轮追问：针对刚刚的回答 + 未覆盖的最关键要求
    snippet = _snippet(body)
    if missing:
        next_followup = f"你刚才提到「{snippet}」。JD 还要求「{missing[0]}」，请具体说明你在这方面的真实经历和结果。"
    elif evidence_status == EVIDENCE_UNSUPPORTED:
        next_followup = f"你刚才提到「{snippet}」，能不能给出一个具体例子，说明你个人的动作和可验证的结果？"
    elif unsupported_claims:
        next_followup = f"你刚才提到「{snippet}」，其中的 {unsupported_claims[0]['value']} 是怎么得到的？请说明口径。"
    else:
        next_followup = f"你刚才提到「{snippet}」，如果面试官继续深挖，你觉得最容易被问住的点是什么？"

    # 6) 改进建议
    tips: list[str] = []
    if missing:
        tips.append(f"补充与「{missing[0]}」相关的真实经历（STAR 结构），这正是本次没覆盖到的 JD 要求。")
    if evidence_status != EVIDENCE_VERIFIED:
        tips.append("回答里尽量落到已确认的岗位简历要点上；没有证据的内容标注为待确认，不要当作已完成事实。")
    if unsupported_claims:
        tips.append("核对数字口径：回答中的数字必须能在已确认事实里找到依据。")
    if not tips:
        tips.append("结构完整、证据清楚。可以再压缩开场、把结果提前，让面试官更快抓到重点。")

    return {
        "answer_coverage": covered,
        "missing_requirements": missing,
        "evidence_status": evidence_status,
        "missing_evidence": missing,
        "unsupported_claims": unsupported_claims,
        "jd_alignment": jd_alignment,
        "next_followup": next_followup,
        "improvement_tip": " ".join(tips),
    }


def _snippet(text: str, limit: int = 24) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return "（未作答）"
    return clean[:limit] + ("…" if len(clean) > limit else "")


# ---------------------------------------------------------------------------
# 提交流程
# ---------------------------------------------------------------------------


def get_session(db: Session, session_id: UUID) -> models.MockInterviewSession:
    row = db.get(models.MockInterviewSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    return row


def submit_answer(db: Session, session_id: UUID, *, answer: str) -> models.MockInterviewSession:
    session = get_session(db, session_id)
    if session.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="该模拟面试已结束。")
    current = next(
        (turn for turn in session.turns if turn.round_number == session.current_round and not turn.answer),
        None,
    )
    if current is None:
        current = max(session.turns, key=lambda t: t.round_number, default=None)
        if current is None:
            raise HTTPException(status_code=409, detail="会话没有待回答的问题。")

    ctx = _context(db, session.profile_id, session.mission_id, session.target_resume_id, None)
    evaluation = evaluate_answer(answer, ctx=ctx)
    current.answer = answer
    current.evaluation = evaluation

    round_number = current.round_number
    if round_number < session.rounds:
        asked = [turn.question for turn in session.turns]
        followup_focus = evaluation["missing_requirements"][0] if evaluation["missing_requirements"] else None
        nxt = _next_question(
            ctx,
            asked=asked,
            round_number=round_number + 1,
            interview_type=session.interview_type,
            difficulty=session.difficulty,
            focus=followup_focus,
            answer_snippet=_snippet(answer),
        )
        db.add(
            models.MockInterviewTurn(
                session_id=session.id,
                round_number=round_number + 1,
                question=nxt["question"],
                question_source=nxt["source"],
            )
        )
        session.current_round = round_number + 1
    else:
        session.status = "COMPLETED"
        session.report = build_overall_report(session)

    db.commit()
    db.refresh(session)
    return session


def build_overall_report(session: models.MockInterviewSession) -> dict:
    """最后一轮才给整体报告：汇总各轮评估，均来自真实回答。"""
    answers = [turn for turn in session.turns if turn.answer]
    evidence_counts = {EVIDENCE_VERIFIED: 0, EVIDENCE_PARTIAL: 0, EVIDENCE_UNSUPPORTED: 0}
    all_missing: list[str] = []
    all_unsupported: list[dict] = []
    alignments: list[float] = []
    for turn in answers:
        ev = turn.evaluation or {}
        evidence_counts[ev.get("evidence_status", EVIDENCE_UNSUPPORTED)] = evidence_counts.get(
            ev.get("evidence_status", EVIDENCE_UNSUPPORTED), 0
        ) + 1
        all_missing.extend(ev.get("missing_requirements") or [])
        all_unsupported.extend(ev.get("unsupported_claims") or [])
        if isinstance(ev.get("jd_alignment"), (int, float)):
            alignments.append(float(ev["jd_alignment"]))
    return {
        "rounds_answered": len(answers),
        "evidence_summary": evidence_counts,
        "average_jd_alignment": round(sum(alignments) / len(alignments), 2) if alignments else None,
        "recurring_missing_requirements": list(dict.fromkeys(all_missing)),
        "unsupported_claims": all_unsupported,
        "note": "整体报告只基于你本轮的逐题回答与已确认事实；未确认内容不作为结论。",
    }


def turn_read(turn: models.MockInterviewTurn) -> dict:
    return {
        "id": str(turn.id),
        "round_number": turn.round_number,
        "question": turn.question,
        "question_source": turn.question_source,
        "answer": turn.answer,
        "evaluation": turn.evaluation or {},
    }


def session_read(session: models.MockInterviewSession) -> dict:
    turns = sorted(session.turns or [], key=lambda t: t.round_number)
    return {
        "id": str(session.id),
        "profile_id": str(session.profile_id),
        "mission_id": str(session.mission_id) if session.mission_id else None,
        "target_resume_id": str(session.target_resume_id) if session.target_resume_id else None,
        "interview_type": session.interview_type,
        "difficulty": session.difficulty,
        "interviewer_style": session.interviewer_style,
        "rounds": session.rounds,
        "current_round": session.current_round,
        "status": session.status,
        "config": session.config or {},
        "report": session.report or {},
        "turns": [turn_read(turn) for turn in turns],
        "pending_question": next(
            (t.question for t in turns if t.round_number == session.current_round and not t.answer), None
        ),
    }


__all__ = [
    "INTERVIEW_TYPES",
    "DIFFICULTIES",
    "start_mock_interview",
    "submit_answer",
    "evaluate_answer",
    "build_overall_report",
    "get_session",
    "session_read",
    "turn_read",
]
