"""面试题库参考答案生成（LLM）。

背景：原来的参考答案只是把已确认事实原文用「；」拼起来，既不像回答，也没有针对性。
这里改为调用模型，基于「已确认事实 + 岗位要求」生成可以直接开口讲的回答要点。

**事实门控不变**：只把已确认事实交给模型，并明确要求不得编造数字、工具、职责、成果；
事实不足时要求如实说明缺什么，而不是硬写。模型不可用/失败时由调用方降级为事实拼接。
"""
from __future__ import annotations

import json
import os
from typing import Any

_SYSTEM_PROMPT = (
    "你是资深面试教练，负责根据「候选人已确认的事实」与「岗位要求」写出一段可以直接开口说的面试回答。\n"
    "硬约束（必须遵守）：\n"
    "1. 只能使用给定的事实，绝对不要编造数字、工具、职责、成果或经历。\n"
    "2. 事实不足以支撑时，不要硬编，改为说明「还需要补充哪一项事实」以及补什么。\n"
    "3. 回答要有结构（优先 STAR：情境-任务-行动-结果），口语化、具体、可复述，控制在 150~260 字。\n"
    "4. 不要复述整段题面，不要输出 markdown、标题或项目符号前的星号。\n"
    "5. 只输出 JSON：{\"answer\": \"...\"}，不要附加任何其它字段或解释。"
)


class QuestionProviderError(RuntimeError):
    """题库参考答案生成失败的统一异常。"""


class QuestionProviderNotConfiguredError(QuestionProviderError):
    """未配置模型（缺 OPENAI_API_KEY）。"""


def _is_deepseek(base_url: str | None) -> bool:
    return "deepseek" in (base_url or "").casefold()


def build_question_client() -> tuple[Any, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise QuestionProviderNotConfiguredError("OPENAI_API_KEY is not configured")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_QUESTION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        raise QuestionProviderNotConfiguredError("openai sdk is not installed") from exc
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
        raise QuestionProviderNotConfiguredError("question provider configuration is invalid") from exc


def generate_answer(
    *,
    question_text: str,
    category: str | None = None,
    jd_refs: list[str] | None = None,
    company: str | None = None,
    role: str | None = None,
    facts: list[str] | None = None,
    followups: list[str] | None = None,
) -> str:
    """调用模型生成一段回答；返回纯文本。异常由调用方捕获并降级。"""
    client, model = build_question_client()
    payload: dict[str, Any] = {
        "岗位": f"{company or '未指定'} · {role or '未指定'}",
        "题目": question_text,
        "题目分类": category or "未指定",
        "关联岗位要求": list(jd_refs or []),
        "可以使用的已确认事实": list(facts or []),
        "可能的追问": list(followups or []),
    }
    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }
    if _is_deepseek(os.getenv("OPENAI_BASE_URL")):
        request["extra_body"] = {"thinking": {"type": "disabled"}}

    response = client.chat.completions.create(**request)
    content = ""
    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise QuestionProviderError("model returned an empty response") from exc

    text = content.strip()
    if not text:
        raise QuestionProviderError("model returned an empty answer")
    # 容错：模型偶尔会包一层 markdown 代码块。
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 不是 JSON 就把它当作纯文本回答（仍然可用）。
        return text
    answer = data.get("answer") if isinstance(data, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise QuestionProviderError("model response is missing the answer field")
    return answer.strip()


__all__ = [
    "QuestionProviderError",
    "QuestionProviderNotConfiguredError",
    "build_question_client",
    "generate_answer",
]
