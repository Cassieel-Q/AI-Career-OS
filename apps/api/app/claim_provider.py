from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Protocol
from uuid import UUID
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .proof_schemas import ClaimProposalPayload


_NIL_UUID = "00000000-0000-0000-0000-000000000000"
_BAD_EVIDENCE_REF_TOKENS = frozenset({"", "none", "null", "undefined", "nil"})


def sanitize_evidence_refs(values: object) -> list[str]:
    """Keep only real UUID strings; drop None/"None"/empty/invalid placeholders.

    Write-path guard: Python None coerced via str() becomes the literal "None",
    which later breaks interview session start. Never persist those.
    """
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, list):
        return out
    for value in values:
        if value is None:
            continue
        if isinstance(value, UUID):
            text = str(value)
        else:
            text = str(value).strip()
        if not text or text.casefold() in _BAD_EVIDENCE_REF_TOKENS:
            continue
        try:
            normalized = str(UUID(text))
        except (TypeError, ValueError, AttributeError):
            continue
        if normalized == _NIL_UUID:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out




logger = logging.getLogger(__name__)


class ClaimProviderError(RuntimeError):
    pass


class ClaimProviderNotConfiguredError(ClaimProviderError):
    pass


class ClaimProviderTimeoutError(ClaimProviderError):
    pass


class ClaimProviderConnectionError(ClaimProviderError):
    pass


