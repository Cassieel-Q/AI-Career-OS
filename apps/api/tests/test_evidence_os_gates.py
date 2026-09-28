"""Unit tests for Evidence OS product gates (no DB required)."""
from __future__ import annotations

import pytest

# Allow importing from apps/api when tests run from repo root or apps/api
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.evidence_os import gates


def test_metric_estimate_forbidden_en():
    with pytest.raises(gates.GateViolation) as ei:
        gates.assert_no_metric_estimate("Grew revenue roughly 30% YoY")
    assert ei.value.code == "METRIC_ESTIMATE_FORBIDDEN"


def test_metric_estimate_forbidden_cn():
    with pytest.raises(gates.GateViolation):
        gates.assert_no_metric_estimate("用户增长大概 20%")


def test_metric_must_be_confirmed():
    with pytest.raises(gates.GateViolation) as ei:
        gates.assert_metric_confirmed({"value": 12, "unit": "%", "source_confirmed": False})
    assert ei.value.code == "METRIC_NOT_CONFIRMED"
    gates.assert_metric_confirmed({"value": 12, "unit": "%", "source_confirmed": True})


def test_confirm_without_evidence_blocked():
    with pytest.raises(gates.GateViolation) as ei:
        gates.assert_claim_confirmable({"verification_status": "confirmed", "evidence_ids": []})
    assert ei.value.code == "CONFIRM_WITHOUT_EVIDENCE"


def test_filter_confirmed_only():
    class C:
        def __init__(self, s):
            self.verification_status = s
    got = gates.filter_confirmed_only([C("pending"), C("confirmed"), C("rejected")])
    assert len(got) == 1
    assert got[0].verification_status == "confirmed"


def test_final_bullets_require_confirmed():
    class Claim:
        def __init__(self, status):
            self.verification_status = status
    blockers = gates.assert_final_uses_confirmed_only(
        [{"claim_id": "a"}, {"claim_id": "b"}],
        {"a": Claim("confirmed"), "b": Claim("pending")},
    )
    assert any("pending" in b for b in blockers)


def test_approval_hash_mismatch():
    text = "hello resume"
    h = gates.hash_text(text)
    with pytest.raises(gates.GateViolation) as ei:
        gates.assert_approval_hash(h, "deadbeef", text)
    assert ei.value.code == "HASH_MISMATCH"
    gates.assert_approval_hash(h, h, text)


def test_render_requires_approval():
    with pytest.raises(gates.GateViolation) as ei:
        gates.assert_render_allowed("draft", False, True)
    assert ei.value.code == "APPROVAL_REQUIRED"
    gates.assert_render_allowed("approved", True, True)


def test_ats_pass_claim_forbidden():
    with pytest.raises(gates.GateViolation) as ei:
        gates.assert_no_ats_pass_claim("This resume will pass ATS with 92% probability")
    assert ei.value.code == "ATS_PASS_CLAIM_FORBIDDEN"


def test_sanitize_eval_label_is_heuristic():
    label = gates.sanitize_eval_label("keyword_coverage", 0.8)
    assert label.startswith("heuristic_")
    assert "pass" not in label.lower()
