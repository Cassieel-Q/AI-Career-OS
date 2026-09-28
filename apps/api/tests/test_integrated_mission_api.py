from uuid import UUID

from app.mission_provider import set_mission_provider
from app import models
from app.mission_schemas import (
    ExperienceSelectionPayload,
    InterviewPackPayload,
    JobExtractionPayload,
    RedTeamPayload,
    ResumeStrategyPayload,
    TargetResumePayload,
    WhatMattersPayload,
)


class StubIntegratedProvider:
    def parse_jd(self, raw_text):
        return JobExtractionPayload.model_validate({
            "company": "Baidu",
            "role": "AI Product Manager",
            "role_family": "AI_PRODUCT",
            "seniority": "MID",
            "location": "Beijing",
            "responsibilities": ["Own evaluation"],
            "requirements": [{"id": "req-1", "text": "Evaluation", "category": "CAPABILITY", "evidence_text": "evaluation"}],
            "preferred_requirements": [],
            "capabilities": ["AI evaluation"],
            "keywords": ["evaluation"],
        })

    def build_what_matters(self, **kwargs):
        return WhatMattersPayload.model_validate({
            "core_capabilities": [{"name": "AI evaluation", "why": "The JD says evaluation.", "evidence_refs": ["req-1"]}],
            "high_importance_requirements": [{"text": "Evaluation", "importance": "HIGH", "evidence_refs": ["req-1"]}],
            "evidence_expected": ["A reproducible evaluation artifact"],
            "likely_success_signals": ["Explains a rubric"],
            "bonus_capabilities": [],
            "potential_interview_focus": ["Quality tradeoffs"],
            "confidence": 0.8,
            "jd_evidence_refs": ["req-1"],
        })

    def select_experiences(self, *, profile_facts, **kwargs):
        experience = next(fact for fact in profile_facts if fact["kind"] == "experience")
        return ExperienceSelectionPayload.model_validate({"selections": [{"experience_id": experience["id"], "decision": "KEEP_AND_HIGHLIGHT", "why": "Closest evidence", "related_capabilities": ["AI evaluation"], "supporting_evidence_refs": [experience["id"]], "confidence": 0.8}]})

    def build_resume_strategy(self, *, profile_facts, selections, **kwargs):
        experience_id = selections.selections[0].experience_id
        return ResumeStrategyPayload.model_validate({"positioning_statement": "Evidence-led AI PM", "recommended_experience_order": [experience_id], "experience_guidance": [{"experience_id": experience_id, "role_in_story": "Shows evaluation ownership", "what_to_highlight": ["Evaluation"], "what_to_avoid": ["Unsupported metrics"], "target_capabilities": ["AI evaluation"], "evidence_refs": [experience_id], "interview_risk_notes": ["Clarify rubric"]}]})

    def build_target_resume(self, *, profile_facts, strategy, **kwargs):
        experience_id = strategy.recommended_experience_order[0]
        return TargetResumePayload.model_validate({"positioning_statement": strategy.positioning_statement, "recommended_experience_order": [experience_id], "bullets": [{"source_experience_id": experience_id, "original_text": "Research Assistant", "suggested_text": "Built an evaluation workflow", "reason": "Maps to the JD", "jd_refs": ["req-1"], "evidence_refs": [experience_id], "resume_skill_refs": ["EVIDENCE_GROUNDED_WRITING"], "risk_flags": ["needs_artifact"]}]})

    def red_team(self, *, target_resume, **kwargs):
        evidence_id = target_resume.bullets[0].evidence_refs[0]
        return RedTeamPayload.model_validate({"findings": [{"claim": "Built an evaluation workflow", "jd_relevance": "High", "evidence_strength": "Weak artifact", "company_interview_trigger": "High", "attack_dimensions": ["AI", "METRICS"], "likely_followups": ["How did you evaluate quality?"], "risk_level": "HIGH", "why": "High trigger with weak evidence", "recommended_next_step": "Recover existing evidence first", "evidence_refs": [evidence_id]}]})

    def build_interview_pack(self, **kwargs):
        return InterviewPackPayload.model_validate({"topics": [{"priority": "HIGH", "topic": "Evaluation tradeoffs", "why": "Red Team risk", "claims": ["Built an evaluation workflow"], "capabilities": ["AI evaluation"], "intel_refs": ["LLM_EVALUATION"], "question_patterns": ["How did you evaluate quality?"], "evidence_expected": ["Dataset or rubric"]}]})


