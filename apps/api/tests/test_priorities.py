from uuid import UUID

from app.gap_provider import set_gap_analysis_provider
from app.gap_schemas import GapProposal, GapProposalPayload, GapState
from app.jd_analysis_provider import set_jd_analysis_provider
from app.jd_analysis_schemas import JdExtraction, JdExtractionItem, JdExtractionPayload, RequirementCategory
from app.priority_service import rank_gaps
from app.role_exploration_schemas import RoleCode
from app.target_role_service import select_target_role
from test_target_role_service import _ready_profile


def _setup(client, db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)
    target = select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)
    for index in range(3):
        assert client.post(f"/api/v1/target-roles/{target.id}/job-descriptions", json={"raw_text": f"Python and product analytics JD {index}"}).status_code == 201

    class JdProvider:
        def analyze(self, *, target_role, job_descriptions):
            return JdExtractionPayload(items=[JdExtraction(jd_id=UUID(row["id"]), items=[
                JdExtractionItem(name="Python", category=RequirementCategory.SKILL, evidence_text="Python"),
                JdExtractionItem(name="Product analytics", category=RequirementCategory.SKILL, evidence_text="product analytics"),
            ]) for row in job_descriptions])

    set_jd_analysis_provider(JdProvider())
    try:
        assert client.post(f"/api/v1/target-roles/{target.id}/market-profile").status_code == 200
    finally:
        set_jd_analysis_provider(None)
    from app import models
    requirements = db_session.query(models.MarketProfile).one().requirements

    class GapProvider:
        def compare(self, *, requirements, profile_facts):
            return GapProposalPayload(items=[GapProposal(
                requirement_id=UUID(row["id"]),
                state=GapState.MISSING,
                severity="HIGH" if row["name"] == "Technical capability" else "LOW",
                proximity="HIGH",
                feasibility="HIGH",
                rationale=f"Need evidence for {row['name']}",
            ) for row in requirements])

    set_gap_analysis_provider(GapProvider())
    try:
        assert client.post(f"/api/v1/profiles/{persisted_profile.id}/gap-analysis").status_code == 200
    finally:
        set_gap_analysis_provider(None)
    return persisted_profile


def test_priority_algorithm_is_stable_and_caps_now(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)
    response = client.get(f"/api/v1/profiles/{profile.id}/priorities")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["overridden"] is False
    assert [item["effective_rank"] for item in payload["items"]] == [1, 2]
    assert payload["items"][0]["lane"] == "NOW"
    assert payload["items"][0]["system_rank"] == 1
    assert payload["items"][0]["requirement_name"] == "Technical capability"
    assert payload["items"][0]["severity"] == "HIGH"
    assert payload["items"][0]["proximity"] == "HIGH"
    assert payload["items"][0]["feasibility"] == "HIGH"


def test_user_override_persists_and_is_not_replaced_by_get(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)
    initial = client.get(f"/api/v1/profiles/{profile.id}/priorities").json()
    order = [item["gap_id"] for item in reversed(initial["items"])]
    updated = client.put(f"/api/v1/profiles/{profile.id}/priorities", json={"order": order})
    assert updated.status_code == 200, updated.text
    assert updated.json()["overridden"] is True
    assert [item["gap_id"] for item in updated.json()["items"]] == order
    reread = client.get(f"/api/v1/profiles/{profile.id}/priorities")
    assert [item["gap_id"] for item in reread.json()["items"]] == order


def test_user_override_requires_a_complete_permutation(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)
    current = client.get(f"/api/v1/profiles/{profile.id}/priorities").json()["items"]
    response = client.put(f"/api/v1/profiles/{profile.id}/priorities", json={"order": [current[0]["gap_id"]]})
    assert response.status_code == 422
