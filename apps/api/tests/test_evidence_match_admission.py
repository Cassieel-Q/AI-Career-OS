"""单岗位匹配度：五类结论 + 准入建议 + 参考分（方案 B）。

单元级直接验证 `_admission_recommendation` / `_ref_score` 的判定规则，
集成级走真实 HTTP 路由确认 `run_match` 把新字段透出。
"""
from __future__ import annotations

from types import SimpleNamespace

from app.evidence_os.enums import MatchStatus, RequirementPriority
from app.evidence_os.service import _admission_recommendation, _ref_score


def _row(match_status: str, requirement_id: str = "r1"):
    return SimpleNamespace(requirement_id=requirement_id, match_status=match_status)


def _req(priority: str, requirement_id: str = "r1", raw_text: str = "需要 RAG 检索质量经验"):
    return SimpleNamespace(id=requirement_id, priority=priority, raw_text=raw_text)


def _admission(rows, reqs):
    return _admission_recommendation(rows, {r.id: r for r in reqs})[0]


# --- 准入建议 ---------------------------------------------------------------

def test_hard_gate_missing_advises_against_applying():
    rows = [_row(MatchStatus.MISSING)]
    reqs = [_req(RequirementPriority.HARD_GATE)]
    admission, reason = _admission_recommendation(rows, {r.id: r for r in reqs})
    assert admission == "do_not_apply"
    assert "硬性要求未证实" in reason


def test_hard_gate_needs_excavation_also_advises_against_applying():
    """引擎对 hard_gate 未命中产出的是 needs_excavation，不是 missing。"""
    rows = [_row(MatchStatus.NEEDS_EXCAVATION)]
    reqs = [_req(RequirementPriority.HARD_GATE)]
    assert _admission(rows, reqs) == "do_not_apply"


def test_unproven_core_requirement_asks_to_confirm_first():
    rows = [_row(MatchStatus.MISSING)]
    reqs = [_req(RequirementPriority.CORE)]
    admission, reason = _admission_recommendation(rows, {r.id: r for r in reqs})
    assert admission == "confirm"
    assert "核心要求未证实" in reason


def test_weak_match_alone_asks_to_confirm_first():
    rows = [_row(MatchStatus.WEAK)]
    reqs = [_req(RequirementPriority.CORE)]
    assert _admission(rows, reqs) == "confirm"


def test_preferred_and_noise_gaps_do_not_block_application():
    rows = [_row(MatchStatus.MISSING, "r1"), _row(MatchStatus.MISSING, "r2")]
    reqs = [
        _req(RequirementPriority.PREFERRED, "r1"),
        _req(RequirementPriority.NOISE, "r2"),
    ]
    assert _admission(rows, reqs) == "can_apply"


def test_all_covered_is_can_apply():
    rows = [_row(MatchStatus.COVERED, "r1"), _row(MatchStatus.COVERED, "r2")]
    reqs = [
        _req(RequirementPriority.HARD_GATE, "r1"),
        _req(RequirementPriority.CORE, "r2"),
    ]
    admission, reason = _admission_recommendation(rows, {r.id: r for r in reqs})
    assert admission == "can_apply"
    assert "均已匹配" in reason


def test_hard_gate_gap_outranks_core_gap():
    rows = [_row(MatchStatus.MISSING, "r1"), _row(MatchStatus.MISSING, "r2")]
    reqs = [
        _req(RequirementPriority.HARD_GATE, "r1"),
        _req(RequirementPriority.CORE, "r2"),
    ]
    assert _admission(rows, reqs) == "do_not_apply"


# --- 参考分 -----------------------------------------------------------------

