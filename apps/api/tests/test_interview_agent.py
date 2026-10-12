"""第九阶段验收：AI 面试助手（顺顺）优化——上下文解析 / 统一上下文 / 准备流程 /
题库 / 模拟面试 / 工具容错。

覆盖用户列出的 15 条测试用例。
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app import assistant_routes, models
from app.assistant_service import execute_tool
from app.interview_context import detect_intent, is_crash_prep, looks_like_jd, resolve_interview_context
from app.interview_prep_planner import CRASH_PREP_SECTIONS, MODE_CRASH_PREP, plan_interview_prep
from app.mission_interview_context import build_mission_interview_context, get_interview_intel_context
from app.mock_interview_service import start_mock_interview, submit_answer
from app.question_bank_service import generate_bank_from_context, generate_reference_answer
from app.tool_result import ToolResult


def _offline_model(**_kwargs):
    """模拟模型不可用：验证降级路径时不依赖网络与模型输出。"""
    raise RuntimeError("model offline")


# ---------------------------------------------------------------------------
# 测试夹具：一个带岗位版简历的档案
# ---------------------------------------------------------------------------


def _make_profile(db_session, *, name="Ada Chen"):
    profile = models.UserProfile(status="CONFIRMED", full_name=name, phone="13800000000", email="ada@example.com")
    db_session.add(profile)
    db_session.flush()
    return profile


def _make_mission(
    db_session,
    profile,
    *,
    company="Acme",
    role="产品经理",
    requirements=("3 年以上 B 端产品经验", "熟练使用 SQL 做数据分析"),
    intel=None,
):
    experience = models.Experience(
        profile_id=profile.id,
        title="Product Intern",
        organization="Acme",
        dates="2025.01–2025.06",
        description="Built evaluation dashboards",
        evidence_text="Product Intern at Acme; built evaluation dashboards",
        experience_type="INTERNSHIP",
    )
    education = models.Education(
        profile_id=profile.id, institution="Example University", degree="MSc", evidence_text="Example University MSc"
    )
    db_session.add_all([experience, education])
    db_session.flush()
    job = models.TargetJob(profile_id=profile.id, raw_text="jd", content_hash=f"{company}-{role}".ljust(64, "0")[:64])
    db_session.add(job)
    db_session.flush()
    mission = models.JobMission(
        profile_id=profile.id,
        target_job_id=job.id,
        display_name=f"{company} {role}",
        company=company,
        role=role,
        parsed_jd={"requirements": [{"text": text} for text in requirements]},
        what_matters={"must_have": list(requirements)},
        interview_intel=list(intel or []),
    )
    db_session.add(mission)
    db_session.flush()
    return mission, experience


def _make_target_resume(db_session, mission, experience, *, status="CONFIRMED", with_evidence=True):
    resume = models.TargetResume(
        mission_id=mission.id, version=1, status=status, recommended_experience_order=[str(experience.id)]
    )
    db_session.add(resume)
    db_session.flush()
    bullet = models.TargetResumeBullet(
        target_resume_id=resume.id,
        source_experience_id=experience.id,
        original_text="Built dashboards",
        suggested_text="Built evaluation dashboards",
        final_text="在 Acme 实习期间搭建了产品评估看板",
        reason="Grounded rewrite",
        evidence_refs=[str(experience.id)] if with_evidence else [],
        status="EDITED",
        sort_order=0,
    )
    db_session.add(bullet)
    db_session.commit()
    return resume, bullet


def _make_claim(db_session, profile, mission, *, text, readiness="CONFIRMED", evidence=True):
    target_job_id = mission.target_job_id
    claim = models.ResumeClaim(
        target_job_id=target_job_id,
        profile_id=profile.id,
        claim=text,
        reason="test",
        jd_relevance="test",
        readiness_status=readiness,
        confidence=0.9,
        risk_reason="",
        fingerprint="f" * 64,
        evidence_refs=["e1"] if evidence else [],
    )
    db_session.add(claim)
    db_session.commit()
    return claim


JD_TEXT = (
    "岗位名称：数据产品经理\n"
    "岗位职责：\n"
    "- 负责 B 端数据产品的需求分析与方案设计\n"
    "- 与数据团队协作，推动指标体系建设\n"
    "任职要求：\n"
    "- 3 年以上 B 端产品经验，熟悉 SQL\n"
    "- 有较强的数据分析与跨团队协作能力\n"
    "我们希望你具备较强的ownership和结果导向。"
)


# ---------------------------------------------------------------------------
# 1. 两个工具并行调用不会触发 dict 比较错误
# ---------------------------------------------------------------------------


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class _Chunk:
    def __init__(self, choices):
        self.choices = choices


class _Fn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _TC:
    def __init__(self, index, id=None, fn=None):
        self.index = index
        self.id = id
        self.function = fn


class _Stream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._chunks:
            yield chunk


class _FakeCompletions:
    def __init__(self, rounds, *, raise_at=None):
        self._rounds = rounds
        self._raise_at = raise_at
        self.calls = 0

    async def create(self, **kwargs):
        index = self.calls
        self.calls += 1
        if self._raise_at is not None and index == self._raise_at:
            raise RuntimeError("upstream exploded")
        return _Stream(self._rounds[min(index, len(self._rounds) - 1)])


class _FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)
        self.closed = False

    async def close(self):
        self.closed = True


def _patch_stream(monkeypatch, rounds, *, raise_at=None):
    completions = _FakeCompletions(rounds, raise_at=raise_at)
    fake = _FakeClient(completions)
    monkeypatch.setattr(assistant_routes, "build_client", lambda: (fake, "fake-model"))
    return fake


def _patch_db_gen(monkeypatch, db_session):
    engine = db_session.get_bind()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _gen():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(assistant_routes, "get_db_gen", _gen)


def _tool_call_round(*pairs):
    """构造一轮「模型返回多个工具调用」的 chunk。"""
    tcs = [_TC(index, f"call_{index}", _Fn(name, args)) for index, (name, args) in enumerate(pairs)]
    return [_Chunk([_Choice(_Delta(content=None, tool_calls=tcs), "tool_calls")])]


def _content_round(text):
    return [_Chunk([_Choice(_Delta(content=text), "stop")])]


def _sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def test_two_parallel_tool_calls_do_not_break_and_generation_continues(client, monkeypatch, db_session):
    _patch_db_gen(monkeypatch, db_session)
    _patch_stream(
        monkeypatch,
        [
            _tool_call_round(("list_jobs", "{}"), ("list_resumes", "{}")),
            _content_round("两个工具都执行完了，这是最终回答。"),
        ],
    )
    conv = client.post("/api/v1/assistant/conversations", json={"surface": "page"}).json()
    response = client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        json={"content": "我有哪些岗位和简历？", "web_search": False, "allow_write": False, "reasoning_effort": "medium"},
    )
    assert response.status_code == 200
    events = _sse_events(response.text)
    tool_events = [event for event in events if event["type"] == "tool"]
    assert [event["name"] for event in tool_events] == ["list_jobs", "list_resumes"]
    assert all(event["ok"] for event in tool_events)
    done = [event for event in events if event["type"] == "done"]
    assert done and done[0]["message"]["content"] == "两个工具都执行完了，这是最终回答。"
    assert not any(event["type"] == "error" for event in events)


def test_tool_order_helper_is_stable_for_multiple_calls():
    # 直接回归：对 dict 调 sorted() 会抛 TypeError，必须按 index 排序。
    tool_calls = {1: {"id": "b", "name": "list_resumes"}, 0: {"id": "a", "name": "list_jobs"}}
    with pytest.raises(TypeError):
        sorted(tool_calls.values())  # noqa: B018 - 复现原生产错误
    ordered = [tool_calls[index] for index in sorted(tool_calls.keys())]
    assert [call["name"] for call in ordered] == ["list_jobs", "list_resumes"]


# ---------------------------------------------------------------------------
# 2. 用户只粘贴 JD，没有保存岗位，仍然可以生成面试准备
# ---------------------------------------------------------------------------


def test_jd_only_message_generates_prep_without_mission(db_session):
    profile = _make_profile(db_session)
    db_session.commit()

    message = "帮我准备面试\n\n" + JD_TEXT
    assert looks_like_jd(message)
    resolved = resolve_interview_context(db_session, message=message, profile_id=str(profile.id))
    assert resolved.intent == "INTERVIEW_PREP"
    assert resolved.jd_in_message is True
    assert resolved.mission_id is None
    assert resolved.needs_clarification is False
    assert JD_TEXT in resolved.raw_jd
    assert resolved.role == "数据产品经理"
    assert "mission" in resolved.missing_context

    ctx = build_mission_interview_context(db_session, profile_id=profile.id, raw_jd=message)
    plan = plan_interview_prep(resolved.to_dict(), ctx)
    assert [section["title"] for section in plan["sections"]] == list(CRASH_PREP_SECTIONS)


# ---------------------------------------------------------------------------
# 3. 已有 mission + 已上传岗位简历时，Agent 能读到目标简历正文
# ---------------------------------------------------------------------------


def test_agent_reads_target_resume_when_mission_bound(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    resume, bullet = _make_target_resume(db_session, mission, experience)

    ctx = build_mission_interview_context(
        db_session, profile_id=profile.id, mission_id=mission.id, target_resume_id=resume.id
    )
    target = ctx["target_resume"]
    assert target is not None
    assert target["resume_id"] == str(resume.id)
    assert target["version"] == 1
    assert target["status"] == "CONFIRMED"
    assert target["bullet_text"] == ["在 Acme 实习期间搭建了产品评估看板"]
    assert target["relevant_experiences"][0]["source_experience_id"] == str(experience.id)
    assert target["relevant_experiences"][0]["evidence_refs"] == [str(experience.id)]


# ---------------------------------------------------------------------------
# 4. 有 mission 但没有 target resume 时，Agent 能明确提示并使用 profile facts
# ---------------------------------------------------------------------------


def test_missing_target_resume_is_reported_and_profile_facts_used(db_session):
    profile = _make_profile(db_session)
    mission, _experience = _make_mission(db_session, profile)
    _make_claim(db_session, profile, mission, text="主导过一次需求评审")

    resolved = resolve_interview_context(db_session, message="帮我准备面试", mission_id=str(mission.id), profile_id=str(profile.id))
    assert resolved.target_resume_id is None
    assert "target_resume" in resolved.missing_context
    assert "岗位版简历" in resolved.reason

    ctx = build_mission_interview_context(db_session, profile_id=profile.id, mission_id=mission.id)
    assert ctx["target_resume"] is None
    assert ctx["confirmed_claims"]["confirmed_count"] == 1
    plan = plan_interview_prep(resolved.to_dict(), ctx)
    degraded = [step for step in plan["steps"] if step["status"] == "DEGRADED"]
    assert any(step["step"] == "RESUME_EVIDENCE_SELECTOR" for step in degraded)


# ---------------------------------------------------------------------------
# 5. 公司存在多个岗位时不会随机选错
# ---------------------------------------------------------------------------


def test_multiple_roles_same_company_lists_candidates(db_session):
    profile = _make_profile(db_session)
    _make_mission(db_session, profile, company="Acme", role="产品经理")
    _make_mission(db_session, profile, company="Acme", role="数据分析师")
    db_session.commit()

    resolved = resolve_interview_context(db_session, message="帮我准备 Acme 的面试", profile_id=str(profile.id))
    assert resolved.needs_clarification is True
    assert resolved.mission_id is None
    assert len(resolved.candidates) == 2
    assert {candidate["role"] for candidate in resolved.candidates} == {"产品经理", "数据分析师"}


def test_multiple_roles_disambiguated_by_explicit_role(db_session):
    profile = _make_profile(db_session)
    _make_mission(db_session, profile, company="Acme", role="产品经理")
    _make_mission(db_session, profile, company="Acme", role="数据分析师")
    db_session.commit()

    resolved = resolve_interview_context(db_session, message="帮我准备 Acme 数据分析师的面试", profile_id=str(profile.id))
    assert resolved.needs_clarification is False
    assert resolved.role == "数据分析师"


# ---------------------------------------------------------------------------
# 6. 同一公司找不到岗位时不会中断
# ---------------------------------------------------------------------------


def test_unknown_company_does_not_crash_without_jd(db_session):
    profile = _make_profile(db_session)
    db_session.commit()
    resolved = resolve_interview_context(db_session, message="帮我准备 ByteDance 的面试", profile_id=str(profile.id))
    assert resolved.needs_clarification is True
    assert resolved.mission_id is None
    assert "mission" in resolved.missing_context


# ---------------------------------------------------------------------------
# 7. 简历中没有数字时，参考答案不能编造数字
# ---------------------------------------------------------------------------


def test_reference_answer_does_not_invent_numbers(db_session, monkeypatch):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    _make_target_resume(db_session, mission, experience)
    db_session.commit()

    bank = generate_bank_from_context(db_session, profile.id, mission_id=mission.id)
    item = next(i for i in bank.items if i.category == "PROJECT_DEEP_DIVE")
    # 模型不可用 → 走事实拼接降级路径，才能断言「没有编造数字」。
    monkeypatch.setattr("app.question_bank_service.generate_answer", _offline_model)
    answer = generate_reference_answer(db_session, item.id)

    assert answer.grounding in {"TARGET_RESUME", "BULLETS"}
    assert not re.search(r"\d", answer.answer_text), answer.answer_text
    item_after = db_session.get(models.QuestionItem, item.id)
    assert item_after.sample_answer is not None
    assert not re.search(r"\d", item_after.sample_answer)


# ---------------------------------------------------------------------------
# 8. demo/CURATED 面经不能进入正式准备包
# ---------------------------------------------------------------------------


def test_demo_intel_is_excluded_from_prep(db_session):
    profile = _make_profile(db_session)
    synthetic = {
        "skill_id": "DEMO_ONLY_priority",
        "topic": "演示题",
        "hint": "合成演示内容，不应出现",
        "body": "## Question patterns\n- 演示问题，不应出现 [demo]\n",
    }
    real = {
        "skill_id": "CURATED_ACME_PM",
        "topic": "产品sense",
        "body": "## Question patterns\n- 你如何给需求排优先级？[product]\n## Interviewer intent\n- 看是否有取舍标准\n",
    }
    mission, experience = _make_mission(db_session, profile, intel=[synthetic, real])
    _make_target_resume(db_session, mission, experience)
    db_session.commit()

    intel = get_interview_intel_context(db_session, mission_id=mission.id, company="Acme")
    assert intel["dropped_synthetic_count"] == 1
    blob = json.dumps(intel, ensure_ascii=False)
    assert "合成演示" not in blob
    assert "演示问题" not in blob
    assert "你如何给需求排优先级？" in blob

    resolved = resolve_interview_context(db_session, message="准备面试", mission_id=str(mission.id), profile_id=str(profile.id))
    ctx = build_mission_interview_context(db_session, profile_id=profile.id, mission_id=mission.id)
    plan = plan_interview_prep(resolved.to_dict(), ctx)
    plan_blob = json.dumps(plan, ensure_ascii=False)
    assert "合成演示" not in plan_blob
    assert "演示问题" not in plan_blob


# ---------------------------------------------------------------------------
# 9. 工具失败后仍能输出降级回答
# ---------------------------------------------------------------------------


def test_tool_result_failure_is_structured(db_session):
    profile = _make_profile(db_session)
    db_session.commit()
    result = execute_tool("get_target_resume_context", {}, db_session, None)
    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error
    assert result.changed is False
    assert "失败" in result.content_for_model


def test_tool_failure_still_produces_answer(client, monkeypatch, db_session):
    _patch_db_gen(monkeypatch, db_session)
    _patch_stream(
        monkeypatch,
        [
            _tool_call_round(("get_target_resume_context", "{}")),
            _content_round("已用现有资料给出降级回答。"),
        ],
    )
    conv = client.post("/api/v1/assistant/conversations", json={"surface": "page"}).json()
    response = client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        json={"content": "看看我的岗位简历", "web_search": False, "allow_write": False, "reasoning_effort": "medium"},
    )
    events = _sse_events(response.text)
    tool_events = [event for event in events if event["type"] == "tool"]
    assert tool_events and tool_events[0]["ok"] is False
    degraded = [event for event in events if event["type"] == "degraded"]
    assert degraded, "工具失败时应给出降级说明"
    done = [event for event in events if event["type"] == "done"]
    assert done and "降级回答" in done[0]["message"]["content"]
    assert "未加载成功" in done[0]["message"]["content"]
    assert not any(event["type"] == "error" for event in events)


# ---------------------------------------------------------------------------
# 10. 当前页面传入 mission_id 和 target_resume_id 后，Agent 能自动使用
# ---------------------------------------------------------------------------


def test_page_context_is_used_automatically(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    resume, _bullet = _make_target_resume(db_session, mission, experience)

    resolved = resolve_interview_context(
        db_session,
        message="我该怎么准备？",
        mission_id=str(mission.id),
        target_resume_id=str(resume.id),
        profile_id=str(profile.id),
    )
    assert resolved.mission_id == str(mission.id)
    assert resolved.target_resume_id == str(resume.id)
    assert resolved.context_confidence >= 0.9
    assert resolved.needs_clarification is False


def test_context_endpoint_returns_summary(client, db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    resume, _bullet = _make_target_resume(db_session, mission, experience)
    _make_claim(db_session, profile, mission, text="主导过一次需求评审")
    db_session.commit()

    response = client.post(
        "/api/v1/assistant/interview-context",
        json={
            "message": "帮我准备面试",
            "profile_id": str(profile.id),
            "mission_id": str(mission.id),
            "target_resume_id": str(resume.id),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resolved"]["mission_id"] == str(mission.id)
    assert body["summary"]["resume_version"] == 1
    assert body["summary"]["confirmed_claims_count"] == 1
    assert body["prep"]["mode"] in {"FULL_PREP", "CRASH_PREP"}


# ---------------------------------------------------------------------------
# 11. 题库问题必须有 jd_requirement_refs 和 experience_refs
# ---------------------------------------------------------------------------


def test_generated_questions_have_jd_and_experience_refs(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    _make_target_resume(db_session, mission, experience)
    db_session.commit()

    bank = generate_bank_from_context(db_session, profile.id, mission_id=mission.id)
    categories = {item.category for item in bank.items}
    assert {"BASIC", "PROJECT_DEEP_DIVE", "HR_QUESTIONS"}.issubset(categories)
    for item in bank.items:
        assert item.jd_requirement_refs, item.question_text
        assert item.experience_refs, item.question_text
        assert item.why_asked
        assert item.followup_paths
    assert all(item.expected_evidence for item in bank.items)


def test_question_without_evidence_is_flagged_not_invented(db_session):
    profile = _make_profile(db_session)
    mission, _experience = _make_mission(db_session, profile)
    db_session.commit()

    bank = generate_bank_from_context(db_session, profile.id, mission_id=mission.id)
    flagged = [item for item in bank.items if "NO_VERIFIED_EXPERIENCE" in (item.risk_flags or [])]
    assert flagged, "没有已确认岗位简历时应打上 NO_VERIFIED_EXPERIENCE 风险标记"


# ---------------------------------------------------------------------------
# 12. 模拟面试追问必须针对用户刚刚的回答，而不是重复第一轮问题
# ---------------------------------------------------------------------------


def test_mock_interview_followup_targets_previous_answer(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    resume, _bullet = _make_target_resume(db_session, mission, experience)
    db_session.commit()

    session = start_mock_interview(
        db_session,
        profile.id,
        mission_id=mission.id,
        target_resume_id=resume.id,
        interview_type="TECHNICAL",
        difficulty="MEDIUM",
        rounds=3,
    )
    assert session.current_round == 1
    first_question = session.turns[0].question

    answer = "我在 Acme 实习时负责需求分析，主导过需求评审。"
    session = submit_answer(db_session, session.id, answer=answer)

    assert session.current_round == 2
    evaluation = session.turns[0].evaluation
    assert set(evaluation) >= {
        "answer_coverage",
        "evidence_status",
        "missing_evidence",
        "unsupported_claims",
        "jd_alignment",
        "next_followup",
        "improvement_tip",
    }
    second_question = session.turns[1].question
    assert second_question != first_question
    assert "需求分析" in second_question or "主导过需求评审" in second_question


def test_mock_interview_flags_unsupported_numbers(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    resume, _bullet = _make_target_resume(db_session, mission, experience)
    db_session.commit()

    session = start_mock_interview(db_session, profile.id, mission_id=mission.id, target_resume_id=resume.id, rounds=2)
    session = submit_answer(db_session, session.id, answer="我做过 3 个项目，转化率提升了 250%。")
    evaluation = session.turns[0].evaluation
    assert evaluation["evidence_status"] == "UNSUPPORTED"
    values = {claim["value"] for claim in evaluation["unsupported_claims"]}
    assert "250%" in values


def test_mock_interview_final_report_only_after_last_round(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    resume, _bullet = _make_target_resume(db_session, mission, experience)
    db_session.commit()

    session = start_mock_interview(db_session, profile.id, mission_id=mission.id, target_resume_id=resume.id, rounds=1)
    assert session.report == {}
    session = submit_answer(db_session, session.id, answer="我在 Acme 实习时搭建了产品评估看板。")
    assert session.status == "COMPLETED"
    assert session.report["rounds_answered"] == 1
    assert session.report["evidence_summary"]["VERIFIED"] == 1


# ---------------------------------------------------------------------------
# 13. 面试记录可以反向生成简历优化建议
# ---------------------------------------------------------------------------


def test_real_interview_question_generates_resume_suggestions(client, db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    _make_target_resume(db_session, mission, experience)
    db_session.commit()

    created = client.post(
        f"/api/v1/profiles/{profile.id}/question-items/real",
        json={"question_text": "请说明你如何做需求优先级排序？", "mission_id": str(mission.id)},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    suggestions = client.post(f"/api/v1/question-items/{item_id}/resume-suggestions")
    assert suggestions.status_code == 200
    body = suggestions.json()
    assert body
    assert body[0]["question"] == "请说明你如何做需求优先级排序？"
    assert body[0]["evidence_refs"]


# ---------------------------------------------------------------------------
# 14. 未确认事实不得进入正式参考答案
# ---------------------------------------------------------------------------


def test_unconfirmed_claim_not_in_reference_answer(db_session):
    profile = _make_profile(db_session)
    mission, _experience = _make_mission(db_session, profile)
    _make_claim(db_session, profile, mission, text="管理过 10 人团队", readiness="NEEDS_CONFIRMATION")
    db_session.commit()

    bank = generate_bank_from_context(db_session, profile.id, mission_id=mission.id)
    item = next(i for i in bank.items if i.category == "PROJECT_DEEP_DIVE")
    answer = generate_reference_answer(db_session, item.id)
    assert answer.grounding == "UNKNOWN"
    assert "10" not in answer.answer_text
    item_after = db_session.get(models.QuestionItem, item.id)
    assert item_after.sample_answer is None


# ---------------------------------------------------------------------------
# 15. 流式中断后，历史消息仍保存已完成内容和工具记录
# ---------------------------------------------------------------------------


def test_stream_error_persists_partial_content_and_tool_log(client, monkeypatch, db_session):
    _patch_db_gen(monkeypatch, db_session)
    _patch_stream(
        monkeypatch,
        [_tool_call_round(("list_jobs", "{}"))],
        raise_at=1,
    )
    conv = client.post("/api/v1/assistant/conversations", json={"surface": "page"}).json()
    response = client.post(
        f"/api/v1/assistant/conversations/{conv['id']}/messages",
        json={"content": "我有哪些岗位？", "web_search": False, "allow_write": False, "reasoning_effort": "medium"},
    )
    events = _sse_events(response.text)
    assert any(event["type"] == "error" for event in events)

    detail = client.get(f"/api/v1/assistant/conversations/{conv['id']}").json()
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert assistant_messages, "中断后仍应保留一条助手消息"
    saved = assistant_messages[-1]
    assert saved["tool_calls"], "应保留已成功执行的工具记录"
    assert saved["tool_calls"][0]["name"] == "list_jobs"
    assert "已完成" in saved["content"] or "list_jobs" in saved["content"]


# ---------------------------------------------------------------------------
# 附加：意图 / CRASH_PREP 判定
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("帮我模拟面试一轮", "MOCK_INTERVIEW"),
        ("给我来一套面试题库", "QUESTION_BANK"),
        ("我的简历和这个岗位匹配吗", "RESUME_MATCH"),
        ("这个岗位要什么要求", "JOB_LOOKUP"),
        ("帮我准备一下面试", "INTERVIEW_PREP"),
        ("你好", "GENERAL_CAREER"),
    ],
)
def test_intent_detection(message, intent):
    assert detect_intent(message) == intent


def test_crash_prep_detection():
    assert is_crash_prep("我今天下午就要面试了")
    assert is_crash_prep("今晚面试，来不及了")
    assert not is_crash_prep("帮我准备一下面试")


def test_crash_prep_plan_uses_short_mode(db_session):
    profile = _make_profile(db_session)
    mission, experience = _make_mission(db_session, profile)
    _make_target_resume(db_session, mission, experience)
    db_session.commit()

    resolved = resolve_interview_context(
        db_session, message="我今天下午就要面试了", mission_id=str(mission.id), profile_id=str(profile.id)
    )
    assert resolved.crash_prep is True
    ctx = build_mission_interview_context(db_session, profile_id=profile.id, mission_id=mission.id)
    plan = plan_interview_prep(resolved.to_dict(), ctx)
    assert plan["mode"] == MODE_CRASH_PREP
    assert len(plan["sections"]) == 8
    assert plan["sections"][1]["items"], "短时模式必须给出最该讲的经历"
    assert plan["question_count"] <= 5


def test_fixed_case_five_required_checks(db_session):
    """固定案例端到端检查（用户明确要求）：
    正确岗位 / 正确简历 / 引用真实经历 / 无编造事实 / 工具失败后继续工作。
    """
    profile = _make_profile(db_session)
    acme, acme_experience = _make_mission(db_session, profile, company="Acme", role="产品经理")
    _make_mission(db_session, profile, company="Globex", role="数据分析师")
    resume, _bullet = _make_target_resume(db_session, acme, acme_experience)
    _make_claim(db_session, profile, acme, text="主导过一次需求评审")
    db_session.commit()

    # --- 检查一：使用了正确岗位（从多个岗位中选中 Acme，而不是 Globex） ---
    resolved = resolve_interview_context(
        db_session, message="帮我准备 Acme 产品经理的面试", profile_id=str(profile.id)
    )
    assert resolved.mission_id == str(acme.id)
    assert resolved.company == "Acme"
    assert resolved.needs_clarification is False

    # --- 检查二：使用了正确简历（命中该岗位绑定的 target resume） ---
    assert resolved.target_resume_id == str(resume.id)

    ctx = build_mission_interview_context(
        db_session, profile_id=profile.id, mission_id=acme.id, target_resume_id=resume.id
    )
    target = ctx["target_resume"]
    assert target["resume_id"] == str(resume.id)
    assert target["mission_id"] == str(acme.id)

    # --- 检查三：引用了真实经历（带 source_experience_id 与 evidence_refs） ---
    verified = target["relevant_experiences"]
    assert verified and verified[0]["source_experience_id"] == str(acme_experience.id)
    assert verified[0]["evidence_refs"] == [str(acme_experience.id)]

    # --- 检查四：没有编造事实（准备包只引用已确认内容，不含未确认条目） ---
    plan = plan_interview_prep(resolved.to_dict(), ctx)
    plan_blob = json.dumps(plan, ensure_ascii=False)
    assert verified[0]["bullet_text"] in plan_blob
    for item in target["needs_confirmation"]:
        if item.get("bullet_text"):
            assert item["bullet_text"] not in plan_blob, "未确认条目不得进入正式准备包"

    # --- 检查五：工具失败后继续工作（返回结构化失败 + 降级说明，不中断） ---
    failed = execute_tool("get_target_resume_context", {}, db_session, None)
    assert failed.ok is False and failed.error
    assert "失败" in failed.content_for_model
    # 已成功加载的上下文仍然可用。
    claims = execute_tool("get_confirmed_claims_context", {}, db_session, str(profile.id))
    assert claims.ok is True
    assert "主导过一次需求评审" in claims.summary