class InvalidEvidenceResumeProvider(StubIntegratedProvider):
    def build_target_resume(self, *, profile_facts, strategy, **kwargs):
        payload = super().build_target_resume(profile_facts=profile_facts, strategy=strategy, **kwargs)
        payload.bullets[0].evidence_refs = [UUID("00000000-0000-0000-0000-000000000099")]
        return payload


def test_integrated_mission_api_persists_the_dogfood_chain(client, db_session, persisted_profile):
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."})
        assert created.status_code == 201, created.text
        mission_id = UUID(created.json()["id"])
        assert created.json()["company"] == "Baidu"
        assert created.json()["what_matters"]["core_capabilities"][0]["evidence_refs"] == ["req-1"]
        identity = client.patch(f"/api/v1/job-missions/{mission_id}/identity", json={"company": "Baidu", "role": "AI PM Intern", "role_family": "AI_PRODUCT", "seniority": "INTERN", "location": "Shanghai"})
        assert identity.status_code == 200
        assert identity.json()["role"] == "AI PM Intern"
        bound = client.post(f"/api/v1/job-missions/{mission_id}/confirm-resume-source", json={"mode": "master", "update_master": False})
        assert bound.status_code == 200, bound.text

        selected = client.post(f"/api/v1/job-missions/{mission_id}/experience-selection/generate")
        assert selected.status_code == 200, selected.text
        confirmed_selection = client.put(
            f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true",
            json={"selections": [{key: row[key] for key in ("experience_id", "decision", "why", "related_capabilities", "supporting_evidence_refs", "confidence")} for row in selected.json()["selections"]]},
        )
        assert confirmed_selection.status_code == 200, confirmed_selection.text
        strategy = client.post(f"/api/v1/job-missions/{mission_id}/resume-strategy")
        assert strategy.status_code == 200, strategy.text
        confirmed_strategy = client.post(f"/api/v1/job-missions/{mission_id}/confirm-strategy")
        assert confirmed_strategy.status_code == 200, confirmed_strategy.text
        resume = client.post(f"/api/v1/job-missions/{mission_id}/target-resumes")
        assert resume.status_code == 201, resume.text
        bullet_id = resume.json()["bullets"][0]["id"]
        # Two AI rewrites for one source experience are alternatives. Once
        # the second version is selected, the first must be rejected so both
        # cannot enter the final resume.
        first = db_session.get(models.TargetResumeBullet, UUID(bullet_id))
        assert first is not None
        sibling = models.TargetResumeBullet(
            target_resume_id=first.target_resume_id,
            source_experience_id=first.source_experience_id,
            original_text=first.original_text,
            suggested_text="Alternative grounded rewrite",
            final_text="Alternative grounded rewrite",
            reason="Alternative wording",
            evidence_refs=list(first.evidence_refs or []),
            status="SUGGESTED",
            sort_order=1,
        )
        db_session.add(sibling)
        db_session.commit()
        edited = client.patch(f"/api/v1/target-resume-bullets/{bullet_id}", json={"status": "ACCEPTED"})
        assert edited.status_code == 200
        selected = client.patch(f"/api/v1/target-resume-bullets/{sibling.id}", json={"status": "ACCEPTED"})
        assert selected.status_code == 200
        db_session.refresh(first)
        assert first.status == "REJECTED"
        assert selected.json()["status"] == "ACCEPTED"
        confirmed_resume = client.post(f"/api/v1/job-missions/{mission_id}/confirm-target-resume")
        assert confirmed_resume.status_code == 200, confirmed_resume.text
        red = client.post(f"/api/v1/job-missions/{mission_id}/red-team")
        assert red.status_code == 200, red.text
        pack = client.post(f"/api/v1/job-missions/{mission_id}/interview-pack")
        assert pack.status_code == 201, pack.text
        readiness = client.get(f"/api/v1/job-missions/{mission_id}/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "STRENGTHEN_FIRST"

        other = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation for a second mission."})
        assert other.status_code == 201, other.text
        assert other.json()["id"] != str(mission_id)
        listed = client.get(f"/api/v1/profiles/{persisted_profile.id}/job-missions")
        assert listed.status_code == 200
        assert len(listed.json()) == 2
        scoped_a = client.get(f"/api/v1/job-missions/{mission_id}/proof-snapshot")
        scoped_b = client.get(f"/api/v1/job-missions/{other.json()['id']}/proof-snapshot")
        assert scoped_a.status_code == scoped_b.status_code == 200
        assert scoped_a.json()["targetJob"]["id"] != scoped_b.json()["targetJob"]["id"]
    finally:
        set_mission_provider(None)


def test_core_flow_generates_interview_pack_without_pressure_test(client, persisted_profile):
    """The user-facing flow only needs a confirmed target resume before interview prep."""
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(
            f"/api/v1/profiles/{persisted_profile.id}/job-missions",
            json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."},
        )
        assert created.status_code == 201, created.text
        mission_id = created.json()["id"]
        assert client.patch(f"/api/v1/job-missions/{mission_id}/identity", json={"company": "Baidu", "role": "AI PM", "role_family": "AI_PRODUCT", "seniority": "INTERN", "location": "Shanghai"}).status_code == 200
        assert client.post(f"/api/v1/job-missions/{mission_id}/advance", json={"event": "select_resume", "user_confirmed": True}).status_code == 200
        assert client.post(f"/api/v1/job-missions/{mission_id}/confirm-resume-source", json={"mode": "master", "update_master": False}).status_code == 200
        selected = client.post(f"/api/v1/job-missions/{mission_id}/experience-selection/generate")
        assert selected.status_code == 200
        assert client.put(
            f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true",
            json={"selections": [
                {key: row[key] for key in ("experience_id", "decision", "why", "related_capabilities", "supporting_evidence_refs", "confidence")}
                for row in selected.json()["selections"]
            ]},
        ).status_code == 200
        assert client.post(f"/api/v1/job-missions/{mission_id}/resume-strategy").status_code == 200
        confirmed_strategy = client.post(f"/api/v1/job-missions/{mission_id}/confirm-strategy")
        assert confirmed_strategy.status_code == 200, confirmed_strategy.text
        resume = client.post(f"/api/v1/job-missions/{mission_id}/target-resumes")
        assert resume.status_code == 201, resume.text
        assert client.post(f"/api/v1/job-missions/{mission_id}/confirm-target-resume").status_code == 200
        pack = client.post(f"/api/v1/job-missions/{mission_id}/interview-pack")
        assert pack.status_code == 201, pack.text
        assert pack.json()["topics"]
    finally:
        set_mission_provider(None)


def test_source_resume_section_order_is_kept_on_target_resume(client, db_session, persisted_profile):
    from app.mission_service import source_resume_section_order, bind_mission_resume_from_extraction
    from app.resume_schemas import ResumeExtractionResult

    source = "教育经历\n某大学 硕士\n项目经历\nAI 产品设计\n技能\nPython"
    assert source_resume_section_order(source) == ["education", "project", "skills"]
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(
            f"/api/v1/profiles/{persisted_profile.id}/job-missions",
            json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."},
        )
        mission_id = UUID(created.json()["id"])
        bound = bind_mission_resume_from_extraction(
            db_session,
            mission_id,
            ResumeExtractionResult.model_validate({
                "education": [{"institution": "某大学", "evidence_text": "某大学 硕士"}],
                "skills": [{"name": "Python", "evidence_text": "Python"}],
                "experiences": [{"title": "AI 产品设计", "experience_type": "PROJECT", "evidence_text": "AI 产品设计"}],
                "certifications": [],
            }),
            mode="paste",
            source_section_order=source_resume_section_order(source),
        )
        assert bound["mission"]["resume_source"]["section_order"] == ["education", "project", "skills"]
    finally:
        set_mission_provider(None)


def test_rebinding_resume_clears_stale_selection_strategy_and_target_resume(client, db_session, persisted_profile):
    from app.mission_service import bind_mission_resume_from_extraction, generate_experience_selection
    from app.resume_schemas import ResumeExtractionResult

    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(
            f"/api/v1/profiles/{persisted_profile.id}/job-missions",
            json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."},
        )
        assert created.status_code == 201, created.text
        mission_id = UUID(created.json()["id"])
        first = bind_mission_resume_from_extraction(
            db_session,
            mission_id,
            ResumeExtractionResult.model_validate({
                "experiences": [{"title": "旧项目", "experience_type": "PROJECT", "evidence_text": "旧项目"}],
            }),
            mode="paste",
        )
        generated = generate_experience_selection(db_session, mission_id, provider=StubIntegratedProvider())
        assert generated["selections"]
        mission = db_session.get(models.JobMission, mission_id)
        mission.resume_strategy = {"positioning_statement": "旧策略"}
        db_session.commit()
        second = bind_mission_resume_from_extraction(
            db_session,
            mission_id,
            ResumeExtractionResult.model_validate({
                "experiences": [{"title": "新项目", "experience_type": "PROJECT", "evidence_text": "新项目"}],
            }),
            mode="paste",
        )
        assert second["bound_profile_id"] != first["bound_profile_id"]
        assert client.get(f"/api/v1/job-missions/{mission_id}/experience-selection").json()["selections"] == []
        refreshed = client.get(f"/api/v1/job-missions/{mission_id}").json()
        assert refreshed["resume_strategy"] == {}
        assert client.get(f"/api/v1/job-missions/{mission_id}/target-resumes").json() == []
    finally:
        set_mission_provider(None)


def test_mission_recover_existing_evidence_creates_user_confirmed_artifact(client, db_session, persisted_profile):
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."})
        mission_id = UUID(created.json()["id"])
        mission = db_session.get(models.JobMission, mission_id)
        claim = models.ResumeClaim(
            target_job_id=mission.target_job_id,
            profile_id=persisted_profile.id,
            claim="Owned evaluation workflow",
            current_text="Evaluation",
            suggested_text="Owned evaluation workflow",
            reason="Synthetic weak claim",
            jd_relevance="High",
            matched_capabilities=[{"name": "AI evaluation", "summary": "evaluation", "atomic_requirement_ids": []}],
            evidence_refs=[str(persisted_profile.experiences[0].id)],
            readiness_status="WEAK_EVIDENCE",
            confidence=0.4,
            risk_reason="Needs artifact",
            attack_surface=[],
            fingerprint="f" * 64,
        )
        db_session.add(claim)
        db_session.commit()

        response = client.post(f"/api/v1/job-missions/{mission_id}/recover-evidence", json={"claim_id": str(claim.id), "confirmed": True, "evidence_text": "I personally built the evaluation rubric.", "existing_project_reference": "synthetic-project"})

        assert response.status_code == 200, response.text
        assert response.json()["next"] == "RE_EVALUATE"
        assert response.json()["before_readiness"] == "WEAK_EVIDENCE"
        assert response.json()["after_readiness"] == "DEFENDABLE"
        state = client.get(f"/api/v1/job-missions/{mission_id}/proof")
        assert state.status_code == 200
        assert state.json()["proof_artifacts"][0]["artifact_type"] == "USER_CONFIRMED"
    finally:
        set_mission_provider(None)


def test_recover_evidence_rejects_audit_text_and_preserves_ready_status(client, db_session, persisted_profile):
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."})
        mission_id = UUID(created.json()["id"])
        mission = db_session.get(models.JobMission, mission_id)
        mission.status = "INTERVIEW_PREP"
        mission.workflow_state = "INTERVIEW_PREP_READY"
        claim = models.ResumeClaim(
            target_job_id=mission.target_job_id,
            profile_id=persisted_profile.id,
            claim="Owned evaluation workflow",
            current_text="Evaluation",
            suggested_text="Owned evaluation workflow",
            reason="Synthetic weak claim",
            jd_relevance="High",
            matched_capabilities=[],
            evidence_refs=[str(persisted_profile.experiences[0].id)],
            readiness_status="WEAK_EVIDENCE",
            confidence=0.4,
            risk_reason="Needs artifact",
            attack_surface=[],
            fingerprint="r" * 64,
        )
        db_session.add(claim)
        db_session.commit()

        rejected = client.post(
            f"/api/v1/job-missions/{mission_id}/recover-evidence",
            json={"claim_id": str(claim.id), "confirmed": True, "evidence_text": "审计测试"},
        )
        assert rejected.status_code == 422
        assert db_session.query(models.ProofArtifact).filter_by(claim_id=claim.id).count() == 0

        accepted = client.post(
            f"/api/v1/job-missions/{mission_id}/recover-evidence",
            json={"claim_id": str(claim.id), "confirmed": True, "evidence_text": "2024 年我负责评测报告，保留周报和结果截图。"},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["message"]
        db_session.refresh(mission)
        assert mission.status == "INTERVIEW_PREP"
        assert mission.workflow_state == "INTERVIEW_PREP_READY"
    finally:
        set_mission_provider(None)


def test_target_resume_rejects_provider_evidence_reference_outside_profile(client, persisted_profile):
    provider = InvalidEvidenceResumeProvider()
    set_mission_provider(provider)
    try:
        created = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."})
        mission_id = created.json()["id"]
        bound = client.post(f"/api/v1/job-missions/{mission_id}/confirm-resume-source", json={"mode": "master", "update_master": False})
        assert bound.status_code == 200, bound.text
        assert client.post(f"/api/v1/job-missions/{mission_id}/experience-selection/generate").status_code == 200
        selected = client.get(f"/api/v1/job-missions/{mission_id}/experience-selection")
        assert selected.status_code == 200, selected.text
        assert client.put(
            f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true",
            json={"selections": [{key: row[key] for key in ("experience_id", "decision", "why", "related_capabilities", "supporting_evidence_refs", "confidence")} for row in selected.json()["selections"]]},
        ).status_code == 200
        assert client.post(f"/api/v1/job-missions/{mission_id}/resume-strategy").status_code == 200
        assert client.post(f"/api/v1/job-missions/{mission_id}/confirm-strategy").status_code == 200
        response = client.post(f"/api/v1/job-missions/{mission_id}/target-resumes")
        assert response.status_code == 201
        assert response.json()["bullets"][0]["grounding_status"] == "NEEDS_CONFIRMATION"
    finally:
        set_mission_provider(None)


def test_archived_mission_can_be_recreated_for_the_same_jd(client, persisted_profile):
    set_mission_provider(StubIntegratedProvider())
    try:
        raw = "Baidu AI PM: own evaluation workflows and quality evaluation."
        first = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": raw})
        assert first.status_code == 201, first.text
        first_id = first.json()["id"]
        archived = client.post(f"/api/v1/job-missions/{first_id}/archive")
        assert archived.status_code == 200, archived.text

        recreated = client.post(f"/api/v1/profiles/{persisted_profile.id}/job-missions", json={"raw_text": raw})
        assert recreated.status_code == 201, recreated.text
        assert recreated.json()["id"] != first_id
        assert recreated.json()["workflow_state"] == "ROLE_UNDERSTOOD"
    finally:
        set_mission_provider(None)


def test_explicit_resume_optimization_regeneration_clears_old_draft(client, persisted_profile):
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(
            f"/api/v1/profiles/{persisted_profile.id}/job-missions",
            json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."},
        )
        mission_id = created.json()["id"]
        assert client.post(f"/api/v1/job-missions/{mission_id}/confirm-resume-source", json={"mode": "master", "update_master": False}).status_code == 200
        assert client.post(f"/api/v1/job-missions/{mission_id}/experience-selection/generate").status_code == 200
        regenerated = client.post(f"/api/v1/job-missions/{mission_id}/resume-optimization/regenerate")
        assert regenerated.status_code == 200, regenerated.text
        assert regenerated.json()["selections"]
        assert regenerated.json()["workflow_state"] == "EXPERIENCE_SELECTION_REQUIRED"
        assert client.get(f"/api/v1/job-missions/{mission_id}/target-resumes").json() == []
    finally:
        set_mission_provider(None)