def test_ref_score_weights_covered_full_and_weak_half():
    rows = [
        _row(MatchStatus.COVERED, "r1"),
        _row(MatchStatus.COVERED, "r2"),
        _row(MatchStatus.COVERED, "r3"),
        _row(MatchStatus.WEAK, "r4"),
        _row(MatchStatus.MISSING, "r5"),
    ]
    reqs = [
        _req(RequirementPriority.HARD_GATE, "r1"),
        _req(RequirementPriority.HARD_GATE, "r2"),
        _req(RequirementPriority.CORE, "r3"),
        _req(RequirementPriority.PREFERRED, "r4"),
        _req(RequirementPriority.NICE_TO_HAVE, "r5"),
    ]
    score, breakdown = _ref_score(rows, reqs)
    assert score == 70  # (3 + 0.5) / 5
    assert [item["name"] for item in breakdown] == ["技能/关键词覆盖", "硬性/核心门槛"]
    assert "未证实 0 条" in breakdown[1]["detail"]


def test_ref_score_zero_when_nothing_matches():
    rows = [_row(MatchStatus.NEEDS_EXCAVATION, "r1")]
    reqs = [_req(RequirementPriority.HARD_GATE, "r1")]
    score, breakdown = _ref_score(rows, reqs)
    assert score == 0
    assert "未证实 1 条" in breakdown[1]["detail"]


def test_ref_score_survives_empty_requirement_list():
    score, _ = _ref_score([], [])
    assert score == 0


# --- 集成：真实路由 ---------------------------------------------------------

def _ingest_jd(client, profile_id, raw_text):
    response = client.post(
        f"/evidence-os/profiles/{profile_id}/jds",
        json={"title": "目标岗位", "raw_text": raw_text, "language": "en"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_match_response_exposes_admission_and_ref_score(client, persisted_profile):
    jd = _ingest_jd(
        client,
        persisted_profile.id,
        "Must have hands-on RAG retrieval quality experience\n"
        "Own offline evaluation harness for LLM agents",
    )
    response = client.post(f"/evidence-os/profiles/{persisted_profile.id}/jds/{jd['id']}/match")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["admission"] in {"can_apply", "confirm", "do_not_apply", "pending"}
    assert isinstance(body["ref_score"], int) and 0 <= body["ref_score"] <= 100
    assert body["admission_reason"]
    assert body["ref_score_breakdown"]
    assert "ATS" in body["disclaimer"]
    assert len(body["rows"]) == len(jd["requirements"])


def test_no_claims_against_hard_gate_jd_advises_against_applying(client, persisted_profile):
    jd = _ingest_jd(
        client,
        persisted_profile.id,
        "必须 具备 RAG 检索质量经验\n"
        "负责搭建离线评测体系并持续优化效果\n"
        "Nice to have 设计感",
    )
    body = client.post(f"/evidence-os/profiles/{persisted_profile.id}/jds/{jd['id']}/match").json()

    assert body["admission"] == "do_not_apply"
    assert body["ref_score"] == 0
    assert body["needs_excavation"] >= 1


def test_confirmed_claim_covering_all_core_requirements_can_apply(client, persisted_profile):
    profile_id = persisted_profile.id
    evidence = client.post(
        f"/evidence-os/profiles/{profile_id}/evidence",
        json={"fact_text": "在 Acme 负责 RAG 检索质量与离线评测体系", "evidence_type": "user_confirmed", "source_ids": []},
    )
    assert evidence.status_code == 200, evidence.text
    claim = client.post(
        f"/evidence-os/profiles/{profile_id}/claims",
        json={
            "source_fact": "在 Acme 负责 RAG 检索质量与离线评测体系",
            "candidate_wording": "Built the offline eval harness for RAG retrieval quality in agent workflows",
            "verification_status": "confirmed",
            "responsibility_level": "owned_module",
            "boundary": "仅限本人负责的模块交付。",
            "evidence_ids": [evidence.json()["id"]],
            "competency_ids": ["rag", "model_evaluation", "agents"],
        },
    )
    assert claim.status_code == 200, claim.text

    jd = _ingest_jd(
        client,
        profile_id,
        "Must have hands-on RAG retrieval quality experience\n"
        "Own offline evaluation harness for LLM agents",
    )
    body = client.post(f"/evidence-os/profiles/{profile_id}/jds/{jd['id']}/match").json()

    assert body["covered"] == 2
    assert body["admission"] == "can_apply"
    assert body["ref_score"] == 100
