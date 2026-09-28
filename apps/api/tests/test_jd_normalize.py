from app.mission_provider import OpenAIMissionProvider
from app.mission_schemas import JobExtractionPayload, WhatMattersPayload


def test_normalize_job_extraction_coerces_loose_llm_shape():
    data = {
        "company": "百度",
        "role": "AI产品经理",
        "seniority": "中级",
        "requirements": [
            "熟悉RAG/Agent",
            {"text": "有ToB经验", "evidence": "有ToB或平台产品经验"},
        ],
        "capabilities": ["RAG", "Agent"],
    }
    payload = JobExtractionPayload.model_validate(OpenAIMissionProvider._normalize_job_extraction(data))
    assert payload.company == "百度"
    assert payload.role_family == "UNKNOWN"
    assert len(payload.requirements) == 2
    assert payload.requirements[0].id.startswith("req-")
    assert payload.requirements[0].category == "must_have"


def test_normalize_what_matters_merges_evidence_refs():
    data = {
        "core_capabilities": [{"name": "评测", "why": "JD", "evidence_refs": ["req-1"]}],
        "confidence": 0.7,
    }
    payload = WhatMattersPayload.model_validate(OpenAIMissionProvider._normalize_what_matters(data))
    assert "req-1" in payload.jd_evidence_refs


def test_normalize_seniority_and_location_aliases():
    from app.jd_identity_normalize import normalize_location, normalize_seniority

    assert normalize_seniority("校招") == "ENTRY_LEVEL"
    assert normalize_seniority("ENTRY_LEVEL") == "ENTRY_LEVEL"
    assert normalize_seniority("entry-level") == "ENTRY_LEVEL"
    assert normalize_seniority("应届生") == "ENTRY_LEVEL"
    assert normalize_seniority("实习") == "INTERN"
    assert normalize_seniority("INTERN") == "INTERN"
    assert normalize_seniority("中级") == "MID"
    assert normalize_seniority("MID") == "MID"
    assert normalize_seniority("") == "UNKNOWN"
    assert normalize_seniority(None) == "UNKNOWN"

    assert normalize_location("北京市") == "北京"
    assert normalize_location("北京") == "北京"
    assert normalize_location("上海市") == "上海"
    assert normalize_location("朝阳区") == "朝阳区"
    assert normalize_location("UNKNOWN") is None
    assert normalize_location("") is None


def test_normalize_job_extraction_maps_baidu_like_enums():
    data = {
        "company": "百度",
        "role": "AI产品经理",
        "seniority": "校招",
        "location": "北京市",
        "requirements": ["熟悉RAG"],
    }
    normalized = OpenAIMissionProvider._normalize_job_extraction(data)
    assert normalized["seniority"] == "ENTRY_LEVEL"
    assert normalized["location"] == "北京"
    payload = JobExtractionPayload.model_validate(normalized)
    assert payload.seniority == "ENTRY_LEVEL"
    assert payload.location == "北京"


def test_identity_update_schema_normalizes_enums():
    from app.mission_schemas import MissionIdentityUpdate

    row = MissionIdentityUpdate.model_validate(
        {
            "company": "百度",
            "role": "AI产品经理",
            "role_family": "AI_PRODUCT",
            "seniority": "校招",
            "location": "北京市",
        }
    )
    assert row.seniority == "ENTRY_LEVEL"
    assert row.location == "北京"


def test_infer_seniority_and_location_from_jd_text():
    from app.jd_identity_normalize import infer_location_from_jd, infer_seniority_from_jd

    jd = (
        "百度智能云\n"
        "工作地点：北京市\n"
        "招聘类型：校招\n"
        "岗位：物理AI产品经理\n"
        "工作职责\n- 负责产品规划\n"
        "任职资格\n- 本科及以上\n"
    )
    assert infer_seniority_from_jd(jd) == "ENTRY_LEVEL"
    assert infer_location_from_jd(jd) == "北京"

    # No markers → do not invent.
    bare = "工作职责\n- 负责产品\n任职资格\n- 沟通能力强\n所属部门：百度智能云\n"
    assert infer_seniority_from_jd(bare) == "UNKNOWN"
    assert infer_location_from_jd(bare) is None


def test_enrich_job_extraction_fills_seniority_location_from_jd():
    from app.mission_provider import OpenAIMissionProvider
    from app.mission_schemas import JobExtractionPayload

    jd = (
        "公司：百度\n"
        "岗位：AI产品经理\n"
        "工作地点：北京市\n"
        "招聘类型：校招\n"
        "工作职责\n- 负责AI产品\n"
    )
    extraction = JobExtractionPayload.model_validate(
        {
            "company": "UNKNOWN",
            "role": "UNKNOWN",
            "role_family": "UNKNOWN",
            "seniority": "UNKNOWN",
            "location": None,
            "responsibilities": [],
            "requirements": [],
            "preferred_requirements": [],
            "capabilities": [],
            "keywords": [],
        }
    )
    enriched = OpenAIMissionProvider._enrich_job_extraction(jd, extraction)
    assert enriched.seniority == "ENTRY_LEVEL"
    assert enriched.location == "北京"
    assert enriched.company != "UNKNOWN"

