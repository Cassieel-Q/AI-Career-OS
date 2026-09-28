"""Workflow state machine guards — lightweight unit tests (no live DB)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# Import from app package when running under apps/api; allow path fallback for kit smoke.
try:
    from app.mission_schemas import WorkflowState
    from app import mission_service as ms
except Exception:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.mission_schemas import WorkflowState  # type: ignore
    from app import mission_service as ms  # type: ignore


def _mission(**kwargs):
    base = dict(
        id="m1",
        workflow_state=WorkflowState.ROLE_UNDERSTOOD.value,
        resume_source=None,
        resume_strategy=None,
        status="DRAFT",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_advance_role_to_resume_required():
    m = _mission()
    ms.advance_workflow(m, "select_resume", user_confirmed=True)
    assert m.workflow_state == WorkflowState.RESUME_REQUIRED.value


def test_advance_rejects_without_user_confirm():
    m = _mission()
    with pytest.raises(HTTPException) as exc:
        ms.advance_workflow(m, "select_resume", user_confirmed=False)
    assert exc.value.status_code == 409


def test_resume_source_guard():
    m = _mission(workflow_state=WorkflowState.RESUME_STRATEGY_REQUIRED.value, resume_source=None)
    with pytest.raises(HTTPException) as exc:
        ms._require_resume_source(m)
    assert exc.value.status_code == 409
    assert "简历" in str(exc.value.detail)


def test_confirm_experiences_moves_to_strategy_required():
    m = _mission(workflow_state=WorkflowState.EXPERIENCE_SELECTION_REQUIRED.value, resume_source={"mode": "master"})
    ms.advance_workflow(m, "confirm_experiences", user_confirmed=True)
    assert m.workflow_state == WorkflowState.RESUME_STRATEGY_REQUIRED.value


def test_provider_errors_are_humanized_chinese():
    class Fake(ms.MissionProviderInvalidResponseError):
        pass

    err = ms.provider_http_error(Fake("boom"))
    assert err.status_code == 502
    assert "Mission intelligence" not in str(err.detail)
    assert "模型" in str(err.detail)


def test_workflow_enum_has_prd_states():
    required = {
        "JD_REQUIRED",
        "ROLE_UNDERSTOOD",
        "RESUME_REQUIRED",
        "RESUME_SELECTED",
        "EXPERIENCE_SELECTION_REQUIRED",
        "EXPERIENCES_CONFIRMED",
        "RESUME_STRATEGY_REQUIRED",
        "RESUME_STRATEGY_CONFIRMED",
        "TARGET_RESUME_DRAFT",
        "TARGET_RESUME_CONFIRMED",
        "STRESS_TEST_REQUIRED",
        "INTERVIEW_PREP_READY",
        "OUTCOME",
    }
    assert required.issubset({s.value for s in WorkflowState})
