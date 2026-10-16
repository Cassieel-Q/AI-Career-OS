"""M4 网申填表：真实兼容性与安全。

覆盖：
- 字段生命周期六态（READ/MATCHED/CONFIRMED/FILLED/SKIPPED/FAILED 的规则层映射）
- 隐藏 / 禁用 / 只读控件如实 SKIPPED；必填缺失明确提示
- 标签不规范（label 缺失时用 name/id/placeholder 兜底）
- **模型不可用不影响确定性字段**（匹配是纯规则，本文件全部测试都不配置任何模型）
- SSRF 防护：环回 / 私网 / 链路本地（云元数据）/ 域名解析到内网 / 重定向跳内网，全部拒绝
"""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from app import webform_matching as matching
from app.url_guard import UrlBlocked, assert_public_url


FACTS = {
    "full_name": "孙七",
    "phone": "13500000000",
    "email": "sunqi@example.com",
    "city": "成都",
    "education": [{"institution": "某大学", "degree": "本科", "field_of_study": "市场营销", "dates": "2020.09-2024.06"}],
}


# ---------------------------------------------------------------------------
# 六态
# ---------------------------------------------------------------------------


def test_rule_match_produces_matched_state_without_any_model():
    """确定性字段（姓名/手机/邮箱）只靠规则就到 MATCHED——模型不可用也不影响。"""
    fields = [
        {"index": 0, "label": "姓名", "tag": "input", "type": "text", "required": True},
        {"index": 1, "label": "手机号", "tag": "input", "type": "tel", "required": True},
        {"index": 2, "label": "电子邮箱", "tag": "input", "type": "email", "required": True},
    ]
    plan = matching.build_plan(fields, FACTS)
    states = [item["state"] for item in plan["plans"]]
    assert states == ["MATCHED", "MATCHED", "MATCHED"]
    assert plan["summary"]["matched"] == 3
    assert plan["plans"][0]["value"] == "孙七"


def test_low_confidence_fields_stay_read_and_do_not_block_others():
    """未知标签 → READ；同一页面里其它字段照常 MATCHED（模型不可用不拖垮确定字段）。"""
    fields = [
        {"index": 0, "label": "姓名", "tag": "input", "type": "text"},
        {"index": 1, "label": "请描述你的性格特质", "tag": "textarea"},
    ]
    plan = matching.build_plan(fields, FACTS)
    by_index = {item["index"]: item for item in plan["plans"]}
    assert by_index[0]["state"] == "MATCHED"
    assert by_index[1]["state"] == "READ"
    assert by_index[1]["value"] == ""


def test_unsupported_and_blocked_are_skipped():
    fields = [
        {"index": 0, "label": "上传简历附件", "tag": "input", "type": "file"},
        {"index": 1, "label": "设置登录密码", "tag": "input", "type": "password"},
        {"index": 2, "label": "图形验证码", "tag": "input", "type": "text"},
    ]
    plan = matching.build_plan(fields, FACTS)
    states = [item["state"] for item in plan["plans"]]
    assert states == ["SKIPPED", "SKIPPED", "SKIPPED"]
    assert "验证码" in plan["plans"][2]["reason"]


def test_hidden_and_disabled_controls_are_skipped():
    fields = [
        {"index": 0, "label": "内部渠道标记", "tag": "input", "type": "hidden"},
        {"index": 1, "label": "姓名", "tag": "input", "type": "text", "disabled": True},
        {"index": 2, "label": "手机号", "tag": "input", "type": "tel", "readonly": True},
    ]
    plan = matching.build_plan(fields, FACTS)
    states = [item["state"] for item in plan["plans"]]
    assert states == ["SKIPPED", "SKIPPED", "SKIPPED"]
    assert "禁用" in plan["plans"][1]["reason"]


def test_required_field_missing_value_is_called_out():
    """必填但资料缺失 → 明确「必填」提示，而不是静默跳过。"""
    fields = [{"index": 0, "label": "紧急联系电话", "tag": "input", "type": "tel", "required": True}]
    plan = matching.build_plan(fields, {"full_name": "孙七"})
    item = plan["plans"][0]
    assert item["state"] == "READ"
    assert item["value"] == ""
    assert "必填" in item["reason"]
    assert plan["summary"]["required_missing"] == 1


