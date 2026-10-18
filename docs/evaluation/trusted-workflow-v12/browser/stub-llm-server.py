"""本地桩模型服务（OpenAI 兼容），仅供可信求职 v1.2 的浏览器 E2E 使用。

为什么需要它
------------
本轮改版要求「真实浏览器主流程」验收，而生成岗位简历、经历筛选、面试参考回答都要走模型。
真实模型调用属于**付费操作**，本轮未获授权，因此用一个本地桩替代：

- 不联网、不产生费用、可复现；
- 只返回**照抄源事实**的改写（不编造数字），保证流程能走通；
- 面试参考回答故意返回一段**含编造数字的第一人称作答**，用来验证 Sprint A 的事实闸门。

它验证的是「产品流程与前端行为」，**不是模型输出质量**——报告中如实标注。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

app = FastAPI(title="stub-llm")

CALLS: list[dict] = []


def _user_payload(messages: list[dict]) -> dict:
    for message in reversed(messages or []):
        if message.get("role") == "user":
            try:
                data = json.loads(message.get("content") or "{}")
                if isinstance(data, dict):
                    return data
            except (TypeError, ValueError):
                return {}
    return {}


def _system_prompt(messages: list[dict]) -> str:
    for message in messages or []:
        if message.get("role") == "system":
            return str(message.get("content") or "")
    return ""


def _first_lines(text: str, limit: int = 3) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()][:limit]


def _jd_extraction(payload: dict) -> dict:
    raw = str(payload.get("raw_text") or "")
    lines = _first_lines(raw, 6)
    company = "UNKNOWN"
    for line in lines:
        match = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,12})(?:公司|科技|科技有限|集团|Inc\.|Ltd)", line)
        if match:
            company = match.group(1)
            break
    role = "UNKNOWN"
    for line in lines:
        match = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,20}?(?:产品经理|产品实习生|数据分析|后端工程师|运营|设计师|实习生))", line)
        if match:
            role = match.group(1)
            break
    requirement_text = lines[1] if len(lines) > 1 else (lines[0] if lines else "具备基本的产品分析与文档能力")
    return {
        "company": company,
        "role": role,
        "role_family": "PRODUCT",
        "seniority": "INTERN",
        "location": "UNKNOWN",
        "education_requirements": [],
        "responsibilities": lines[:3],
        "requirements": [
            {
                "id": "req-1",
                "text": requirement_text,
                "category": "SKILL",
                "evidence_text": requirement_text[:200] if requirement_text in raw else "产品",
            }
        ],
        "preferred_requirements": [],
        "capabilities": ["产品分析"],
        "keywords": ["产品", "数据"],
    }


def _experience_selection(payload: dict) -> dict:
    facts = payload.get("profile_facts") or []
    selections = []
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict) or fact.get("kind") not in {"experience", "project"}:
            continue
        decision = "KEEP_AND_HIGHLIGHT" if index == 0 else "KEEP"
        selections.append({
            "experience_id": fact.get("id"),
            "decision": decision,
            "why": f"这段经历与岗位的「{str(fact.get('title') or '目标能力')}」直接相关，可在面试里展开讲具体做法。",
            "related_capabilities": ["产品分析"],
            "supporting_evidence_refs": [fact.get("id")] if fact.get("id") else [],
            "confidence": 0.7,
        })
    return {"selections": selections}


def _strategy(payload: dict) -> dict:
    facts = payload.get("profile_facts") or []
    order: list[str] = []
    guidance: list[dict] = []
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict) or fact.get("kind") not in {"experience", "project"}:
            continue
        order.append(str(fact.get("id")))
        guidance.append({
            "experience_id": fact.get("id"),
            "role_in_story": "主线经历" if index == 0 else "支撑经历",
            "what_to_highlight": ["真实职责与做法"],
            "what_to_avoid": ["编造数字", "夸大主导范围"],
            "target_capabilities": ["产品分析"],
            "evidence_refs": [fact.get("id")] if fact.get("id") else [],
            "interview_risk_notes": ["结果数据需要候选人自己确认"],
        })
    return {
        "positioning_statement": "围绕真实经历组织叙事，突出可核对的动作与方法。",
        "recommended_experience_order": order,
        "experience_guidance": guidance,
    }


def _target_resume(payload: dict) -> dict:
    """照抄源事实的改写：不新增数字、不新增工具、不新增结果。"""
    facts = payload.get("SOURCE_RESUME") or payload.get("GLOBAL_EVIDENCE") or []
    blocks: list[dict] = []
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("kind") not in {"experience", "project"}:
            continue
        original = str(fact.get("description") or fact.get("title") or "").strip()
        if not original:
            continue
        lines = [line.strip().removeprefix("• ").removeprefix("- ") for line in original.splitlines() if line.strip()]
        bullets = []
        for line in lines[:4]:
            bullets.append({
                "original_text": line,
                "suggested_text": f"改写框架：STAR（有完整过程）{line}",
                "why_changed": "照抄源事实，只调整表述以贴近岗位用语，未新增任何数字或结果。",
                "target_capabilities": ["产品分析"],
                "jd_evidence_refs": [],
                "evidence_refs": [fact.get("id")] if fact.get("id") else [],
                "resume_skill_refs": [],
                "grounding_status": "SUPPORTED",
                "risk_flags": [],
            })
        if not bullets:
            continue
        blocks.append({
            "source_experience_id": fact.get("id"),
            "display_name": str(fact.get("title") or "经历"),
            "role_in_resume": str(fact.get("title") or "经历"),
            "include": True,
            "bullets": bullets,
        })
    skills = [
        {"name": str(fact.get("name") or ""), "proficiency": str(fact.get("proficiency") or "")}
        for fact in facts
        if isinstance(fact, dict) and fact.get("kind") == "skill"
    ]
    return {
        "positioning_summary": "以真实经历为主线的岗位版简历。",
        "section_order": ["education", "experience", "skills", "certifications"],
        "experiences": blocks,
        "skills": skills,
        "excluded_suggestions": [],
    }


def _claims(payload: dict) -> dict:
    """照抄源事实生成「可面试主张」，不新增任何结果数字。"""
    facts = payload.get("profile_facts") or []
    claims = []
    for fact in facts:
        if not isinstance(fact, dict) or fact.get("kind") not in {"experience", "project"}:
            continue
        text = str(fact.get("description") or fact.get("title") or "").strip()
        if not text:
            continue
        claims.append({
            "claim": f"我做过「{str(fact.get('title') or '这个项目')}」，能讲清楚自己的具体动作。",
            "current_text": text[:400],
            "suggested_text": None,
            "reason": "源事实里就有这段描述，可直接讲。",
            "jd_relevance": "岗位要求能讲清真实项目过程。",
            "matched_capabilities": [],
            "evidence_refs": [fact.get("id")] if fact.get("id") else [],
            "readiness_status": "DEFENDABLE",
            "confidence": 0.6,
            "risk_reason": "结果数字还没有可核对来源，面试前需要候选人自己确认。",
            "attack_surface": [],
        })
    if not claims:
        claims.append({
            "claim": "我完成过一个产品分析项目。",
            "current_text": "完成过一个产品分析项目",
            "suggested_text": None,
            "reason": "源事实里只有这一条。",
            "jd_relevance": "岗位要求讲清真实项目。",
            "matched_capabilities": [],
            "evidence_refs": [],
            "readiness_status": "NEEDS_EVIDENCE",
            "confidence": 0.3,
            "risk_reason": "缺少可核对证据。",
            "attack_surface": [],
        })
    return {"claims": claims}


def _interview_pack(_payload: dict) -> dict:
    return {
        "topics": [
            {
                "priority": "HIGH",
                "topic": "讲清楚一个真实项目的完整过程",
                "why": "面试官会追问你在项目里具体做了什么、怎么判断优先级。",
                "claims": [],
                "capabilities": ["产品分析"],
                "intel_refs": [],
                "question_patterns": ["挑一个你主导过的项目，说说从需求到上线的过程。"],
                "evidence_expected": ["项目背景", "你的具体动作", "可核对的结果"],
            },
            {
                "priority": "MEDIUM",
                "topic": "如何判断需求优先级",
                "why": "岗位要求在多需求下做取舍。",
                "claims": [],
                "capabilities": ["需求优先级"],
                "intel_refs": [],
                "question_patterns": ["需求冲突时你怎么排优先级？"],
                "evidence_expected": ["取舍标准", "一个真实例子"],
            },
        ]
    }


def _interview_answer(_payload: dict) -> dict:
    """故意给出含编造数字的第一人称作答，用来验证事实闸门会拦下它。"""
    return {
        "score": 7,
        "reference_answer": "我主导了这个项目，把转化率提升了 37%，日活从三千涨到一万二，还带了一个五人小组。",
        "reference_answer_detail": {
            "grounded": True,
            "known_facts": [],
            "missing_facts": [{"aspect": "可核对结果", "question": "这个结果的具体数字是多少？"}],
            "answer_structure": ["先说背景", "再说动作", "最后说结果"],
            "sample_wording": "我主导了这个项目，把转化率提升了 37%，日活从三千涨到一万二，还带了一个五人小组。",
            "blocked_reason": None,
        },
        "strong_points": ["结构完整"],
        "weak_points": ["结果数字没有依据"],
        "gap_type": "EVIDENCE",
        "why": "桩模型故意编造数字，用于验证闸门。",
        "evidence_refs": [],
        "recommended_next_action": "补充可核对的事实后再生成示范表达。",
    }


def _interview_question(payload: dict) -> dict:
    """面试「提问」：必须给出 question + skill_id，否则后端直接 422。

    同一个提示词也用于「回答后再追问」——那时 payload 里带 answer，需要同时返回
    evaluation（参考答案），否则这一轮的评分会是空的。
    """
    question = {
        "question": "讲一个你真实做过的项目：背景、你的动作、遇到的取舍、最后的结果。",
        "skill_id": "PROJECT_OWNERSHIP",
        "followup_dimensions": ["结果", "取舍"],
    }
    if payload.get("answer"):
        # 故意给出含编造数字的第一人称作答，用来验证 Sprint A 的事实闸门会拦下它。
        question["evaluation"] = _interview_answer(payload)
        return question
    question["evaluation"] = {}
    return question


def _what_matters(payload: dict) -> dict:
    """只输出「岗位看重什么」的保守结构：不编造能力证据，evidence_refs 一律留空。"""
    jd = str(payload.get("raw_text") or payload.get("jd_text") or "")
    keyword = "产品分析" if "产品" in jd else "通用能力"
    return {
        "core_capabilities": [],
        "high_importance_requirements": [],
        "evidence_expected": [f"能讲清与「{keyword}」相关的真实经历"],
        "likely_success_signals": ["能给出可核对的项目过程"],
        "bonus_capabilities": [],
        "potential_interview_focus": ["真实项目过程", "需求取舍"],
        "confidence": 0.4,
        "jd_evidence_refs": [],
    }


def _resume_extraction(payload: dict) -> dict:
    text = str(payload.get("text") or payload.get("resume_text") or "")
    lines = _first_lines(text, 12)
    return {
        "education": [{"institution": lines[0] if lines else "示例大学", "degree": "本科", "evidence_text": lines[0] if lines else "示例大学"}],
        "skills": [{"name": "产品分析", "evidence_text": "产品分析"}],
        "experiences": [
            {
                "title": "示例项目",
                "organization": "示例组织",
                "dates": "2025.01-2025.06",
                "description": "；".join(lines[1:4]) or "完成了一个产品分析项目",
                "evidence_text": "；".join(lines[1:4]) or "完成了一个产品分析项目",
            }
        ],
        "certifications": [],
    }


# 顺序即优先级：越靠前越先匹配。
# 注意：不能把「question / interview」这类宽泛词放在前面——
# 岗位简历生成的提示词里同时含 "follow-up questions" 和 "interview-ready"，
# 早期版本因此被误判成「面试提问」，返回错误结构导致后端 502。
ROUTES: list[tuple[str, callable]] = [
    # 面试「提问」与「评分」两个提示词里都含 reference_answer，必须先按整句区分，
    # 否则提问会被误判成评分 → 没有 question/skill_id → 后端 422。
    ("run a claim-specific text interview", _interview_question),
    ("evaluate one interview q&a", _interview_answer),
    ("参考回答", _interview_answer),
    ("reference_answer", _interview_answer),
    ("interviewevaluation", _interview_answer),
    ("score the candidate", _interview_answer),
    ("resume optimization", _target_resume),
    ("target resume for one job mission", _target_resume),
    ("draft a versioned target resume", _target_resume),
    ("ground what matters", _what_matters),
    ("extract company, role, role_family", _jd_extraction),
    ("select and explain relevant experiences", _experience_selection),
    ("build a grounded resume strategy", _strategy),
    ("classify readiness as supported", _claims),
    ("interview pack", _interview_pack),
    ("next interview question", _interview_question),
    ("resume extraction", _resume_extraction),
]


def _route(system: str, payload: dict) -> dict:
    text = system.lower()
    for needle, builder in ROUTES:
        if needle.lower() in text:
            return builder(payload)
    if "question" in text and "interview" in text:
        return _interview_question(payload)
    if "resume" in text and "json" in text and "target" not in text:
        return _resume_extraction(payload)
    # 不支持的操作：返回可被识别为空响应的内容，让上层走降级或报错，不伪造内容。
    return {"type": "json_object"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    messages = body.get("messages") or []
    system = _system_prompt(messages)
    payload = _user_payload(messages)
    content = json.dumps(_route(system, payload), ensure_ascii=False)
    CALLS.append({"model": body.get("model"), "system_head": system[:120], "chars": len(content)})
    return JSONResponse(
        {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model") or "stub-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(system) // 4, "completion_tokens": len(content) // 4, "total_tokens": (len(system) + len(content)) // 4},
        }
    )


@app.get("/v1/models")
async def models() -> JSONResponse:
    return JSONResponse({"data": [{"id": "stub-model", "object": "model"}]})


@app.get("/__calls")
async def calls() -> JSONResponse:
    return JSONResponse({"count": len(CALLS), "calls": CALLS})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8801)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