class ClaimProviderUpstreamError(ClaimProviderConnectionError):
    def __init__(self, message: str = "claim provider returned an upstream error", *, status_code: int | None = None, provider_code: str | None = None, provider_type: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_code = provider_code
        self.provider_type = provider_type


class ClaimProviderInvalidResponseError(ClaimProviderError):
    def __init__(self, message: str = "claim provider returned invalid structured output", *, reason: str = "schema_validation", validation_errors: list[dict[str, object]] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.validation_errors = validation_errors or []


class ClaimAnalysisProvider(Protocol):
    def analyze(self, *, target_job: dict[str, object], profile_facts: list[dict[str, object]]) -> ClaimProposalPayload: ...


def _is_deepseek(base_url: str | None) -> bool:
    hostname = (urlparse(base_url or "").hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


def _timeout_seconds() -> float:
    raw = (os.getenv("OPENAI_CLAIM_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "15").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ClaimProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or value <= 0 or value > 120:
        raise ClaimProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS is outside the allowed range")
    return value


def _max_retries() -> int:
    raw = os.getenv("OPENAI_MAX_RETRIES", "0").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ClaimProviderNotConfiguredError("OPENAI_MAX_RETRIES must be an integer") from exc
    if value < 0 or value > 2:
        raise ClaimProviderNotConfiguredError("OPENAI_MAX_RETRIES is outside the allowed range")
    return value


class OpenAIClaimAnalysisProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise ClaimProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_CLAIM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = _is_deepseek(base_url)
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            options: dict[str, object] = {
                "api_key": api_key,
                "timeout": _timeout_seconds(),
                "max_retries": _max_retries(),
            }
            if base_url:
                options["base_url"] = base_url
            self.client = OpenAI(**options)
        except ClaimProviderError:
            raise
        except Exception as exc:
            raise ClaimProviderNotConfiguredError("claim provider configuration is invalid") from exc

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Analyze resume claims for one supplied target JD using only the supplied confirmed Profile facts. "
            "Return JSON only with a claims array of at most 3 items. Prefer claims grounded in JD capabilities and concrete project/experience facts (STAR-style ownership, scope, metrics). Do NOT emit isolated skill-list tokens (e.g. Revit / SuperMap / AutoCAD) as standalone claims unless tied to a project outcome. "
            "Each item must be a resume-writable optimization the candidate can paste into a Target Resume "
            "(rewrite/reframe with concrete suggested_text grounded in supplied facts). "
            "Prefer DEFENDABLE or WEAK_EVIDENCE over UNSUPPORTED. "
            "Do not emit a long wall of UNSUPPORTED JD-mapped gaps with no citeable evidence or writable suggested_text. "
            "If evidence is thin, return fewer than 3 rather than inventing claims. "
            "Classify readiness as SUPPORTED, DEFENDABLE, WEAK_EVIDENCE, or UNSUPPORTED. "
            "A done but poorly expressed fact is Rewrite/Reframe; knowledge with weak proof is Strengthen Evidence; "
            "an absent capability is Gap/Action only when it is one of the top 3 priorities and still actionable. "
            "Never invent numbers, outcomes, projects, tools, or experience. "
            "evidence_refs must be copied UUIDs from supplied facts. suggested_text must not add unsupported details. "
            "Include matched_capabilities and a short attack_surface for Product, AI, Engineering, Metrics, and Business impact. "
            "Use a JSON object, no markdown, no extra keys."
        )

    def _request(self, target_job: dict[str, object], profile_facts: list[dict[str, object]]) -> object:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps({"target_job": target_job, "profile_facts": profile_facts}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ClaimProviderTimeoutError("claim provider timed out") from exc
        except (httpx.RequestError, httpx.HTTPStatusError, ConnectionError) as exc:
            raise ClaimProviderConnectionError("claim provider request failed") from exc
        except Exception as exc:
            if any(base.__name__ == "APIStatusError" for base in type(exc).__mro__):
                status_code = getattr(exc, "status_code", None)
                if not isinstance(status_code, int):
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                body = getattr(exc, "body", None)
                details = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body
                if not isinstance(details, dict):
                    details = {}
                raise ClaimProviderUpstreamError(
                    status_code=status_code if isinstance(status_code, int) else None,
                    provider_code=details.get("code") if isinstance(details.get("code"), str) else None,
                    provider_type=details.get("type") if isinstance(details.get("type"), str) else None,
                ) from exc
            name = type(exc).__name__.casefold()
            if "timeout" in name:
                raise ClaimProviderTimeoutError("claim provider timed out") from exc
            raise ClaimProviderConnectionError("claim provider request failed") from exc
        logger.info("claim_provider_latency_ms=%d", round((time.perf_counter() - started) * 1000))
        return response


    @staticmethod
    def _unwrap_claims_payload(data: dict) -> dict:
        if isinstance(data.get("claims"), list):
            return data
        for key in ("result", "data", "output", "payload", "claim_analysis", "analysis"):
            nested = data.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("claims"), list):
                return nested
            if isinstance(nested, list):
                return {"claims": nested}
        if isinstance(data.get("items"), list):
            return {"claims": data["items"]}
        return data

    @staticmethod
    def _as_uuid_list(values: object) -> list[str]:
        return sanitize_evidence_refs(values)

    @staticmethod
    def _normalize_readiness(value: object) -> str:
        raw = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "SUPPORTED": "SUPPORTED",
            "SUPPORT": "SUPPORTED",
            "DEFENDABLE": "DEFENDABLE",
            "DEFENSIBLE": "DEFENDABLE",
            "WEAK": "WEAK_EVIDENCE",
            "WEAK_EVIDENCE": "WEAK_EVIDENCE",
            "WEAKLY_SUPPORTED": "WEAK_EVIDENCE",
            "UNSUPPORTED": "UNSUPPORTED",
            "NOT_SUPPORTED": "UNSUPPORTED",
            "GAP": "UNSUPPORTED",
        }
        return aliases.get(raw, "WEAK_EVIDENCE")

    @staticmethod
    def _normalize_attack_area(value: object) -> str | None:
        raw = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "PRODUCT": "PRODUCT",
            "AI": "AI",
            "ENGINEERING": "ENGINEERING",
            "ENG": "ENGINEERING",
            "METRICS": "METRICS",
            "METRIC": "METRICS",
            "BUSINESS": "BUSINESS_IMPACT",
            "BUSINESS_IMPACT": "BUSINESS_IMPACT",
            "IMPACT": "BUSINESS_IMPACT",
        }
        return aliases.get(raw)

    @classmethod
    def _normalize_claim_item(cls, item: object) -> dict | None:
        if isinstance(item, str) and item.strip():
            claim = item.strip()[:600]
            return {
                "claim": claim,
                "current_text": claim,
                "suggested_text": None,
                "reason": "模型返回了简短主张，已做结构化归一",
                "jd_relevance": "需对照目标 JD 确认相关性",
                "matched_capabilities": [],
                "evidence_refs": [],
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.4,
                "risk_reason": "缺少完整结构化字段，面试前建议复查",
                "attack_surface": [{"area": "PRODUCT", "risk": "准备具体例子与个人贡献说明", "evidence_refs": []}],
            }
        if not isinstance(item, dict):
            return None
        claim = str(item.get("claim") or item.get("statement") or item.get("text") or item.get("title") or "").strip()[:600]
        if not claim:
            return None
        evidence_refs = cls._as_uuid_list(item.get("evidence_refs") or item.get("supporting_evidence_refs") or [])
        readiness = cls._normalize_readiness(item.get("readiness_status") or item.get("readiness") or item.get("status"))
        suggested = item.get("suggested_text")
        if isinstance(suggested, str):
            suggested = suggested.strip()[:600] or None
        else:
            suggested = None
        # Avoid inventing grounded suggestions without evidence.
        if suggested and readiness in {"SUPPORTED", "DEFENDABLE"} and not evidence_refs:
            readiness = "WEAK_EVIDENCE"
            suggested = None
        # Bare JD-shaped UNSUPPORTED lines stay gaps: never attach a writable suggestion without evidence.
        if readiness == "UNSUPPORTED" and not evidence_refs:
            suggested = None
        caps_raw = item.get("matched_capabilities") or item.get("capabilities") or []
        caps: list[dict] = []
        if isinstance(caps_raw, list):
            for cap in caps_raw[:12]:
                if isinstance(cap, str) and cap.strip():
                    caps.append({"name": cap.strip()[:255], "summary": cap.strip()[:600], "atomic_requirement_ids": []})
                elif isinstance(cap, dict):
                    name = str(cap.get("name") or cap.get("capability") or "").strip()[:255]
                    if not name:
                        continue
                    summary = str(cap.get("summary") or cap.get("why") or name).strip()[:600] or name
                    req_ids = cls._as_uuid_list(cap.get("atomic_requirement_ids") or [])
                    caps.append({"name": name, "summary": summary, "atomic_requirement_ids": req_ids})
        attack_raw = item.get("attack_surface") or item.get("attacks") or []
        attacks: list[dict] = []
        if isinstance(attack_raw, list):
            for atk in attack_raw[:5]:
                if isinstance(atk, str) and atk.strip():
                    attacks.append({"area": "PRODUCT", "risk": atk.strip()[:300], "evidence_refs": []})
                    continue
                if not isinstance(atk, dict):
                    continue
                area = cls._normalize_attack_area(atk.get("area") or atk.get("dimension") or atk.get("name") or "PRODUCT")
                if not area:
                    area = "PRODUCT"
                risk = str(atk.get("risk") or atk.get("note") or atk.get("text") or "准备可辩护的具体例子").strip()[:300]
                attacks.append({"area": area, "risk": risk or "准备可辩护的具体例子", "evidence_refs": cls._as_uuid_list(atk.get("evidence_refs") or [])[:12]})
        if not attacks:
            attacks = [{"area": "PRODUCT", "risk": "准备具体例子与个人贡献说明", "evidence_refs": evidence_refs[:12]}]
        try:
            confidence = float(item.get("confidence") if item.get("confidence") is not None else 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        reason = str(item.get("reason") or item.get("why") or "基于已确认履历事实整理的面试主张").strip()[:600]
        jd_relevance = str(item.get("jd_relevance") or item.get("jd_fit") or "需对照目标 JD 确认相关性").strip()[:600]
        risk_reason = str(item.get("risk_reason") or item.get("risk") or "证据或表达仍可能在面试中被追问").strip()[:600]
        current_text = item.get("current_text")
        if isinstance(current_text, str):
            current_text = current_text.strip()[:600] or None
        else:
            current_text = None
        return {
            "claim": claim,
            "current_text": current_text,
            "suggested_text": suggested,
            "reason": reason or "基于已确认履历事实整理的面试主张",
            "jd_relevance": jd_relevance or "需对照目标 JD 确认相关性",
            "matched_capabilities": caps[:12],
            "evidence_refs": evidence_refs[:12],
            "readiness_status": readiness,
            "confidence": confidence,
            "risk_reason": risk_reason or "证据或表达仍可能在面试中被追问",
            "attack_surface": attacks[:5],
        }

    @staticmethod
    def _claim_priority(claim: dict) -> tuple:
        readiness = str(claim.get("readiness_status") or "")
        suggested = bool(claim.get("suggested_text"))
        evidence = bool(claim.get("evidence_refs"))
        if suggested and evidence:
            tier = 4
        elif suggested:
            tier = 3
        elif evidence and readiness != "UNSUPPORTED":
            tier = 2
        elif evidence:
            tier = 1
        else:
            tier = 0
        readiness_bonus = {"SUPPORTED": 3, "DEFENDABLE": 2, "WEAK_EVIDENCE": 1, "UNSUPPORTED": 0}.get(readiness, 0)
        try:
            confidence = float(claim.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return (tier, readiness_bonus, confidence)

    @classmethod
    def _select_top_claims(cls, claims: list[dict], *, limit: int = 3) -> list[dict]:
        """Keep ~3 resume-writable items; drop bare UNSUPPORTED spam when better options exist.

        JD-shaped UNSUPPORTED claims without evidence stay as gaps only — never fill the
        interviewable set by falling back to invent-ownership lines.
        """
        if not claims:
            return []
        ranked = sorted(claims, key=cls._claim_priority, reverse=True)
        preferred = [claim for claim in ranked if cls._claim_priority(claim)[0] > 0]
        if preferred:
            return preferred[:limit]
        # No evidenced/writable claims: keep at most WEAK_EVIDENCE-with-text gaps, never bare UNSUPPORTED.
        soft_gaps = [
            claim
            for claim in ranked
            if str(claim.get('readiness_status') or '') != 'UNSUPPORTED' or bool(claim.get('evidence_refs'))
        ]
        return soft_gaps[:limit]

    @classmethod
    def _normalize_claims_payload(cls, data: dict) -> dict:
        data = cls._unwrap_claims_payload(data)
        raw_claims = data.get("claims") or []
        if not isinstance(raw_claims, list):
            raw_claims = []
        claims: list[dict] = []
        for item in raw_claims:
            normalized = cls._normalize_claim_item(item)
            if normalized:
                claims.append(normalized)
        return {"claims": cls._select_top_claims(claims, limit=3)}


    @staticmethod
    def _looks_like_isolated_skill_token(text: str) -> bool:
        value = (text or "").strip()
        if not value:
            return True
        if len(value) > 24:
            return False
        if any(ch.isspace() for ch in value):
            return False
        if any(ch in value for ch in "，。；、,."):
            return False
        return True

    @classmethod
    def _claims_are_skill_token_only(cls, claims: list[dict], profile_facts: list[dict[str, object]]) -> bool:
        if not claims:
            return False
        has_experience = any(str(f.get("kind") or "") in {"experience", "project"} for f in profile_facts if isinstance(f, dict))
        if not has_experience:
            return False
        return all(cls._looks_like_isolated_skill_token(str(c.get("claim") or "")) for c in claims)

    @staticmethod
    def _soft_claims_from_facts(profile_facts: list[dict[str, object]]) -> dict:
        """Deterministic soft path from confirmed profile facts — no invented evidence.

        Prefer concrete experience/project facts over isolated skill-list tokens
        (Revit / SuperMap / AutoCAD style) when project evidence exists.
        """
        facts = [fact for fact in (profile_facts or []) if isinstance(fact, dict)]
        experiences = [f for f in facts if str(f.get("kind") or "") in {"experience", "project"}]
        skills = [f for f in facts if str(f.get("kind") or "") == "skill"]
        ordered = experiences + (skills if not experiences else [])
        # If we have experiences, still allow at most one skill and only when it is long/contextual.
        if experiences:
            contextual_skills = []
            for skill in skills:
                text = str(skill.get("value") or skill.get("evidence_text") or "").strip()
                # Skip bare tool tokens (<= 24 chars, no sentence punctuation/space-heavy context)
                if len(text) <= 24 and " " not in text and "，" not in text and "," not in text:
                    continue
                contextual_skills.append(skill)
            ordered = experiences + contextual_skills[:1]

        claims: list[dict] = []
        for fact in ordered:
            kind = str(fact.get("kind") or "")
            if kind not in {"experience", "project", "skill"}:
                continue
            text = str(fact.get("value") or fact.get("evidence_text") or "").strip()
            if not text:
                continue
            fact_id = str(fact.get("id") or "").strip()
            refs: list[str] = []
            try:
                refs = [str(UUID(fact_id))]
            except Exception:
                refs = []
            claims.append({
                "claim": text[:600],
                "current_text": text[:600],
                "suggested_text": None,
                "reason": "主张分析模型输出不可用时，基于已确认项目/经历条目生成的软路径主张",
                "jd_relevance": "需对照目标 JD 能力与项目经历进一步确认相关性",
                "matched_capabilities": [],
                "evidence_refs": refs,
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.35 if kind != "skill" else 0.25,
                "risk_reason": "尚未完成完整主张分析，建议稍后重新生成",
                "attack_surface": [{"area": "PRODUCT", "risk": "准备具体例子与个人贡献说明", "evidence_refs": refs}],
            })
            if len(claims) >= 3:
                break
        return {"claims": claims}


    @staticmethod
    def _content(response: object) -> str:
        try:
            content = response.choices[0].message.content  # type: ignore[attr-defined]
        except Exception as exc:
            raise ClaimProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise ClaimProviderInvalidResponseError(reason="empty_response")
        return content

    def analyze(self, *, target_job: dict[str, object], profile_facts: list[dict[str, object]]) -> ClaimProposalPayload:
        try:
            data = json.loads(self._content(self._request(target_job, profile_facts)))
        except ClaimProviderInvalidResponseError:
            soft = self._soft_claims_from_facts(profile_facts)
            if soft.get("claims"):
                return ClaimProposalPayload.model_validate(soft)
            raise
        except json.JSONDecodeError as exc:
            soft = self._soft_claims_from_facts(profile_facts)
            if soft.get("claims"):
                return ClaimProposalPayload.model_validate(soft)
            raise ClaimProviderInvalidResponseError(reason="json_decode") from exc
        if not isinstance(data, dict):
            soft = self._soft_claims_from_facts(profile_facts)
            if soft.get("claims"):
                return ClaimProposalPayload.model_validate(soft)
            raise ClaimProviderInvalidResponseError(reason="response_shape")
        try:
            normalized = self._normalize_claims_payload(data)
            if not normalized.get("claims") or self._claims_are_skill_token_only(normalized.get("claims") or [], profile_facts):
                soft = self._soft_claims_from_facts(profile_facts)
                if soft.get("claims"):
                    return ClaimProposalPayload.model_validate(soft)
                if not normalized.get("claims"):
                    raise ClaimProviderInvalidResponseError(reason="schema_validation", validation_errors=[{"loc": ["claims"], "type": "missing"}])
            return ClaimProposalPayload.model_validate(normalized)
        except ValidationError as exc:
            soft = self._soft_claims_from_facts(profile_facts)
            if soft.get("claims"):
                return ClaimProposalPayload.model_validate(soft)
            safe_errors = [{"loc": list(error.get("loc", ())), "type": str(error.get("type", "validation_error"))} for error in exc.errors()]
            raise ClaimProviderInvalidResponseError(reason="schema_validation", validation_errors=safe_errors) from exc


_provider: ClaimAnalysisProvider | None = None


def set_claim_analysis_provider(provider: ClaimAnalysisProvider | None) -> None:
    global _provider
    _provider = provider


def get_claim_analysis_provider() -> ClaimAnalysisProvider:
    return _provider if _provider is not None else OpenAIClaimAnalysisProvider()
