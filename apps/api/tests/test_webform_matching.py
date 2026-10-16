"""网申填表匹配引擎单测（纯函数，无副作用）。"""
from __future__ import annotations

from app import webform_matching as wm

FACTS = {
    "full_name": "张三",
    "phone": "13800000000",
    "email": "zhangsan@example.com",
    "city": "上海",
    "education": [
        {
            "institution": "示例大学",
            "degree": "硕士",
            "field_of_study": "计算机科学与技术",
            "dates": "2026-06",
            "cet6_score": "520",
        }
    ],
    "application": {
        "id_number": "310000000000000000",
        "emergency_contact": "李四",
        "emergency_phone": "13900000000",
        "availability": "一个月内",
        "family_info": "父母务农",
    },
}


def test_text_field_matches_name_and_returns_ready():
    plan = wm.build_plan(
        [{"index": 0, "tag": "input", "type": "text", "name": "fullName", "label": "姓名", "required": True}],
        FACTS,
    )
    item = plan["plans"][0]
    assert item["status"] == "READY"
    assert item["match_key"] == "full_name"
    assert item["value"] == "张三"
    assert item["support"] == "FULL"


def test_password_and_captcha_are_blocked():
    plan = wm.build_plan(
        [
            {"index": 0, "tag": "input", "type": "password", "name": "password", "label": "登录密码"},
            {"index": 1, "tag": "input", "type": "text", "name": "smsCode", "label": "短信验证码"},
            {"index": 2, "tag": "input", "type": "hidden", "name": "csrf", "label": ""},
            {"index": 3, "tag": "button", "type": "submit", "name": "submitBtn", "label": "提交申请"},
        ],
        FACTS,
    )
    statuses = [item["status"] for item in plan["plans"]]
    assert statuses == ["BLOCKED", "BLOCKED", "BLOCKED", "BLOCKED"]
    assert all(item["value"] == "" for item in plan["plans"])


def test_file_upload_is_unsupported():
    plan = wm.build_plan([{"index": 0, "tag": "input", "type": "file", "name": "resume", "label": "简历附件"}], FACTS)
    assert plan["plans"][0]["status"] == "UNSUPPORTED"
    assert plan["plans"][0]["support"] == "UNSUPPORTED"


def test_select_matches_option_or_needs_confirm():
    ok = wm.build_plan(
        [{"index": 0, "tag": "select", "type": "select", "name": "degree", "label": "最高学历", "options": ["大专", "本科", "硕士"]}],
        FACTS,
    )["plans"][0]
    assert ok["status"] == "READY" and ok["value"] == "硕士"

    bad = wm.build_plan(
        [{"index": 0, "tag": "select", "type": "select", "name": "degree", "label": "最高学历", "options": ["大专", "本科"]}],
        FACTS,
    )["plans"][0]
    assert bad["status"] == "NEEDS_CONFIRM"


def test_unknown_field_needs_confirm():
    plan = wm.build_plan(
        [{"index": 0, "tag": "input", "type": "text", "name": "favorite_color", "label": "最喜欢的颜色"}],
        FACTS,
    )["plans"][0]
    assert plan["status"] == "NEEDS_CONFIRM"
    assert plan["match_key"] is None


def test_education_and_application_fields_are_used():
    plan = wm.build_plan(
        [
            {"index": 0, "tag": "input", "type": "text", "name": "school", "label": "毕业院校"},
            {"index": 1, "tag": "input", "type": "text", "name": "major", "label": "专业"},
            {"index": 2, "tag": "input", "type": "text", "name": "idNumber", "label": "身份证号"},
            {"index": 3, "tag": "input", "type": "text", "name": "emergency", "label": "紧急联系人"},
        ],
        FACTS,
    )
    values = {item["match_key"]: item["value"] for item in plan["plans"]}
    assert values["school"] == "示例大学"
    assert values["major"] == "计算机科学与技术"
    assert values["id_number"] == "310000000000000000"
    assert values["emergency_contact"] == "李四"


def test_summary_counts_and_sensitive_keys():
    plan = wm.build_plan(
        [
            {"index": 0, "tag": "input", "type": "text", "name": "fullName", "label": "姓名"},
            {"index": 1, "tag": "input", "type": "text", "name": "unknown", "label": "未知字段"},
            {"index": 2, "tag": "input", "type": "file", "name": "resume", "label": "简历附件"},
            {"index": 3, "tag": "input", "type": "password", "name": "pwd", "label": "密码"},
        ],
        FACTS,
    )
    assert plan["summary"]["total"] == 4
    assert plan["summary"]["ready"] == 1
    assert plan["summary"]["needs_confirm"] == 1
    assert plan["summary"]["unsupported"] == 1
    assert plan["summary"]["blocked"] == 1
    assert "id_number" in plan["fact_keys_available"]


def test_date_field_rejects_non_date_value():
    facts = dict(FACTS)
    facts = {**FACTS, "education": [{**FACTS["education"][0], "dates": "毕业那年"}]}
    plan = wm.build_plan(
        [{"index": 0, "tag": "input", "type": "date", "name": "graduationDate", "label": "毕业时间"}],
        facts,
    )["plans"][0]
    assert plan["status"] == "NEEDS_CONFIRM"
    assert plan["support"] == "PARTIAL"
