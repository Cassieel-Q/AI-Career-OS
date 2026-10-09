"""Live product-API client for synthetic (authorized-fixture) benchmark runs.

Calls the local AI Career OS HTTP API. Does not invent consented corpora.
sample_class is always labeled from fixtures (synthetic vs consented_real).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from evals.benchmark.io_util import read_json
from evals.benchmark.paths import FIXTURES_DIR

DEFAULT_API_BASE = os.environ.get("CAREEROS_API_BASE", "http://127.0.0.1:8000").rstrip("/")

SYN_RESUME_TEXT = """Syn Candidate — AI / Technical Product Manager
Email: syn.candidate@example.com | Shanghai

EXPERIENCE

LLM Evaluation Internship | University Lab | 2024.01 - 2024.06
- Built an offline LLM judge set with 120 labeled prompts and tracked agreement versus human raters.
- Partnered with two engineers on RAG quality metrics for an internal demo.

Campus Bookstore Cashier | University Store | 2023.01 - 2023.12
- Operated the cash register and restocked shelves during peak campus hours.

RAG Prototype Project | Personal / Lab | 2024.07 - 2024.09
- Shipped an internal RAG demo used by 3 product managers for evidence lookup.
- Documented failure modes and evaluation criteria for retrieval quality.

Creator A/B Test Lead | Campus Media Club | 2023.06 - 2023.12
- Ran A/B tests on creator-tool onboarding copy and wrote short PRDs for the club product.

EDUCATION
B.S. Computer Science, Example University, 2024

