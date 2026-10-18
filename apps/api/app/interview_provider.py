from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

import httpx
from pydantic import ValidationError

from .proof_schemas import InterviewGapType, InterviewResponsePayload
from .model_config_service import ModelNotConfiguredError, ModelUnusableError, llm_settings, try_llm_settings


class InterviewProviderError(RuntimeError):
    pass


class InterviewProviderNotConfiguredError(InterviewProviderError):
    pass


class InterviewProviderTimeoutError(InterviewProviderError):
    pass


class InterviewProviderConnectionError(InterviewProviderError):
    pass


class InterviewProviderInvalidResponseError(InterviewProviderError):
    def __init__(self, message: str = "interview provider returned invalid structured output", *, reason: str = "schema_validation") -> None:
        super().__init__(message)
        self.reason = reason


class InterviewProvider(Protocol):
    def ask(
        self,
        *,
        target_job: dict[str, object],
        claim: dict[str, object],
        evidence: list[dict[str, object]],
        skills: list[dict[str, object]],
        turns: list[dict[str, object]],
        answer: str | None,
        attested_facts: list[str] | None = None,
        rejected_facts: list[str] | None = None,
    ) -> InterviewResponsePayload: ...


def _is_deepseek(base_url: str | None) -> bool:
    hostname = (urlparse(base_url or "").hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


class OpenAIInterviewProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        try:
            _settings = llm_settings("interview")
        except (ModelNotConfiguredError, ModelUnusableError) as _model_exc:
            if client is None:
                raise InterviewProviderNotConfiguredError(str(_model_exc)) from _model_exc
            _settings = None
        api_key = _settings.api_key if _settings else ""
        base_url = _settings.base_url if _settings else None
        self.model = _settings.model if _settings else "gpt-4o-mini"
        self.is_deepseek = _is_deepseek(base_url)
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            # Interview turns are interactive. Keep the default provider wait
            # short enough that the deterministic Chinese fallback can keep
            # the user moving; deployments can raise it explicitly.
            timeout = os.getenv("OPENAI_INTERVIEW_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "15"
            options: dict[str, object] = {"api_key": api_key, "timeout": float(timeout), "max_retries": int(os.getenv("OPENAI_MAX_RETRIES", "0"))}
            if base_url:
                options["base_url"] = base_url
            self.client = OpenAI(**options)
        except Exception as exc:
            raise InterviewProviderNotConfiguredError("interview provider configuration is invalid") from exc

    #: 参考答案的硬性契约：把「已知事实 / 待补 / 方法 / 示范」分开，禁止补造第一人称经历。
    _REFERENCE_CONTRACT = (
        "Reference answer contract (must follow exactly):\n"
        "1. Every substantive statement about the candidate must be traceable to supplied facts "
        "(final_resume bullets, claim, evidence, or prior turns the candidate actually said).\n"
        "2. You MUST NOT add numbers, people, teams, tools, dates, launches, results, or metrics "
        "that the supplied facts do not contain. Do not turn participation into ownership, "
        "a prototype into a shipped product, or a plan into a delivered result.\n"
        "3. Put the answer into evaluation.reference_answer_detail with:\n"
        "   - known_facts: [{text, source_kind: SOURCE_EXTRACTED|USER_PROVIDED|AI_PROPOSED, source_id, quote}] "
        "for what is actually supported, with the source quote.\n"
        "   - missing_facts: [{aspect, question}] for what the candidate must still supply "
        "(actions taken, problems found, trade-offs, results).\n"
        "   - answer_structure: [\"step\", ...] a STAR-like structure for this question.\n"
        "   - sample_wording: a first-person sample paragraph. ONLY produce it when known_facts "
        "already support the whole story; otherwise set it to null.\n"
        "   - grounded: true only when sample_wording is fully supported by known_facts; otherwise false.\n"
        "4. evaluation.reference_answer is the candidate-facing text. When grounded is true it may be the "
        "sample_wording. When grounded is false it MUST be only the supported facts, the open questions, "
        "and the answer structure - never a fabricated first-person narrative."
    )

    @classmethod
    def _system_prompt(cls) -> str:
        return (
            "Run a claim-specific text interview. Use only the supplied target JD, the latest confirmed final_resume bullets "
            "(prefer those bullets when choosing what to ask), resume claim, Profile evidence, curated skill pack, interview pack topics, "
            "and bounded interview_intel question patterns from real curated company reports, "
            "and prior turns. Ask one concrete question at a time and return JSON only with "
            "question, skill_id, followup_dimensions, and evaluation. Evaluation must include a simple integer score 0-10 "
            "when an answer is present, plus 1-2 strong_points, 1-2 weak_points, a concise recommended_next_action, "
            "and reference_answer grounded in supplied facts. "
            "Use Simplified Chinese for every question, feedback, suggested answer, and next action. "
            "Do not invent user outcomes, numbers, tools, teams, launches or results. "
            "When interview_intel is present, prefer its matching question patterns and focus signals; do not present source IDs as user-facing text. "
            "After enough turns, set question and skill_id to null and classify one gap type: KNOWLEDGE_GAP, "
            "PROJECT_GAP, EVIDENCE_GAP, or ARTICULATION_GAP. Keep evidence_refs to supplied UUIDs and never add keys.\n"
            + cls._REFERENCE_CONTRACT
        )

    @staticmethod
    def _as_str_list(value: object, *, max_items: int = 8, max_len: int = 300) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text[:max_len]] if text else []
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip()[:max_len])
            elif item is not None:
                text = str(item).strip()
                if text:
                    out.append(text[:max_len])
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _as_uuid_list(value: object, *, max_items: int = 12) -> list[str]:
        if value is None:
            return []
        raw = value if isinstance(value, list) else [value]
        out: list[str] = []
        for item in raw:
            try:
                out.append(str(UUID(str(item).strip())))
            except Exception:
                continue
            if len(out) >= max_items:
                break
        return out

    @classmethod
    def _normalize_gap_type(cls, value: object) -> str | None:
        if value is None:
            return None
        raw = str(value).strip().upper().replace(" ", "_").replace("-", "_")
        if not raw:
            return None
        aliases = {
            "KNOWLEDGE": "KNOWLEDGE_GAP",
            "KNOWLEDGE_GAP": "KNOWLEDGE_GAP",
            "PROJECT": "PROJECT_GAP",
            "PROJECT_GAP": "PROJECT_GAP",
            "EVIDENCE": "EVIDENCE_GAP",
            "EVIDENCE_GAP": "EVIDENCE_GAP",
            "ARTICULATION": "ARTICULATION_GAP",
            "ARTICULATION_GAP": "ARTICULATION_GAP",
        }
        mapped = aliases.get(raw)
        if mapped is None:
            try:
                return InterviewGapType(raw).value
            except Exception:
                return None
        return mapped

    @classmethod
    def _normalize_evaluation(cls, value: object) -> dict[str, object]:
        """Soft-normalize LLM evaluation shapes (mirrors claim_provider soft path)."""
        label_defaults = {
            "OPENING": "开场轮次，尚未形成完整评价",
            "PASS": "本轮表现可接受，继续追问",
            "FAIL": "本轮回答偏弱，需继续澄清",
            "CONTINUE": "继续追问以收集更多证据",
            "INCOMPLETE": "评价信息不完整，已做结构化归一",
        }
        if isinstance(value, str):
            label = value.strip()
            key = label.upper().replace(" ", "_").replace("-", "_")
            why = label_defaults.get(key) or (f"模型返回了简短评价标签：{label}" if label else "模型返回了非结构化评价，已做归一")
            return {
                "score": None,
                "reference_answer": None,
                "strong_points": [],
                "weak_points": [],
                "gap_type": None,
                "why": why[:600],
                "evidence_refs": [],
                "recommended_next_action": None,
            }
        if not isinstance(value, dict):
            return {
                "score": None,
                "reference_answer": None,
                "strong_points": [],
                "weak_points": [],
                "gap_type": None,
                "why": "模型未返回结构化评价，已用空评价占位",
                "evidence_refs": [],
                "recommended_next_action": None,
            }

        score_raw = value.get("score") or value.get("rating")
        try:
            score = max(0, min(10, int(float(score_raw)))) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None
        why_raw = value.get("why") or value.get("reason") or value.get("summary") or value.get("note")
        if isinstance(why_raw, str):
            why = why_raw.strip()[:600] or None
        else:
            why = None

        next_raw = value.get("recommended_next_action") or value.get("next_action") or value.get("recommendation")
        if isinstance(next_raw, str):
            recommended = next_raw.strip()[:600] or None
        else:
            recommended = None

        return {
            "score": score,
            "reference_answer": str(value.get("reference_answer") or value.get("sample_answer") or "").strip()[:1_200] or None,
            "reference_answer_detail": cls._normalize_reference_detail(value.get("reference_answer_detail")),
            "strong_points": cls._as_str_list(value.get("strong_points") or value.get("strengths"), max_items=8, max_len=300),
            "weak_points": cls._as_str_list(value.get("weak_points") or value.get("weaknesses"), max_items=8, max_len=300),
            "gap_type": cls._normalize_gap_type(value.get("gap_type") or value.get("gap")),
            "why": why,
            "evidence_refs": cls._as_uuid_list(value.get("evidence_refs") or value.get("evidence") or []),
            "recommended_next_action": recommended,
        }

    @classmethod
    def _normalize_reference_detail(cls, value: object) -> dict[str, object] | None:
        """把模型给出的结构化参考答案收成固定形状。形状不对就返回 None（后续按未自审处理）。"""
        if not isinstance(value, dict):
            return None

        def _rows(raw: object, *, keys: tuple[str, ...], limit: int) -> list[dict[str, str]]:
            if not isinstance(raw, list):
                return []
            rows: list[dict[str, str]] = []
            for item in raw:
                if isinstance(item, dict):
                    text = ""
                    for key in keys:
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            text = candidate.strip()
                            break
                    if not text:
                        continue
                    row = {key: (str(item.get(key)).strip() if item.get(key) is not None else "") for key in keys}
                    row[keys[0]] = text
                    rows.append({k: v[:400] for k, v in row.items()})
                elif isinstance(item, str) and item.strip():
                    rows.append({keys[0]: item.strip()[:400], **{k: "" for k in keys[1:]}})
                if len(rows) >= limit:
                    break
            return rows

        sample = value.get("sample_wording")
        sample = sample.strip()[:1_200] if isinstance(sample, str) and sample.strip() else None
        blocked = value.get("blocked_reason")
        return {
            "grounded": bool(value.get("grounded") is True),
            "known_facts": _rows(value.get("known_facts"), keys=("text", "source_kind", "source_id", "quote"), limit=12),
            "missing_facts": _rows(value.get("missing_facts"), keys=("aspect", "question"), limit=12),
            "answer_structure": cls._as_str_list(value.get("answer_structure") or value.get("structure"), max_items=8, max_len=200),
            "sample_wording": sample,
            "blocked_reason": blocked.strip()[:400] if isinstance(blocked, str) and blocked.strip() else None,
            "screening": {},
        }

    @classmethod
    def _normalize_interview_payload(cls, data: object) -> dict[str, object]:
        if not isinstance(data, dict):
            raise InterviewProviderInvalidResponseError(reason="response_shape")

        question = data.get("question")
        if isinstance(question, str):
            question = question.strip()[:1_000] or None
        elif question is not None:
            text = str(question).strip()
            question = text[:1_000] if text else None

        skill_id = data.get("skill_id")
        if isinstance(skill_id, str):
            skill_id = skill_id.strip()[:64] or None
        elif skill_id is not None:
            text = str(skill_id).strip()
            skill_id = text[:64] if text else None

        followups = cls._as_str_list(
            data.get("followup_dimensions") or data.get("followups") or data.get("dimensions"),
            max_items=8,
            max_len=64,
        )

        evaluation = data.get("evaluation")
        if evaluation is None and any(key in data for key in ("score", "rating", "strong_points", "weak_points", "gap_type", "why")):
            evaluation = {
                "strong_points": data.get("strong_points"),
                "weak_points": data.get("weak_points"),
                "score": data.get("score") or data.get("rating"),
                "reference_answer": data.get("reference_answer") or data.get("sample_answer"),
                "gap_type": data.get("gap_type"),
                "why": data.get("why"),
                "evidence_refs": data.get("evidence_refs"),
                "recommended_next_action": data.get("recommended_next_action"),
            }

        return {
            "question": question,
            "skill_id": skill_id,
            "followup_dimensions": followups,
            "evaluation": cls._normalize_evaluation(evaluation),
        }

    @staticmethod
    def _legacy_reference_risk(reference: str, grounding: str) -> list[str]:
        """旧版确定性规则（数字 + 「访谈某人」）。保留以确保护栏能力不回退。"""
        if not reference or not grounding.strip(" {}[]\"'"):
            return []
        reasons: list[str] = []
        answer_numbers = re.findall(r"(?<!\w)\d+(?:\.\d+)?\s*[%％]?", reference)
        missing_numbers = [token.strip() for token in answer_numbers if token.strip() not in grounding]
        if missing_numbers:
            reasons.append(f"参考回答出现了证据里没有的数字：{missing_numbers}。")
        high_risk_actions = re.findall(r"(?:访谈|采访|访问)[^。；，,。\n]{0,16}(?:用户|创作者|客户|专家)", reference)
        if high_risk_actions and not any(action in grounding for action in high_risk_actions):
            reasons.append("参考回答出现了证据里没有的用户访谈动作。")
        return reasons

    @staticmethod
    def _rejected_fact_hits(candidate: str, rejected_facts: list[str] | None) -> list[str]:
        """用户已否认的事实不得再次进入参考回答。"""
        if not candidate or not rejected_facts:
            return []
        from .fact_trust import coverage_score

        hits: list[str] = []
        for fact in rejected_facts:
            text = str(fact or "").strip()
            if not text:
                continue
            if coverage_score(text, candidate) >= 0.6:
                hits.append(text)
        return hits

    @classmethod
    def _gate_reference_answer(
        cls,
        evaluation: dict[str, object],
        *,
        target_job: dict[str, object],
        claim: dict[str, object],
        evidence: list[dict[str, object]],
        attested_facts: list[str] | None = None,
        rejected_facts: list[str] | None = None,
        context: str | None = None,
    ) -> dict[str, object]:
        """Fail closed when a reference answer adds candidate facts absent from supplied evidence.

        三重保险，任一不通过即降级为「已知事实 / 待补 / 方法」，绝不产出第一人称成稿：

        1. **模型自审**：``reference_answer_detail.grounded`` 必须为 true 才可能放行。
        2. **确定性筛查**：证据中不存在的数量值、高风险动作/结果词、句子级覆盖率过低。
        3. **旧版规则**：数字与「访谈某人」模式（保留既有拦截能力）。

        判断不确定时一律保守降级，不默默放行。
        """
        from .fact_trust import merge_grounding, normalize_text, render_degraded_reference, screen_reference_wording

        detail = evaluation.get("reference_answer_detail")
        detail = detail if isinstance(detail, dict) else None
        reference = str(evaluation.get("reference_answer") or "").strip()
        sample = str(detail.get("sample_wording") or "").strip() if detail else ""
        if not reference and not sample and detail is None:
            # 模型既没给结构化详情也没给参考答案时保持原样，避免给空评价凭空塞内容。
            return evaluation

        corpus_parts: list[object] = [
            json.dumps(target_job.get("final_resume") or {}, ensure_ascii=False),
            str(claim.get("claim") or ""),
            json.dumps(evidence or [], ensure_ascii=False),
        ]
        if context:
            corpus_parts.append(context)
        if attested_facts:
            corpus_parts.extend(attested_facts)
        grounding = merge_grounding(corpus_parts)

        known = list(detail.get("known_facts") or []) if detail else []
        missing = list(detail.get("missing_facts") or []) if detail else []
        structure = list(detail.get("answer_structure") or []) if detail else []
        # 模型给了 sample_wording 就以它为准；否则退回旧字段（旧格式兼容）。
        candidate = sample or reference

        blocked: list[str] = []
        screening = None
        if candidate:
            rejected_hits = cls._rejected_fact_hits(candidate, rejected_facts)
            if rejected_hits:
                blocked.append("参考回答使用了你已标记为不属实的事实。")
            if not normalize_text(grounding):
                blocked.append("没有可核对的事实依据，不能生成候选人陈述。")
            if detail is not None and not detail.get("grounded"):
                blocked.append("模型自审判定事实不足，示范表达已降级。")
            screening = screen_reference_wording(candidate, grounding)
            if not screening.supported:
                blocked.extend(screening.reasons)
            blocked.extend(cls._legacy_reference_risk(candidate, grounding))
        else:
            blocked.append("模型未提供可使用的示范表达。")

        if not blocked and candidate:
            return {
                **evaluation,
                "reference_answer": candidate,
                "reference_answer_detail": {
                    **(detail or {}),
                    "grounded": True,
                    "sample_wording": candidate,
                    "blocked_reason": None,
                    "screening": screening.as_dict() if screening else {},
                },
            }

        weak_points = list(evaluation.get("weak_points") or [])
        note = "参考回答含有未确认事实，已拦截。"
        if note not in weak_points:
            weak_points.append(note)
        reason = " ".join(blocked) or (str(detail.get("blocked_reason") or "") if detail else "")
        friendly_reason = (
            "证据不足，不能把这项动作或数字写入候选人的回答。下面是已有的事实、还缺的信息和建议的表达结构。"
        )
        if not missing:
            missing = [
                {"aspect": "你的具体动作", "question": "你亲自做了哪几步？"},
                {"aspect": "过程中的发现或困难", "question": "遇到过什么问题，怎么取舍？"},
                {"aspect": "可核对的结果", "question": "有什么能复核的产出、数据或反馈？"},
            ]
        degraded = render_degraded_reference(
            known_facts=known,
            missing_facts=missing,
            answer_structure=structure,
            reason=friendly_reason,
        )
        return {
            **evaluation,
            "reference_answer": degraded,
            "reference_answer_detail": {
                **(detail or {}),
                "grounded": False,
                "sample_wording": None,
                "blocked_reason": (reason or None),
                "known_facts": known,
                "missing_facts": missing,
                "answer_structure": structure,
                "screening": screening.as_dict() if screening else {},
            },
            "weak_points": weak_points[:8],
            "recommended_next_action": evaluation.get("recommended_next_action") or "补充对应项目的原始记录、过程或结果证据。",
        }

    def ask(
        self,
        *,
        target_job: dict[str, object],
        claim: dict[str, object],
        evidence: list[dict[str, object]],
        skills: list[dict[str, object]],
        turns: list[dict[str, object]],
        answer: str | None,
        attested_facts: list[str] | None = None,
        rejected_facts: list[str] | None = None,
    ) -> InterviewResponsePayload:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps({"target_job": target_job, "claim": claim, "evidence": evidence, "skills": skills, "turns": turns, "answer": answer}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise InterviewProviderTimeoutError("interview provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise InterviewProviderConnectionError("interview provider request failed") from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.casefold():
                raise InterviewProviderTimeoutError("interview provider timed out") from exc
            raise InterviewProviderConnectionError("interview provider request failed") from exc
        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise InterviewProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise InterviewProviderInvalidResponseError(reason="empty_response")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InterviewProviderInvalidResponseError(reason="json_decode") from exc
        try:
            normalized = self._normalize_interview_payload(data)
            normalized["evaluation"] = self._gate_reference_answer(
                normalized["evaluation"],
                target_job=target_job,
                claim=claim,
                evidence=evidence,
                attested_facts=attested_facts,
                rejected_facts=rejected_facts,
            )
            return InterviewResponsePayload.model_validate(normalized)
        except InterviewProviderInvalidResponseError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise InterviewProviderInvalidResponseError(reason="schema_validation") from exc


    @classmethod
    def _evaluate_system_prompt(cls) -> str:
        return (
            "Evaluate one interview Q&A for a job candidate. "
            "Return ONLY a JSON object with an evaluation object. "
            "Evaluation must include: score (integer 0-10), strong_points (string list), "
            "weak_points (string list), gap_type (one of KNOWLEDGE_GAP, PROJECT_GAP, EVIDENCE_GAP, ARTICULATION_GAP or null), "
            "why (short Chinese reason), reference_answer (optional Chinese sample), "
            "recommended_next_action (short Chinese next step). "
            "Do not invent employer-specific secrets. Prefer concrete, actionable Chinese feedback.\n"
            "The only facts you may use are the candidate's own answer and the supplied context. "
            "Never add numbers, people, teams, tools, dates, launches or results they did not state.\n"
            + cls._REFERENCE_CONTRACT
        )

    def evaluate_answer(
        self,
        *,
        question: str,
        answer: str,
        context: str | None = None,
        company: str | None = None,
        role: str | None = None,
    ):
        from .proof_schemas import InterviewEvaluation

        payload = {
            "company": company or "",
            "role": role or "",
            "question": question,
            "context": context or "",
            "answer": answer,
        }
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._evaluate_system_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise InterviewProviderTimeoutError("interview provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise InterviewProviderConnectionError("interview provider request failed") from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.casefold():
                raise InterviewProviderTimeoutError("interview provider timed out") from exc
            raise InterviewProviderConnectionError("interview provider request failed") from exc
        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise InterviewProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise InterviewProviderInvalidResponseError(reason="empty_response")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InterviewProviderInvalidResponseError(reason="json_decode") from exc
        if not isinstance(data, dict):
            raise InterviewProviderInvalidResponseError(reason="response_shape")
        evaluation = data.get("evaluation") if isinstance(data.get("evaluation"), dict) else data
        try:
            normalized = self._normalize_evaluation(evaluation)
            # 同一套事实闸门：参考答案只能复述候选人自己说过的话与给定上下文。
            normalized = self._gate_reference_answer(
                normalized,
                target_job={"final_resume": {}},
                claim={"claim": answer or ""},
                evidence=[],
                context=context,
            )
            return InterviewEvaluation.model_validate(normalized)
        except (ValidationError, TypeError, ValueError) as exc:
            raise InterviewProviderInvalidResponseError(reason="schema_validation") from exc



_provider: InterviewProvider | None = None


def set_interview_provider(provider: InterviewProvider | None) -> None:
    global _provider
    _provider = provider


def get_interview_provider() -> InterviewProvider:
    return _provider if _provider is not None else OpenAIInterviewProvider()