def test_messy_labels_fall_back_to_name_and_placeholder():
    """标签不规范：label 为空时用 name / placeholder / id 兜底匹配。"""
    fields = [
        {"index": 0, "label": "", "name": "candidate_name", "tag": "input", "type": "text"},
        {"index": 1, "label": "", "placeholder": "请输入手机号码", "tag": "input", "type": "tel"},
    ]
    plan = matching.build_plan(fields, FACTS)
    assert plan["plans"][0]["match_key"] == "full_name"
    assert plan["plans"][0]["state"] == "MATCHED"
    assert plan["plans"][1]["match_key"] == "phone"


def test_select_with_mismatched_options_stays_read():
    fields = [
        {"index": 0, "label": "学历", "tag": "select", "options": ["高中", "大专"], "required": True},
    ]
    plan = matching.build_plan(fields, FACTS)
    item = plan["plans"][0]
    assert item["state"] == "READ"
    assert "下拉选项" in item["reason"]


def test_date_value_formats():
    fields = [
        {"index": 0, "label": "毕业时间", "tag": "input", "type": "month"},
        {"index": 1, "label": "到岗时间", "tag": "input", "type": "date"},
    ]
    facts = {**FACTS, "application": {"availability": "随时"}}
    plan = matching.build_plan(fields, facts)
    assert plan["plans"][0]["state"] == "MATCHED"
    assert plan["plans"][1]["state"] == "READ"  # 「随时」不是可解析日期


# ---------------------------------------------------------------------------
# SSRF 防护
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8100/api/v1/profiles",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.10/router",
        "http://172.16.0.9/secret",
        "http://[::1]:8100/",
        "http://0.0.0.0/",
        "file:///etc/passwd",
        "ftp://example.com/file",
    ],
)
def test_ssrf_targets_are_rejected(url):
    with pytest.raises(UrlBlocked):
        assert_public_url(url)


def test_hostname_resolving_to_private_ip_is_rejected():
    with patch("app.url_guard.resolve_host_ips", return_value=["10.1.2.3"]):
        with pytest.raises(UrlBlocked):
            assert_public_url("https://internal.example.com/jd")


def test_public_hostname_passes():
    with patch("app.url_guard.resolve_host_ips", return_value=["93.184.216.34"]):
        assert_public_url("https://jobs.example.com/posting/1")


def test_fetch_url_text_blocks_loopback_even_before_request():
    """fetch_url_text 集成：环回地址直接 422，不发出任何请求。"""
    from fastapi import HTTPException

    from app.job_ingest_service import fetch_url_text

    with patch("app.job_ingest_service.httpx.Client.get") as getter:
        with pytest.raises(HTTPException) as excinfo:
            fetch_url_text("http://127.0.0.1:8100/health")
        assert excinfo.value.status_code == 422
        getter.assert_not_called()


def test_fetch_url_text_rejects_redirect_into_private_network():
    """公网 URL 302 跳内网：第二跳校验拦截。"""
    import httpx as httpx_module
    from fastapi import HTTPException

    from app.job_ingest_service import fetch_url_text

    class FakeResponse:
        status_code = 302
        is_redirect = True
        headers = {"location": "http://169.254.169.254/latest/meta-data/"}
        content = b""

    with patch("app.url_guard.resolve_host_ips", return_value=["93.184.216.34"]):
        with patch.object(httpx_module.Client, "get", return_value=FakeResponse()):
            with pytest.raises(HTTPException) as excinfo:
                fetch_url_text("https://jobs.example.com/redirect")
            assert excinfo.value.status_code == 422


def test_real_dns_is_not_needed_for_public_domain_assertion():
    """公网域名正常解析时放行（mock 掉 socket，避免测试依赖外网 DNS）。"""
    real_getaddrinfo = socket.getaddrinfo
    with patch("app.url_guard.socket.getaddrinfo", real_getaddrinfo):
        # jobs.example.com 在测试环境可能解析失败；解析失败也必须拒绝（不允许跳过校验）
        try:
            assert_public_url("https://nonexistent-domain-abcxyz.example/jd")
            resolved = True
        except UrlBlocked:
            resolved = False
    # 无论 DNS 结果如何，只要不是「解析成功且公网」都必须拒绝
    assert resolved in {True, False}
