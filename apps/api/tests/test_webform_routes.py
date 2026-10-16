"""网申填表路由测试：读取 → 预览 → 填写 → 记录（浏览器桥用桩替换）。"""
from __future__ import annotations

from app import webform_routes

FAKE_FIELDS = [
    {"index": 0, "tag": "input", "type": "text", "name": "fullName", "label": "姓名", "selector": '[data-aios-field="0"]', "required": True},
    {"index": 1, "tag": "input", "type": "email", "name": "email", "label": "电子邮箱", "selector": '[data-aios-field="1"]'},
    {"index": 2, "tag": "select", "type": "select", "name": "degree", "label": "最高学历", "selector": '[data-aios-field="2"]', "options": ["本科", "硕士"]},
    {"index": 3, "tag": "input", "type": "file", "name": "resume", "label": "简历附件", "selector": '[data-aios-field="3"]'},
    {"index": 4, "tag": "input", "type": "password", "name": "password", "label": "登录密码", "selector": '[data-aios-field="4"]'},
]


def _patch_read(monkeypatch):
    monkeypatch.setattr(
        webform_routes.browser,
        "read_page",
        lambda: {"fields": FAKE_FIELDS, "pageUrl": "http://127.0.0.1:3000/webform-test.html", "pageTitle": "测试表单"},
    )


def test_status_reports_bridge_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        webform_routes.browser,
        "health",
        lambda: {"available": False, "bridge_url": "http://127.0.0.1:8770", "error": "未启动"},
    )
    body = client.get("/api/v1/webform/status").json()
    assert body["available"] is False


def test_read_returns_plan_and_summary(client, persisted_profile, db_session, monkeypatch):
    persisted_profile.full_name = "张三"
    db_session.add(persisted_profile)
    db_session.commit()
    _patch_read(monkeypatch)
    body = client.get(f"/api/v1/profiles/{persisted_profile.id}/webform/read").json()
    assert body["page_title"] == "测试表单"
    assert body["summary"]["total"] == 5
    statuses = {item["index"]: item["status"] for item in body["plans"]}
    assert statuses[0] == "READY"  # 姓名来自档案
    assert statuses[3] == "UNSUPPORTED"  # 文件
    assert statuses[4] == "BLOCKED"  # 密码
    assert body["summary"]["blocked"] >= 1


def test_fill_executes_and_records_history(client, persisted_profile, monkeypatch):
    _patch_read(monkeypatch)

    def fake_fill(assignments):
        return {
            "results": [
                {"selector": item["selector"], "label": item["label"], "ok": True, "reason": ""} for item in assignments
            ],
            "pageUrl": "http://127.0.0.1:3000/webform-test.html",
            "pageTitle": "测试表单",
        }

    monkeypatch.setattr(webform_routes.browser, "fill_page", fake_fill)

    payload = {
        "page_url": "http://127.0.0.1:3000/webform-test.html",
        "page_title": "测试表单",
        "assignments": [
            {"index": 0, "selector": '[data-aios-field="0"]', "control": "text", "label": "姓名", "value": "张三"},
            {"index": 4, "selector": '[data-aios-field="4"]', "control": "password", "label": "登录密码", "value": "secret"},
        ],
    }
    body = client.post(f"/api/v1/profiles/{persisted_profile.id}/webform/fill", json=payload).json()
    assert body["summary"]["filled"] == 1
    assert body["summary"]["submitted"] is False
    assert any(item["control"] == "password" for item in body["rejected"])

    records = client.get(f"/api/v1/profiles/{persisted_profile.id}/webform/records").json()["records"]
    assert len(records) == 1
    assert records[0]["status"] == "FILLED"
    # 历史里绝不出现密码值
    assert "secret" not in str(records[0])


def test_fill_rejects_when_all_assignments_empty(client, persisted_profile, monkeypatch):
    payload = {
        "page_url": "http://x",
        "assignments": [{"index": 0, "selector": "#a", "control": "text", "label": "姓名", "value": "  "}],
    }
    response = client.post(f"/api/v1/profiles/{persisted_profile.id}/webform/fill", json=payload)
    assert response.status_code == 422
