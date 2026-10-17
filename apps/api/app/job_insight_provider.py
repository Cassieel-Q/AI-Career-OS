"""岗位洞察：岗位关键词分析 + 简历×岗位匹配度分析（均走模型，失败降级到本地规则）。

背景（用户反馈）：
- 「准备度」原来只是把 workflow_state 映射成一个固定分数，与简历毫无关系，说不清为什么匹配；
- 岗位表格里没有任何岗位特征，用户希望能一眼看到这个岗位在要什么。

所以这里提供两个纯函数：
- ``analyze_job_keywords``：从 JD 里提炼 **2~3 个**岗位关键词（用于岗位表格展示）；
- ``analyze_job_match``：把「候选人简历事实」与「岗位要求」比对，给出 0~100 匹配分、
  为什么匹配、哪里不匹配、是否值得投递。

两者都是**模型优先**：模型不可用/超时/返回不合规时，退回本地规则估算，
并在结果里用 ``source`` 字段标明（``LLM`` / ``LOCAL_RULE``），绝不让页面白屏。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable
from .model_config_service import ModelNotConfiguredError, ModelUnusableError, llm_settings, try_llm_settings

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


def _deepseek_enabled(module: str = "insight") -> bool:
    """当前生效配置是否是 DeepSeek（用户配置或旧环境变量）。"""
    settings = try_llm_settings(module)
    return bool(settings and settings.is_deepseek)


class JobInsightError(RuntimeError):
    """岗位洞察生成失败的统一异常。"""


class JobInsightNotConfiguredError(JobInsightError):
    """未配置模型（缺 OPENAI_API_KEY）。"""


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


def _is_deepseek(base_url: str | None) -> bool:
    return "deepseek" in (base_url or "").casefold()


def build_insight_client() -> tuple[Any, str]:
    try:
        _settings = llm_settings("insight")
    except (ModelNotConfiguredError, ModelUnusableError) as _model_exc:
        raise JobInsightNotConfiguredError(str(_model_exc)) from _model_exc
    api_key = _settings.api_key if _settings else ""
    base_url = _settings.base_url if _settings else None
    model = _settings.model if _settings else "gpt-4o-mini"
    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        raise JobInsightNotConfiguredError("openai sdk is not installed") from exc
    try:
        timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS") or "30")
    except ValueError:
        timeout = 30.0
    options: dict[str, object] = {"api_key": api_key, "timeout": timeout}
    if base_url:
        options["base_url"] = base_url
    try:
        return OpenAI(**options), model
    except Exception as exc:  # noqa: BLE001
        raise JobInsightNotConfiguredError("job insight provider configuration is invalid") from exc


def _call_json(system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    client, model = build_insight_client()
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }
    if _deepseek_enabled():
        request["extra_body"] = {"thinking": {"type": "disabled"}}
    response = client.chat.completions.create(**request)
    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise JobInsightError("model returned an empty response") from exc
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].casefold() == "json":
            text = text[4:]
        text = text.strip()
    if not text:
        raise JobInsightError("model returned an empty payload")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JobInsightError("model response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise JobInsightError("model response must be a JSON object")
    return data


# ---------------------------------------------------------------------------
# 岗位关键词
# ---------------------------------------------------------------------------

_KEYWORD_PROMPT = (
    "你是招聘岗位分析专家。根据给出的岗位信息，提炼这个岗位**最核心的 2 到 3 个关键词**，"
    "用于岗位列表里一眼看懂「这个岗位到底在要什么」。\n"
    "硬约束：\n"
    "1. 关键词必须来自岗位描述，不要凭空发明；\n"
    "2. 每个关键词 2~8 个字，是名词或名词短语（如「用户增长」「SQL 建模」「To B 销售」）；\n"
    "3. 关键词之间要有区分度，不要同义反复，不要用「沟通能力」这类空话；\n"
    "4. 再给一句不超过 30 字的摘要，说明这个岗位的核心职责。\n"
    "只输出 JSON：{\"keywords\": [\"...\", \"...\"], \"summary\": \"...\"}"
)

_STOPWORDS = {
    "以及", "并且", "负责", "要求", "熟悉", "熟练", "掌握", "具备", "优先", "相关", "经验",
    "能力", "工作", "岗位", "以上", "良好", "团队", "公司", "进行", "我们", "你们", "能够",
}


def _clean_keywords(raw: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = re.sub(r"\s+", " ", item).strip().strip("，,。.;；:：/、|-—【】[]()（）").strip()
        if not text or len(text) > 16:
            continue
        if text.casefold() in _STOPWORDS:
            continue
        key = text.casefold().replace(" ", "")
        if any(key == seen.casefold().replace(" ", "") for seen in out):
            continue
        out.append(text)
        if len(out) == 3:
            break
    return out


def local_job_keywords(
    *,
    role: str | None,
    requirement_names: list[str] | None = None,
    jd_text: str | None = None,
) -> list[str]:
    """本地规则兜底：优先用已解析出的岗位要求名，其次从 JD 里挑高频名词短语。"""
    picked: list[str] = _clean_keywords(list(requirement_names or []))
    if len(picked) < 2:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.\- ]{1,18}|[\u4e00-\u9fa5]{2,6}", jd_text or "")
        counter: dict[str, int] = {}
        candidates: list[str] = []
        for token in tokens:
            key = token.strip()
            if not key or key.casefold() in _STOPWORDS:
                continue
            counter[key] = counter.get(key, 0) + 1
        for key, _count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])):
            candidates.append(key)
        picked = _clean_keywords([*picked, *candidates])
    if not picked and role:
        picked = _clean_keywords([role])
    return picked[:3]


def analyze_job_keywords(
    *,
    role: str | None,
    company: str | None = None,
    jd_text: str | None = None,
    requirement_names: list[str] | None = None,
) -> dict[str, Any]:
    """返回 ``{"keywords": [...], "summary": str, "source": "LLM"|"LOCAL_RULE"}``。"""
    local_keywords = local_job_keywords(role=role, requirement_names=requirement_names, jd_text=jd_text)
    fallback = {
        "keywords": local_keywords,
        "summary": (f"{company} · {role}" if company else (role or "")).strip(" ·")[:40],
        "source": "LOCAL_RULE",
    }
    try:
        data = _call_json(
            _KEYWORD_PROMPT,
            {
                "公司": company or "未指定",
                "岗位": role or "未指定",
                "已解析的岗位要求": list(requirement_names or [])[:20],
                "岗位描述": (jd_text or "")[:4000],
            },
        )
    except JobInsightError:
        return fallback
    except Exception:  # noqa: BLE001 - 网络/超时/鉴权等一律降级
        return fallback
    keywords = _clean_keywords(data.get("keywords") or [])
    if len(keywords) < 2:
        return fallback
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback["summary"]
    return {"keywords": keywords, "summary": summary.strip()[:60], "source": "LLM"}


# ---------------------------------------------------------------------------
# 简历 × 岗位匹配度
# ---------------------------------------------------------------------------

_MATCH_PROMPT = (
    "你是资深职业顾问。请把「候选人简历事实」与「岗位要求」逐条比对，给出匹配度评估。\n"
    "硬约束：\n"
    "1. 只能依据给出的简历事实，简历里没有的能力一律视为「不匹配」，不要替候选人假设；\n"
    "2. reasons（为什么匹配）与 gaps（哪里不匹配）都必须具体，最好引用简历原文或岗位要求原文；\n"
    "3. score 是 0~100 的整数，按「岗位硬性要求被简历直接命中」的比例给分，宁可保守；\n"
    "4. verdict 必须与 score 保持一致：score ≥ 70 → strong(值得投递)；40 ≤ score < 70 → maybe(先补齐再投)；\n"
    "   score < 40 → weak(暂不建议投递)；\n"
    "5. advice 一句话说清下一步该做什么，不超过 40 字。\n"
    "只输出 JSON：{\"score\": 0-100, \"verdict\": \"strong|maybe|weak\", \"reasons\": [\"...\"], "
    "\"gaps\": [\"...\"], \"advice\": \"...\"}"
)


def verdict_for_score(score: int) -> str:
    """结论由分数统一推导，保证「分数」与「是否值得投递」在界面上永远自洽。

    模型仍然会在 advice / reasons / gaps 里保留它对硬性门槛的判断，
    但如果让模型单独给 verdict，就会出现「72 分值得投递」「75 分先补齐再投」这类
    自相矛盾的展示（用户实测里确实出现过），所以这里统一口径。
    """
    if score >= 70:
        return "strong"
    if score >= 40:
        return "maybe"
    return "weak"


def _resume_tokens(resume_text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,20}|[\u4e00-\u9fa5]{2,6}", resume_text or "")
    return {token.casefold() for token in tokens if token.strip()}


def local_job_match(
    *,
    resume_text: str | None,
    requirement_names: list[str] | None = None,
    has_resume: bool = True,
) -> dict[str, Any]:
    """本地规则兜底：按「岗位要求名在简历原文里出现过」的比例给分。"""
    requirements = [str(name).strip() for name in (requirement_names or []) if str(name).strip()]
    if not has_resume or not (resume_text or "").strip():
        return {
            "score": 0,
            "verdict": "weak",
            "reasons": [],
            "gaps": ["还没有可用于比对的简历原文"],
            "advice": "先在简历中心上传简历，再来评估匹配度。",
            "source": "LOCAL_RULE",
        }
    tokens = _resume_tokens(resume_text or "")
    if not requirements:
        return {
            "score": 50,
            "verdict": "maybe",
            "reasons": ["岗位要求还没解析出来，暂按中等匹配估算"],
            "gaps": ["岗位要求解析缺失，无法逐条比对"],
            "advice": "先刷新岗位解析，再评估匹配度。",
            "source": "LOCAL_RULE",
        }
    hits = [name for name in requirements if name.casefold() in tokens or name.casefold() in (resume_text or "").casefold()]
    missed = [name for name in requirements if name not in hits]
    score = max(5, min(95, int(round(len(hits) / len(requirements) * 100))))
    verdict = verdict_for_score(score)
    reasons = [f"简历中已直接出现岗位要求「{name}」" for name in hits[:4]] or ["尚未命中任何明确的岗位要求"]
    gaps = [f"简历中没有找到岗位要求「{name}」的依据" for name in missed[:4]]
    advice = {
        "strong": "匹配度不错，可以准备投递并重点讲命中项。",
        "maybe": "先补齐未命中的要求，再决定是否投递。",
        "weak": "当前简历与岗位差距较大，建议先换更匹配的岗位。",
    }[verdict]
    return {
        "score": score,
        "verdict": verdict,
        "reasons": reasons,
        "gaps": gaps,
        "advice": advice,
        "source": "LOCAL_RULE",
    }


def _clean_strings(raw: Any, limit: int = 6) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        out.append(text[:120])
        if len(out) == limit:
            break
    return out


def analyze_job_match(
    *,
    role: str | None,
    company: str | None = None,
    resume_text: str | None = None,
    jd_text: str | None = None,
    requirement_names: list[str] | None = None,
    has_resume: bool = True,
) -> dict[str, Any]:
    """返回 ``{score, verdict, reasons, gaps, advice, source}``。"""
    fallback = local_job_match(resume_text=resume_text, requirement_names=requirement_names, has_resume=has_resume)
    if not has_resume or not (resume_text or "").strip():
        return fallback
    try:
        data = _call_json(
            _MATCH_PROMPT,
            {
                "公司": company or "未指定",
                "岗位": role or "未指定",
                "已解析的岗位要求": list(requirement_names or [])[:20],
                "岗位描述": (jd_text or "")[:4000],
                "简历事实": (resume_text or "")[:6000],
            },
        )
    except JobInsightError:
        return fallback
    except Exception:  # noqa: BLE001
        return fallback
    try:
        score = int(round(float(data.get("score"))))
    except (TypeError, ValueError):
        return fallback
    score = max(0, min(100, score))
    verdict = verdict_for_score(score)
    reasons = _clean_strings(data.get("reasons"))
    gaps = _clean_strings(data.get("gaps"))
    advice = data.get("advice")
    advice = advice.strip()[:80] if isinstance(advice, str) and advice.strip() else fallback["advice"]
    if not reasons and not gaps:
        return fallback
    return {
        "score": score,
        "verdict": verdict,
        "reasons": reasons,
        "gaps": gaps,
        "advice": advice,
        "source": "LLM",
    }


__all__ = [
    "JobInsightError",
    "JobInsightNotConfiguredError",
    "analyze_job_keywords",
    "analyze_job_match",
    "build_insight_client",
    "local_job_keywords",
    "local_job_match",
    "verdict_for_score",
]