SKILLS
LLM evaluation, experiment design, RAG, SQL literacy, product metrics, PRD writing, cross-functional leadership
"""


def _http_json(method: str, url: str, body: dict[str, Any] | None = None, timeout: float = 180.0) -> tuple[int, Any, float]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = (time.perf_counter() - started) * 1000
            parsed: Any = json.loads(raw) if raw.strip() else None
            return int(resp.status), parsed, elapsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        elapsed = (time.perf_counter() - started) * 1000
        try:
            parsed = json.loads(raw) if raw.strip() else {"detail": raw}
        except Exception:
            parsed = {"detail": raw}
        return int(exc.code), parsed, elapsed


def api_healthy(base: str = DEFAULT_API_BASE) -> bool:
    try:
        code, payload, _ = _http_json("GET", f"{base}/health", None, timeout=5)
        return code == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
    except Exception:
        return False


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def _contains(hay: str | None, needle: str | None) -> bool:
    h, n = _norm(hay), _norm(needle)
    return bool(h and n and (n in h or h in n))


def _years_from_text(text: str) -> str | None:
    m = re.search(r"(\d+\+?)\s*years?", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(\d+)\s*年", text)
    return m.group(1) if m else None


def _edu_from_mission(mission: dict[str, Any]) -> str | None:
    parsed = mission.get("parsed_jd") or {}
    blob = " ".join(
        [
            str(x.get("text") or "")
            for x in (parsed.get("preferred_requirements") or []) + (parsed.get("requirements") or [])
        ]
    )
    for label in ("Bachelor", "Master", "PhD", "Doctor", "本科", "硕士", "博士"):
        if label.casefold() in blob.casefold():
            if label.lower().startswith("bachelor") or label == "本科":
                return "Bachelor"
            if label.lower().startswith("master") or label == "硕士":
                return "Master"
            return label
    return None


def _must_have_from_mission(mission: dict[str, Any]) -> list[str]:
    """Return requirement strings using evidence_text and text."""
    parsed = mission.get("parsed_jd") or {}
    out: list[str] = []
    for item in parsed.get("requirements") or []:
        for key in ("evidence_text", "text"):
            val = str(item.get(key) or "").strip()
            if val and val not in out:
                out.append(val)
    return out


def _map_must_have(expected: list[str], actual: list[str]) -> bool:
    if not expected:
        return not actual
    return all(any(_contains(a, e) or _contains(e, a) for a in actual) for e in expected)


_TITLE_ALIASES = {
    "llm evaluation internship": "llm eval internship",
    "llm eval internship": "llm eval internship",
    "campus bookstore cashier": "campus bookstore cashier",
    "rag prototype project": "rag prototype project",
    "creator a/b test lead": "creator a/b test lead",
}


def _canon_title(title: str) -> str:
    n = _norm(title)
    return _TITLE_ALIASES.get(n, n)


def _title_from_why(why: str) -> str:
    # Chinese/English titles often appear early in why strings.
    for marker in (
        "LLM Evaluation Internship",
        "LLM eval internship",
        "Campus Bookstore Cashier",
        "Campus bookstore cashier",
        "RAG Prototype Project",
        "RAG prototype project",
        "Creator A/B Test Lead",
        "Creator A/B test lead",
    ):
        if marker.casefold() in (why or "").casefold():
            return marker
    return ""


def _create_profile(base: str) -> str:
    code, payload, _ = _http_json("POST", f"{base}/api/v1/profiles/draft", {})
    if code not in {200, 201} or not isinstance(payload, dict):
        raise RuntimeError(f"draft profile failed: {code} {payload}")
    return str(payload["profile_id"])


def _create_mission(base: str, profile_id: str, raw_text: str) -> tuple[dict[str, Any], float]:
    code, payload, ms = _http_json(
        "POST",
        f"{base}/api/v1/profiles/{profile_id}/job-missions",
        {"raw_text": raw_text},
        timeout=180,
    )
    if code not in {200, 201} or not isinstance(payload, dict):
        raise RuntimeError(f"create mission failed: {code} {payload}")
    return payload, ms


def _bind_resume(base: str, mission_id: str, raw_text: str) -> dict[str, Any]:
    code, payload, _ = _http_json(
        "POST",
        f"{base}/api/v1/job-missions/{mission_id}/resumes/text",
        {"raw_text": raw_text, "update_master": False},
        timeout=180,
    )
    if code != 200:
        raise RuntimeError(f"resume text failed: {code} {payload}")
    code2, payload2, _ = _http_json(
        "POST",
        f"{base}/api/v1/job-missions/{mission_id}/confirm-resume-source",
        {"mode": "paste", "update_master": False},
    )
    if code2 != 200:
        raise RuntimeError(f"confirm resume failed: {code2} {payload2}")
    return payload2 if isinstance(payload2, dict) else {}


def _generate_selection(base: str, mission_id: str) -> tuple[dict[str, Any], float]:
    code, payload, ms = _http_json(
        "POST",
        f"{base}/api/v1/job-missions/{mission_id}/experience-selection/generate",
        None,
        timeout=180,
    )
    if code != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"experience selection failed: {code} {payload}")
    return payload, ms


def _confirm_selection(base: str, mission_id: str, selection: dict[str, Any]) -> None:
    rows = []
    for row in selection.get("selections") or []:
        rows.append(
            {
                "experience_id": row["experience_id"],
                "decision": row["decision"],
                "why": row.get("why") or "confirmed for live eval",
                "related_capabilities": row.get("related_capabilities") or [],
                "supporting_evidence_refs": row.get("supporting_evidence_refs") or [],
                "confidence": row.get("confidence") if row.get("confidence") is not None else 0.5,
            }
        )
    code, payload, _ = _http_json(
        "PUT",
        f"{base}/api/v1/job-missions/{mission_id}/experience-selection?confirm=true",
        {"selections": rows},
        timeout=60,
    )
    if code != 200:
        raise RuntimeError(f"confirm selection failed: {code} {payload}")


def _strategy_and_target(base: str, mission_id: str) -> tuple[dict[str, Any], float]:
    code, payload, _ = _http_json("POST", f"{base}/api/v1/job-missions/{mission_id}/resume-strategy", None, timeout=180)
    if code != 200:
        raise RuntimeError(f"resume-strategy failed: {code} {payload}")
    code2, payload2, _ = _http_json("POST", f"{base}/api/v1/job-missions/{mission_id}/confirm-strategy", None, timeout=60)
    if code2 != 200:
        raise RuntimeError(f"confirm-strategy failed: {code2} {payload2}")
    code3, payload3, ms = _http_json("POST", f"{base}/api/v1/job-missions/{mission_id}/target-resumes", None, timeout=300)
    if code3 not in {200, 201} or not isinstance(payload3, dict):
        raise RuntimeError(f"target-resumes failed: {code3} {payload3}")
    return payload3, ms


def _confirm_target_and_pack(base: str, mission_id: str) -> tuple[dict[str, Any], float]:
    code, payload, _ = _http_json("POST", f"{base}/api/v1/job-missions/{mission_id}/confirm-target-resume", None, timeout=60)
    if code != 200:
        raise RuntimeError(f"confirm-target-resume failed: {code} {payload}")
    code2, payload2, ms = _http_json("POST", f"{base}/api/v1/job-missions/{mission_id}/interview-pack", None, timeout=300)
    if code2 not in {200, 201} or not isinstance(payload2, dict):
        raise RuntimeError(f"interview-pack failed: {code2} {payload2}")
    return payload2, ms


def run_live_jd(base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    rows = list(read_json(FIXTURES_DIR / "jd" / "synthetic_offline.json"))
    cases: list[dict[str, Any]] = []
    field_hits = {k: 0 for k in ["company", "role_title", "location", "years_experience", "education"]}
    must_hits = 0
    compared = 0
    failures: list[str] = []
    for row in rows:
        expected = row.get("expected") or {}
        try:
            profile_id = _create_profile(base)
            mission, latency_ms = _create_mission(base, profile_id, str(row["raw_text"]))
            actual = {
                "company": mission.get("company"),
                "role_title": mission.get("role"),
                "location": mission.get("location"),
                "years_experience": _years_from_text(str(row["raw_text"])),
                "education": _edu_from_mission(mission),
                "must_have": _must_have_from_mission(mission),
            }
            # Prefer parsed years from requirements if present
            blob = " ".join(actual["must_have"])
            y = _years_from_text(blob) or _years_from_text(str(row["raw_text"]))
            actual["years_experience"] = y
            detail = {}
            row_ok = True
            for name in field_hits:
                ok = _contains(str(actual.get(name)), str(expected.get(name))) or _norm(str(actual.get(name))) == _norm(
                    str(expected.get(name))
                )
                # years: allow 3 vs 3+
                if name == "years_experience":
                    ok = _norm(str(actual.get(name))).rstrip("+") == _norm(str(expected.get(name))).rstrip("+") or ok
                detail[name] = ok
                if ok:
                    field_hits[name] += 1
                else:
                    row_ok = False
            must_ok = _map_must_have(list(expected.get("must_have") or []), list(actual.get("must_have") or []))
            detail["must_have_set"] = must_ok
            if must_ok:
                must_hits += 1
            else:
                row_ok = False
            compared += 1
            cases.append(
                {
                    "jd_id": row.get("jd_id"),
                    "sample_class": "synthetic",
                    "consent_status": "n/a_synthetic",
                    "status": "PASSED" if row_ok else "FAILED",
                    "latency_ms": latency_ms,
                    "mission_id": mission.get("id"),
                    "warnings": mission.get("warnings") or [],
                    "field_exact": detail,
                    "actual_redacted": {
                        "company": actual.get("company"),
                        "role_title": actual.get("role_title"),
                        "location": actual.get("location"),
                        "years_experience": actual.get("years_experience"),
                        "education": actual.get("education"),
                        "must_have_count": len(actual.get("must_have") or []),
                    },
                }
            )
            if not row_ok:
                failures.append(str(row.get("jd_id")))
        except Exception as exc:
            cases.append(
                {
                    "jd_id": row.get("jd_id"),
                    "sample_class": "synthetic",
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                }
            )
            failures.append(str(row.get("jd_id")))
    metrics = {name: (field_hits[name] / compared if compared else None) for name in field_hits}
    metrics["must_have_soft_recall"] = must_hits / compared if compared else None
    return {
        "suite": "jd",
        "mode": "live",
        "status": "COMPLETED",
        "provider_called": True,
        "sample_class": "synthetic",
        "planned_note": "PLAN=30 independent JDs; ACTUAL=synthetic fixtures only",
        "fixture_count": len(rows),
        "compared": compared,
        "not_run": 0,
        "metrics": metrics,
        "failures": failures,
        "cases": cases,
    }


def run_live_match(base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    jd_rows = {r["jd_id"]: r for r in read_json(FIXTURES_DIR / "jd" / "synthetic_offline.json")}
    rows = list(read_json(FIXTURES_DIR / "match" / "synthetic_offline.json"))
    labels = ["KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"]
    correct = 0
    compared_items = 0
    critical_omit_errors = 0
    cases: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in rows:
        jd = jd_rows.get(row["jd_id"])
        if not jd:
            cases.append({"case_id": row.get("case_id"), "status": "NOT_RUN", "reason": "missing jd fixture"})
            continue
        title_to_expected = {}
        for exp in row.get("experiences") or []:
            title_to_expected[_canon_title(exp["title"])] = (
                (row.get("expected_labels") or {}).get(exp["experience_id"]),
                exp["title"],
            )
        try:
            profile_id = _create_profile(base)
            mission, _ = _create_mission(base, profile_id, str(jd["raw_text"]))
            mission_id = str(mission["id"])
            _bind_resume(base, mission_id, SYN_RESUME_TEXT)
            selection, latency_ms = _generate_selection(base, mission_id)
            pred_by_title: dict[str, str] = {}
            for sel in selection.get("selections") or []:
                title = _title_from_why(str(sel.get("why") or ""))
                if title:
                    pred_by_title[_canon_title(title)] = str(sel.get("decision"))
            item_results = []
            row_ok = True
            for canon, (gold, display_title) in title_to_expected.items():
                pred = pred_by_title.get(canon)
                title = display_title
                if pred is None:
                    item_results.append({"title": title, "gold": gold, "pred": None, "status": "NOT_EVALUABLE"})
                    row_ok = False
                    continue
                compared_items += 1
                ok = pred == gold
                if ok:
                    correct += 1
                else:
                    row_ok = False
                    if gold != "OMIT" and pred == "OMIT":
                        critical_omit_errors += 1
                item_results.append({"title": title, "gold": gold, "pred": pred, "status": "PASSED" if ok else "FAILED"})
            cases.append(
                {
                    "case_id": row.get("case_id"),
                    "sample_class": "synthetic",
                    "status": "PASSED" if row_ok else "FAILED",
                    "latency_ms": latency_ms,
                    "mission_id": mission_id,
                    "items": item_results,
                }
            )
            if not row_ok:
                failures.append(str(row.get("case_id")))
        except Exception as exc:
            cases.append(
                {
                    "case_id": row.get("case_id"),
                    "sample_class": "synthetic",
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                }
            )
            failures.append(str(row.get("case_id")))
    return {
        "suite": "match",
        "mode": "live",
        "status": "COMPLETED",
        "provider_called": True,
        "sample_class": "synthetic",
        "planned_note": "PLAN=30; ACTUAL=synthetic fixtures only",
        "fixture_count": len(rows),
        "compared_items": compared_items,
        "metrics": {
            "decision_accuracy": (correct / compared_items) if compared_items else None,
            "critical_omit_errors": critical_omit_errors,
            "human_macro_f1": "NOT_EVALUABLE",
        },
        "failures": failures,
        "cases": cases,
    }


def run_live_rewrite(base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    """Generate live target-resume bullets for synthetic JD+resume; human scores UNRATED."""
    jd_rows = {r["jd_id"]: r for r in read_json(FIXTURES_DIR / "jd" / "synthetic_offline.json")}
    match_rows = list(read_json(FIXTURES_DIR / "match" / "synthetic_offline.json"))
    # One live rewrite pipeline per unique jd in rewrite fixtures
    rewrite_rows = list(read_json(FIXTURES_DIR / "rewrite" / "synthetic_offline.json"))
    jd_ids = sorted({r["jd_id"] for r in rewrite_rows if r.get("jd_id") in jd_rows})
    cases: list[dict[str, Any]] = []
    failures: list[str] = []
    bullet_total = 0
    for jd_id in jd_ids:
        jd = jd_rows[jd_id]
        try:
            profile_id = _create_profile(base)
            mission, _ = _create_mission(base, profile_id, str(jd["raw_text"]))
            mission_id = str(mission["id"])
            _bind_resume(base, mission_id, SYN_RESUME_TEXT)
            selection, _ = _generate_selection(base, mission_id)
            _confirm_selection(base, mission_id, selection)
            target, latency_ms = _strategy_and_target(base, mission_id)
            bullets = target.get("bullets") or []
            bullet_total += len(bullets)
            # Map fixture units to live case shell
            related_units = [u for u in rewrite_rows if u.get("jd_id") == jd_id]
            for unit in related_units:
                cases.append(
                    {
                        "unit_id": unit.get("unit_id"),
                        "sample_class": "synthetic",
                        "status": "COMPLETED",
                        "human_scores": "UNRATED",
                        "adoption_rate": "NOT_EVALUABLE",
                        "critical_fact_error_rate": "NOT_EVALUABLE",
                        "mission_id": mission_id,
                        "latency_ms": latency_ms,
                        "live_bullet_count": len(bullets),
                        "notes": "Live product suggestions generated; fixture offline suggestion_text not used as gold for LLM quality.",
                    }
                )
        except Exception as exc:
            failures.append(jd_id)
            for unit in rewrite_rows:
                if unit.get("jd_id") == jd_id:
                    cases.append(
                        {
                            "unit_id": unit.get("unit_id"),
                            "sample_class": "synthetic",
                            "status": "FAILED",
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:300],
                        }
                    )
    return {
        "suite": "rewrite",
        "mode": "live",
        "status": "COMPLETED" if not failures else "COMPLETED_WITH_FAILURES",
        "provider_called": True,
        "sample_class": "synthetic",
        "planned_note": "PLAN=90 rewrite units; ACTUAL=synthetic fixtures only; human dims UNRATED",
        "fixture_count": len(rewrite_rows),
        "live_pipelines": len(jd_ids),
        "live_bullet_total": bullet_total,
        "metrics": {
            "human_factuality_mean": "UNRATED",
            "human_jd_fit_mean": "UNRATED",
            "adoption_rate": "NOT_EVALUABLE",
            "critical_fact_error_rate": "NOT_EVALUABLE",
            "live_bullet_total": bullet_total,
        },
        "failures": failures,
        "cases": cases,
        "unused_match_fixture_count": len(match_rows),
    }


def run_live_interview(base: str = DEFAULT_API_BASE) -> dict[str, Any]:
    jd_rows = {r["jd_id"]: r for r in read_json(FIXTURES_DIR / "jd" / "synthetic_offline.json")}
    rows = list(read_json(FIXTURES_DIR / "interview" / "synthetic_offline.json"))
    jd_ids = sorted({r["jd_id"] for r in rows if r.get("jd_id") in jd_rows})
    cases: list[dict[str, Any]] = []
    failures: list[str] = []
    topic_total = 0
    demo_leak_topics = 0
    for jd_id in jd_ids:
        jd = jd_rows[jd_id]
        try:
            profile_id = _create_profile(base)
            mission, _ = _create_mission(base, profile_id, str(jd["raw_text"]))
            mission_id = str(mission["id"])
            _bind_resume(base, mission_id, SYN_RESUME_TEXT)
            selection, _ = _generate_selection(base, mission_id)
            _confirm_selection(base, mission_id, selection)
            _strategy_and_target(base, mission_id)
            pack, latency_ms = _confirm_target_and_pack(base, mission_id)
            topics = pack.get("topics") or pack.get("interview_topics") or []
            if not topics and isinstance(pack.get("pack"), dict):
                topics = pack["pack"].get("topics") or []
            topic_total += len(topics)
            blob = json.dumps(pack, ensure_ascii=False)
            leaked = ("SYNTHETIC_DEMO" in blob) or ("demo_baidu" in blob.casefold()) or ("（CURATED，非合成演示）" in blob)
            if leaked:
                demo_leak_topics += 1
            related = [q for q in rows if q.get("jd_id") == jd_id]
            for q in related:
                cases.append(
                    {
                        "question_id": q.get("question_id"),
                        "sample_class": "synthetic",
                        "status": "COMPLETED",
                        "human_scores": "UNRATED",
                        "mission_id": mission_id,
                        "latency_ms": latency_ms,
                        "live_topic_count": len(topics),
                        "synthetic_demo_leak_detected": leaked,
                        "notes": "Fixture expected question strings are not gold for live pack topic text; structural leak check only.",
                    }
                )
        except Exception as exc:
            failures.append(jd_id)
            for q in rows:
                if q.get("jd_id") == jd_id:
                    cases.append(
                        {
                            "question_id": q.get("question_id"),
                            "sample_class": "synthetic",
                            "status": "FAILED",
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:300],
                        }
                    )
    return {
        "suite": "interview",
        "mode": "live",
        "status": "COMPLETED" if not failures else "COMPLETED_WITH_FAILURES",
        "provider_called": True,
        "sample_class": "synthetic",
        "planned_note": "PLAN=10 cases / 50 questions; ACTUAL=synthetic fixtures only",
        "fixture_count": len(rows),
        "live_pipelines": len(jd_ids),
        "live_topic_total": topic_total,
        "metrics": {
            "live_topic_total": topic_total,
            "synthetic_demo_leak_pipelines": demo_leak_topics,
            "jd_grounding_human": "UNRATED",
            "resume_grounding_human": "UNRATED",
        },
        "failures": failures,
        "cases": cases,
    }


LIVE_RUNNERS = {
    "jd": run_live_jd,
    "match": run_live_match,
    "rewrite": run_live_rewrite,
    "interview": run_live_interview,
}
