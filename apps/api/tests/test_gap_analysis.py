import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from app import models
from app import gap_service
from app.gap_provider import OpenAIGapAnalysisProvider, set_gap_analysis_provider
from app.gap_schemas import GapProposal, GapProposalPayload, GapState
from app.jd_analysis_provider import set_jd_analysis_provider
from app.jd_analysis_schemas import JdExtraction, JdExtractionItem, JdExtractionPayload, RequirementCategory
from app.market_profile_service import market_profile_capabilities
from app.role_exploration_schemas import RoleCode
from app.target_role_service import select_target_role
from test_target_role_service import _ready_profile


class JdProvider:
    def analyze(self, *, target_role, job_descriptions):
        return JdExtractionPayload(items=[JdExtraction(jd_id=UUID(row["id"]), items=[JdExtractionItem(name="Python", category=RequirementCategory.SKILL, evidence_text="Python")]) for row in job_descriptions])


def _target(db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)
    return select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)


def _ready_market(client, target):
    for index in range(3):
        assert client.post(f"/api/v1/target-roles/{target.id}/job-descriptions", json={"raw_text": f"Use Python in JD {index}"}).status_code == 201
    set_jd_analysis_provider(JdProvider())
    try:
        response = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    finally:
        set_jd_analysis_provider(None)
    assert response.status_code == 200, response.text


def test_gap_analysis_requires_current_market_profile(client, db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)
    response = client.post(f"/api/v1/profiles/{persisted_profile.id}/gap-analysis")
    assert response.status_code == 409
    assert "target role" in response.json()["detail"]


def test_gap_analysis_uses_confirmed_profile_and_allowed_states(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _ready_market(client, target)
    market = db_session.query(models.MarketProfile).one()
    requirement = market.requirements[0]

    class Provider:
        def compare(self, *, requirements, profile_facts):
            assert len(requirements) == 1
            assert requirements[0]["atomic_requirement_ids"]
            assert requirements[0]["source_jd_count"] == 3
            return GapProposalPayload(items=[GapProposal(
                requirement_id=requirement.id,
                state=GapState.PARTIAL,
                severity="HIGH",
                proximity="MEDIUM",
                feasibility="HIGH",
                rationale="Python is present but proficiency is not confirmed.",
                evidence_refs=[persisted_profile.skills[0].id],
            )])

    set_gap_analysis_provider(Provider())
    try:
        response = client.post(f"/api/v1/profiles/{persisted_profile.id}/gap-analysis")
    finally:
        set_gap_analysis_provider(None)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gaps"][0]["state"] == "PARTIAL"
    assert payload["gaps"][0]["evidence_refs"] == [str(persisted_profile.skills[0].id)]
    assert payload["gaps"][0]["atomic_requirement_ids"]
    assert payload["gaps"][0]["capability_name"] == "Technical capability"
    assert "fit" not in response.text.lower()


def test_unknown_profile_evidence_is_dropped_and_missing_proposal_is_uncertain(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _ready_market(client, target)
    market = db_session.query(models.MarketProfile).one()
    requirement = market.requirements[0]

    class Provider:
        def compare(self, *, requirements, profile_facts):
            return GapProposalPayload(items=[GapProposal(
                requirement_id=requirement.id,
                state=GapState.MATCHED,
                rationale="Unsupported evidence ref is removed by the server.",
                evidence_refs=[UUID("00000000-0000-0000-0000-000000000099")],
            )])

    set_gap_analysis_provider(Provider())
    try:
        response = client.post(f"/api/v1/profiles/{persisted_profile.id}/gap-analysis")
    finally:
        set_gap_analysis_provider(None)
    assert response.status_code == 200
    assert response.json()["gaps"][0]["evidence_refs"] == []


def test_valid_json_object_provider_response_is_persisted(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _ready_market(client, target)
    captured: dict[str, object] = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            request = json.loads(kwargs["messages"][1]["content"])
            payload = {
                "items": [
                    {
                        "requirement_id": item["id"],
                        "state": "MISSING",
                        "severity": "MEDIUM",
                        "proximity": "MEDIUM",
                        "feasibility": "HIGH",
                        "rationale": "No confirmed evidence was supplied.",
                        "evidence_refs": [],
                    }
                    for item in request["requirements"]
                ]
            }
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
            )

    provider = OpenAIGapAnalysisProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    )
    set_gap_analysis_provider(provider)
    try:
        response = client.post(f"/api/v1/profiles/{persisted_profile.id}/gap-analysis")
    finally:
        set_gap_analysis_provider(None)

    assert response.status_code == 200, response.text
    assert response.json()["gaps"]
    assert captured["response_format"] == {"type": "json_object"}
    assert len(response.json()["gaps"]) == len(
        market_profile_capabilities(db_session.query(models.MarketProfile).one())
    )


def test_gap_analysis_does_not_hold_market_lock_while_provider_runs(monkeypatch):
    """A slow provider must not make a concurrent request wait on FOR UPDATE."""

    profile_id = uuid4()
    market = models.MarketProfile(id=uuid4(), sample_fingerprint="market-fingerprint")
    requirement = models.MarketRequirement(
        id=uuid4(),
        name="Python",
        category="SKILL",
        occurrence_count=3,
        frequency_ratio=1.0,
        sort_order=1,
    )
    capability = SimpleNamespace(
        id=requirement.id,
        name="Technical capability",
        summary="Grounded capability",
        occurrence_count=3,
        frequency_ratio=1.0,
        source_jd_ids=[],
        atomic_requirement_ids=[],
        atomic_requirements=[],
        evidence=[],
    )
    profile = models.UserProfile(id=profile_id, status="CONFIRMED")
    monkeypatch.setattr(
        gap_service,
        "_current_context",
        lambda _db, _profile_id: (profile, market, "profile-fingerprint"),
    )
    monkeypatch.setattr(gap_service, "market_profile_capabilities", lambda _market: [capability])

    events: list[str] = []
    analysis_holder: dict[str, models.GapAnalysis] = {}

    class FakeSession:
        def scalar(self, statement):
            if getattr(statement, "_for_update_arg", None) is not None:
                events.append("market_lock")
                return market
            events.append("read")
            return None

        def add(self, value):
            if isinstance(value, models.GapAnalysis):
                value.id = uuid4()
                value.market_profile = market
                value.generated_at = value.updated_at = datetime.now(timezone.utc)
                analysis_holder["value"] = value
            elif isinstance(value, models.Gap):
                value.id = uuid4()
                value.market_requirement = requirement
                value.gap_analysis = analysis_holder["value"]

        def flush(self):
            events.append("flush")

        def commit(self):
            events.append("commit")

        def refresh(self, _value):
            return None

        def rollback(self):
            events.append("rollback")

    class Provider:
        def compare(self, *, requirements, profile_facts):
            events.append("provider")
            return GapProposalPayload(items=[])

    result = gap_service.create_gap_analysis(FakeSession(), profile_id, provider=Provider())

    assert result.gaps[0].capability_name == "Technical capability"
    assert events.index("rollback") < events.index("provider")
    assert events.index("provider") < events.index("market_lock")
