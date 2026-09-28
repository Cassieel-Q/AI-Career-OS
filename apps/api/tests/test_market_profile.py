from uuid import UUID

from app import models
from app.jd_analysis_provider import set_jd_analysis_provider
from app.jd_analysis_schemas import JdExtraction, JdExtractionItem, JdExtractionPayload, MarketRequirementEvidenceRead, MarketRequirementRead, RequirementCategory
from app.market_profile_service import synthesize_capabilities
from app.role_exploration_schemas import RoleCode
from app.target_role_service import select_target_role
from test_target_role_service import _ready_profile


def collection(target_id):
    return f"/api/v1/target-roles/{target_id}/job-descriptions"


class Provider:
    def analyze(self, *, target_role, job_descriptions):
        return JdExtractionPayload(
            items=[
                JdExtraction(
                    jd_id=UUID(row["id"]),
                    items=[
                        JdExtractionItem(name="Python programming", category=RequirementCategory.SKILL, evidence_text="Python"),
                        JdExtractionItem(name="Product analytics", category=RequirementCategory.SKILL, evidence_text="product analytics"),
                    ],
                )
                for row in job_descriptions
            ]
        )


def _target(db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)
    return select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)


def _add_three(client, target):
    for index in range(3):
        response = client.post(collection(target.id), json={"raw_text": f"Build with Python and product analytics, JD {index}"})
        assert response.status_code == 201, response.text


def test_market_profile_requires_three_saved_jds(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    response = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    assert response.status_code == 409
    assert "至少需要 3" in response.json()["detail"]


def test_market_profile_aggregates_counts_and_evidence(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _add_three(client, target)
    set_jd_analysis_provider(Provider())
    try:
        response = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    finally:
        set_jd_analysis_provider(None)
    assert response.status_code == 200, response.text
    payload = response.json()
    python = next(item for item in payload["requirements"] if item["name"] == "Python")
    assert python["occurrence_count"] == 3
    assert python["frequency_ratio"] == 1.0
    assert len(python["evidence"]) == 3
    evidence_response = client.get(f"/api/v1/market-requirements/{python['id']}/evidence")
    assert evidence_response.status_code == 200
    assert all(row["evidence_text"] == "Python" for row in evidence_response.json())


def test_market_profile_exposes_grounded_capability_clusters_without_discarding_atomics(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _add_three(client, target)
    set_jd_analysis_provider(Provider())
    try:
        response = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    finally:
        set_jd_analysis_provider(None)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["requirements"]) == 2
    assert len(payload["capabilities"]) == 2
    capability = next(item for item in payload["capabilities"] if item["name"] == "Technical capability")
    assert capability["occurrence_count"] == 3
    assert capability["frequency_ratio"] == 1.0
    assert len(capability["atomic_requirements"]) == 1
    assert capability["atomic_requirements"][0]["name"] == "Python"
    assert len(capability["evidence"]) == 3
    assert {row["job_description_id"] for row in capability["evidence"]} == set(capability["source_jd_ids"])


def test_capability_prevalence_is_the_distinct_union_of_grounded_atomic_sources():
    requirement_one = MarketRequirementRead(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Python",
        category=RequirementCategory.SKILL,
        occurrence_count=2,
        frequency_ratio=0.5,
        source_jd_ids=[UUID("00000000-0000-0000-0000-000000000101"), UUID("00000000-0000-0000-0000-000000000102")],
        evidence=[
            MarketRequirementEvidenceRead(id=UUID("00000000-0000-0000-0000-000000000201"), job_description_id=UUID("00000000-0000-0000-0000-000000000101"), source_url=None, evidence_text="Python"),
            MarketRequirementEvidenceRead(id=UUID("00000000-0000-0000-0000-000000000202"), job_description_id=UUID("00000000-0000-0000-0000-000000000102"), source_url=None, evidence_text="Python"),
        ],
    )
    requirement_two = requirement_one.model_copy(update={
        "id": UUID("00000000-0000-0000-0000-000000000002"),
        "name": "Prompt engineering",
        "source_jd_ids": [UUID("00000000-0000-0000-0000-000000000102"), UUID("00000000-0000-0000-0000-000000000103")],
        "evidence": [
            MarketRequirementEvidenceRead(id=UUID("00000000-0000-0000-0000-000000000203"), job_description_id=UUID("00000000-0000-0000-0000-000000000102"), source_url=None, evidence_text="Prompt engineering"),
            MarketRequirementEvidenceRead(id=UUID("00000000-0000-0000-0000-000000000204"), job_description_id=UUID("00000000-0000-0000-0000-000000000103"), source_url=None, evidence_text="Prompt engineering"),
        ],
    })

    capabilities = synthesize_capabilities([requirement_one, requirement_two], sample_count=4)

    assert len(capabilities) == 1
    assert capabilities[0].occurrence_count == 3
    assert capabilities[0].frequency_ratio == 0.75
    assert capabilities[0].atomic_requirement_ids == [requirement_one.id, requirement_two.id]
    assert {row.job_description_id for row in capabilities[0].evidence} == {
        UUID("00000000-0000-0000-0000-000000000101"),
        UUID("00000000-0000-0000-0000-000000000102"),
        UUID("00000000-0000-0000-0000-000000000103"),
    }


def test_unverifiable_provider_evidence_is_not_persisted(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _add_three(client, target)

    class BadProvider:
        def analyze(self, *, target_role, job_descriptions):
            return JdExtractionPayload(
                items=[
                    JdExtraction(
                        jd_id=UUID(row["id"]),
                        items=[JdExtractionItem(name="Hidden preference", category=RequirementCategory.OTHER, evidence_text="not in source")],
                    )
                    for row in job_descriptions
                ]
            )

    set_jd_analysis_provider(BadProvider())
    try:
        response = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    finally:
        set_jd_analysis_provider(None)
    assert response.status_code == 502
    assert db_session.query(models.MarketProfile).count() == 0


def test_mixed_unverifiable_provider_evidence_rejects_the_whole_analysis(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _add_three(client, target)

    class MixedProvider:
        def analyze(self, *, target_role, job_descriptions):
            return JdExtractionPayload(
                items=[
                    JdExtraction(
                        jd_id=UUID(row["id"]),
                        items=[
                            JdExtractionItem(name="Python", category=RequirementCategory.SKILL, evidence_text="Python"),
                            JdExtractionItem(name="Hidden preference", category=RequirementCategory.OTHER, evidence_text="not in source"),
                        ],
                    )
                    for row in job_descriptions
                ]
            )

    set_jd_analysis_provider(MixedProvider())
    try:
        response = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    finally:
        set_jd_analysis_provider(None)
    assert response.status_code == 502
    assert db_session.query(models.MarketProfile).count() == 0


def test_jd_mutation_invalidates_market_profile(client, db_session, persisted_profile):
    target = _target(db_session, persisted_profile)
    _add_three(client, target)
    set_jd_analysis_provider(Provider())
    try:
        generated = client.post(f"/api/v1/target-roles/{target.id}/market-profile")
    finally:
        set_jd_analysis_provider(None)
    assert generated.status_code == 200
    jd = client.get(collection(target.id)).json()[0]
    assert client.patch(f"/api/v1/job-descriptions/{jd['id']}", json={"raw_text": "Changed Python JD"}).status_code == 200
    db_session.expire_all()
    market = db_session.query(models.MarketProfile).one()
    assert market.status == "INVALIDATED"
    assert client.get(f"/api/v1/target-roles/{target.id}/market-profile").status_code == 409
