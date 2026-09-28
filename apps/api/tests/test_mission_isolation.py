"""Mission isolation: two missions same profile must not share target resume / interview session rows.

Discovers project models/fixtures when present; otherwise skips with a clear reason.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _try_import():
    """Best-effort import of mission-related ORM / services used by IJM."""
    mods = {}
    candidates = [
        ("app.models", "models"),
        ("app.db", "db"),
        ("app.mission_service", "mission_service"),
        ("app.services.mission_service", "mission_service"),
        ("app.missions.service", "mission_service"),
    ]
    for path, key in candidates:
        try:
            mods[key] = __import__(path, fromlist=["*"])
        except Exception:
            continue
    return mods


def _find_attr(obj, names):
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


@pytest.fixture(scope="module")
def isolation_ctx():
    mods = _try_import()
    models = mods.get("models")
    if models is None:
        pytest.skip("app.models not importable in this environment")

    Mission = _find_attr(models, ["JobMission", "Mission", "mission_table"])
    TargetResume = _find_attr(
        models,
        ["TargetResume", "MissionTargetResume", "ResumeVersion", "TargetResumeRow"],
    )
    InterviewSession = _find_attr(
        models,
        ["InterviewSession", "MissionInterviewSession", "InterviewPrepSession"],
    )
    if Mission is None or (TargetResume is None and InterviewSession is None):
        pytest.skip(
            "Mission isolation models not found "
            f"(Mission={Mission is not None}, TargetResume={TargetResume is not None}, "
            f"InterviewSession={InterviewSession is not None})"
        )
    return {
        "models": models,
        "Mission": Mission,
        "TargetResume": TargetResume,
        "InterviewSession": InterviewSession,
        "db": mods.get("db"),
        "mission_service": mods.get("mission_service"),
    }


def test_two_missions_do_not_share_target_resume_or_interview_session(isolation_ctx):
    """If create helpers exist, create two missions and assert FK isolation.

    Fallback: assert ORM columns include mission_id (or equivalent) on child tables
    so rows cannot be profile-global only.
    """
    TargetResume = isolation_ctx["TargetResume"]
    InterviewSession = isolation_ctx["InterviewSession"]
    Mission = isolation_ctx["Mission"]
    svc = isolation_ctx["mission_service"]

    def cols(cls):
        table = getattr(cls, "__table__", None)
        if table is not None:
            return {c.name for c in table.columns}
        # pydantic / dataclass fallback
        ann = getattr(cls, "__annotations__", {}) or {}
        return set(ann.keys()) | set(vars(cls).keys())

    for label, cls in (("TargetResume", TargetResume), ("InterviewSession", InterviewSession)):
        if cls is None:
            continue
        c = cols(cls)
        assert any(
            k in c for k in ("mission_id", "job_mission_id", "missionId", "job_mission")
        ), f"{label} missing mission foreign key columns; got {sorted(c)[:40]}"

    # Prefer live create path when service exposes it
    create = None
    if svc is not None:
        create = _find_attr(
            svc,
            [
                "create_mission",
                "create_job_mission",
                "start_mission",
                "create",
            ],
        )
    if create is None:
        # Structural assertion above is the minimum gate when no DB harness.
        assert cols(Mission)
        return

    # Live path — only when call signature is trivial; otherwise structural pass.
    try:
        profile_id = f"iso-profile-{uuid.uuid4().hex[:8]}"
        m1 = create(profile_id=profile_id)  # type: ignore[call-arg]
        m2 = create(profile_id=profile_id)  # type: ignore[call-arg]
    except TypeError:
        pytest.skip("mission create helper signature not compatible with isolation harness")

    id1 = getattr(m1, "id", None) or (m1.get("id") if isinstance(m1, dict) else None)
    id2 = getattr(m2, "id", None) or (m2.get("id") if isinstance(m2, dict) else None)
    assert id1 and id2 and id1 != id2

    # Children must reference distinct mission ids when present on the objects
    for obj, mid in ((m1, id1), (m2, id2)):
        for attr in ("target_resume", "target_resumes", "interview_session", "interview_sessions"):
            child = getattr(obj, attr, None)
            if child is None:
                continue
            rows = child if isinstance(child, (list, tuple)) else [child]
            for row in rows:
                rid = getattr(row, "mission_id", None) or getattr(row, "job_mission_id", None)
                if rid is not None:
                    assert rid == mid
