"""第四 / 五阶段：面试准备 Agent 的固定流程状态机 + CRASH_PREP 短时准备模式。

不让模型自由决定所有步骤——后端用明确的状态机（``PIPELINE_STEPS``）控制每一步
及其所需工具/数据；数据缺失时把该步标为 ``BLOCKED`` 并给出降级说明，而不是中断。

CRASH_PREP：用户说「今天/今晚/马上要面试」时进入短时准备模式，输出固定 8 段结构。
所有内容都只来自真实上下文（JD 要点 / 岗位版简历 / 已确认事实 / 真实面经），
不编造；缺失的部分标注为「需补强」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODE_FULL_PREP = "FULL_PREP"
MODE_CRASH_PREP = "CRASH_PREP"


@dataclass(frozen=True)
class PipelineStep:
    key: str
    title: str
    tool: str | None
    needs: tuple[str, ...]
    produces: str


PIPELINE_STEPS: tuple[PipelineStep, ...] = (
    PipelineStep("CONTEXT_RESOLVER", "上下文解析", None, (), "intent/company/role/mission_id/target_resume_id/confidence"),
    PipelineStep("MISSION_CONTEXT_LOADER", "岗位上下文加载", "get_mission_context", ("mission_or_jd",), "raw_jd/parsed_requirements/what_matters"),
    PipelineStep("JD_SCREENING_STRATEGIST", "JD 筛选策略", "get_mission_context", ("raw_jd",), "这份 JD 真正在筛什么"),
    PipelineStep("RESUME_EVIDENCE_SELECTOR", "简历证据选择", "get_target_resume_context", ("target_resume_or_claims",), "最该讲 / 不要主动讲的经历"),
    PipelineStep("INTERVIEW_PREPARATION_PLANNER", "准备计划", None, ("target_resume_or_claims",), "准备计划"),
    PipelineStep("QUESTION_COACH", "问题教练", "get_interview_intel_context", ("raw_jd",), "高优先级问题清单"),
    PipelineStep("ANSWER_EVALUATOR", "回答评估", None, ("target_resume_or_claims",), "回答评估维度"),
    PipelineStep("RESUME_FEEDBACK_WRITER", "简历反馈", "get_confirmed_claims_context", ("target_resume_or_claims",), "简历优化建议"),
)

# CRASH_PREP 的 8 段固定输出结构。
CRASH_PREP_SECTIONS: tuple[str, ...] = (
    "这份 JD 真正在筛什么",
    "从我的简历中最应该讲哪 3 段经历",
    "哪些经历不要主动讲",
    "60 分钟准备计划",
    "5 道最高优先级问题",
    "每道题对应的真实经历和证据",
    "CEO/HR 反问问题",
    "立即开始第一道模拟题",
)


def _requirements_text(ctx: dict) -> list[str]:
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


def _verified_experiences(ctx: dict) -> list[dict]:
    target = ctx.get("target_resume") or {}
    return list(target.get("relevant_experiences") or [])


def _needs_confirmation(ctx: dict) -> list[dict]:
    target = ctx.get("target_resume") or {}
    return list(target.get("needs_confirmation") or [])


def _screening_focus(ctx: dict) -> list[dict]:
    """这份 JD 真正在筛什么——只用真实 JD 要点，无要点则标注缺失。"""
    reqs = _requirements_text(ctx)
    if not reqs:
        return [
            {
                "focus": None,
                "grounding": "MISSING",
                "note": "本轮没有可用的 JD 要点（既没有已保存岗位的解析结果，也没有可解析的本轮 JD）。",
            }
        ]
    return [{"focus": text, "grounding": "JD"} for text in reqs[:8]]


def _priority_questions(ctx: dict) -> list[dict]:
    """高优先级问题：优先用真实面经里出现过的题，其次由 JD 要点改写成问题。"""
    intel = ctx.get("interview_intel") or {}
    questions: list[dict] = []
    for item in intel.get("items") or []:
        for q in item.get("questions") or []:
            question = (q.get("question") or "").strip()
            if question:
                questions.append(
                    {
                        "question": question,
                        "why_asked": (q.get("why") or "").strip() or "来自真实面经信号。",
                        "source": "REAL_INTERVIEW",
                        "topic": item.get("topic"),
                    }
                )
    if questions:
        return questions[:5]
    for req in _requirements_text(ctx)[:5]:
        questions.append(
            {
                "question": f"请结合你的经历说明：你如何满足「{req}」？",
                "why_asked": f"对应 JD 要求：{req}",
                "source": "JD_DERIVED",
                "topic": None,
            }
        )
    return questions


def _not_to_say(ctx: dict) -> list[dict]:
    """哪些经历不要主动讲：来自需要确认的条目 + 服务型/无关经历。"""
    out: list[dict] = []
    for item in _needs_confirmation(ctx):
        out.append(
            {
                "text": item.get("bullet_text"),
                "reason": "该条目缺少证据（evidence_refs），未确认前不要当作已完成事实主动讲。",
                "grounding": "NEEDS_CONFIRMATION",
            }
        )
    from .mission_interview_context import _SERVICE_EXPERIENCE_TYPES

    for exp in _all_profile_experiences(ctx):
        if str(exp.get("experience_type") or "").upper() in _SERVICE_EXPERIENCE_TYPES:
            out.append(
                {
                    "text": f"{exp.get('title')} @ {exp.get('organization')}",
                    "reason": "服务型/与目标岗位无关，主动讲会稀释主线，非必要不展开。",
                    "grounding": "OMIT_SUGGESTED",
                }
            )
    return out


def _all_profile_experiences(ctx: dict) -> list[dict]:
    """该档案下的全部经历（含服务型），用于判断「哪些不要主动讲」。"""
    return list(ctx.get("all_experiences") or [])


def _all_profile_experiences(ctx: dict) -> list[dict]:
    # relevant_experiences 已在构建时过滤掉服务型，这里补充说明来源。
    return list(ctx.get("all_experiences") or [])


def _crash_plan(ctx: dict) -> list[dict]:
    """60 分钟准备计划（面向「今天就要面试」的短时高强度安排）。"""
    has_intel = bool((ctx.get("interview_intel") or {}).get("has_intel"))
    return [
        {"minutes": 5, "task": "读一遍这份 JD 的筛选重点（上面第 1 段），圈出 3 个最高频要求。"},
        {"minutes": 15, "task": "把最该讲的 3 段经历，各写成 STAR 骨架（情境/任务/动作/结果），只写真实数据。"},
        {"minutes": 15, "task": "针对 5 道高优先级问题，各口述一遍，卡住的地方回去补证据。"},
        {"minutes": 10, "task": "准备 CEO/HR 反问问题（下面第 7 段），挑 2 个最想知道的。"},
        {"minutes": 10, "task": "从第 8 段开始，直接做一道模拟题，按回答评估维度自查。"},
        {"minutes": 5, "task": "复盘：确认没有任何「没证据的数字」会脱口而出。" if has_intel else "复盘：确认只使用已确认事实，未确认内容不主动展开。"},
    ]


def _evidence_for_question(question: dict, ctx: dict) -> dict:
    """为每道题配真实经历与证据；无证据则明确标注缺失，不编造。"""
    verified = _verified_experiences(ctx)
    evidence = []
    for item in verified[:3]:
        evidence.append(
            {
                "bullet_text": item.get("bullet_text"),
                "source_experience_id": item.get("source_experience_id"),
                "claim_status": item.get("claim_status"),
                "evidence_refs": item.get("evidence_refs") or [],
            }
        )
    if not evidence:
        return {
            "question": question.get("question"),
            "evidence": [],
            "grounding": "NEEDS_CONFIRMATION",
            "note": "当前没有带证据的已确认经历可支撑这道题；请先确认相关经历（事实台账 / 岗位简历）再作答。",
        }
    return {"question": question.get("question"), "evidence": evidence, "grounding": "VERIFIED"}


def _reverse_questions(ctx: dict) -> list[dict]:
    """CEO/HR 反问问题：基于真实 JD 要点与公司生成，不编造。"""
    company = ctx.get("company") or "贵公司"
    reqs = _requirements_text(ctx)
    questions = [
        {"audience": "HR", "question": f"这个岗位目前在团队里最希望 3 个月内解决的核心问题是什么？（{company}）"},
        {"audience": "HR", "question": "团队的绩效评估与晋升节奏是怎样的？"},
        {"audience": "CEO", "question": "从业务视角看，这个岗位做得好与做得一般，差别体现在哪里？"},
    ]
    if reqs:
        questions.insert(
            0,
            {"audience": "HR", "question": f"JD 里「{reqs[0]}」目前团队的实际成熟度如何？我会接手到什么程度？"},
        )
    return questions[:5]


def plan_interview_prep(resolved: dict, ctx: dict) -> dict:
    """按固定状态机生成准备方案；``ctx`` 是 ``build_mission_interview_context`` 的输出。"""
    mode = MODE_CRASH_PREP if resolved.get("crash_prep") else MODE_FULL_PREP
    missing = list(ctx.get("missing_context") or [])

    steps: list[dict] = []
    blocked: list[str] = []
    for step in PIPELINE_STEPS:
        status = "READY"
        reasons: list[str] = []
        for need in step.needs:
            if need == "mission_or_jd" and "mission" in missing and not ctx.get("raw_jd"):
                status = "BLOCKED"
                reasons.append("既没有已保存岗位，也没有本轮 JD。")
            if need == "raw_jd" and not ctx.get("raw_jd") and "raw_jd" in missing:
                status = "DEGRADED"
                reasons.append("缺少 JD 原文，筛选重点将由已保存的解析结果或用户补充。")
            if need == "target_resume_or_claims" and not ctx.get("target_resume"):
                status = "DEGRADED"
                reasons.append("当前岗位没有绑定岗位版简历，改用已确认个人资料与已确认事实。")
        steps.append(
            {
                "step": step.key,
                "title": step.title,
                "tool": step.tool,
                "status": status,
                "reasons": reasons,
                "produces": step.produces,
            }
        )
        if status == "BLOCKED":
            blocked.append(step.key)

    # 8 段 CRASH_PREP 输出结构；FULL_PREP 也复用同一结构（更详尽）。
    questions = _priority_questions(ctx)
    sections: list[dict] = [
        {"key": "screening", "title": CRASH_PREP_SECTIONS[0], "items": _screening_focus(ctx)},
        {
            "key": "must_tell_experiences",
            "title": CRASH_PREP_SECTIONS[1],
            "items": [
                {
                    "text": item.get("bullet_text"),
                    "source_experience_id": item.get("source_experience_id"),
                    "evidence_refs": item.get("evidence_refs") or [],
                }
                for item in _verified_experiences(ctx)[:3]
            ],
            "grounding": "VERIFIED" if _verified_experiences(ctx) else "NEEDS_CONFIRMATION",
            "note": None if _verified_experiences(ctx) else "没有带证据的已确认经历，请先在事实台账/岗位简历里确认。",
        },
        {"key": "avoid", "title": CRASH_PREP_SECTIONS[2], "items": _not_to_say(ctx)},
        {"key": "plan", "title": CRASH_PREP_SECTIONS[3], "items": _crash_plan(ctx)},
        {"key": "questions", "title": CRASH_PREP_SECTIONS[4], "items": questions},
        {
            "key": "question_evidence",
            "title": CRASH_PREP_SECTIONS[5],
            "items": [_evidence_for_question(q, ctx) for q in questions],
        },
        {"key": "reverse_questions", "title": CRASH_PREP_SECTIONS[6], "items": _reverse_questions(ctx)},
        {
            "key": "mock_start",
            "title": CRASH_PREP_SECTIONS[7],
            "items": [
                {
                    "question": (questions[0]["question"] if questions else None),
                    "instruction": "请直接口述你的回答，我会按回答评估维度（覆盖度/证据/缺失证据/未支撑主张/JD 对齐/追问/改进建议）给出反馈。",
                }
            ],
        },
    ]

    grounding_note = (
        "全部内容只用本轮 JD、岗位版简历、已确认事实与真实面经；未确认的内容已标注「待确认」，不编造。"
    )

    return {
        "mode": mode,
        "steps": steps,
        "blocked_steps": blocked,
        "sections": sections,
        "missing_context": missing,
        "grounding_note": grounding_note,
        "question_count": len(questions),
    }


__all__ = [
    "MODE_FULL_PREP",
    "MODE_CRASH_PREP",
    "PIPELINE_STEPS",
    "CRASH_PREP_SECTIONS",
    "plan_interview_prep",
]
