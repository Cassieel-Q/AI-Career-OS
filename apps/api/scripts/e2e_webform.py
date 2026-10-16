"""网申填表端到端验收：真实 API + 真实受控浏览器 + 本地测试表单页。

流程：建档案 → 写资料 → 打开受控浏览器 → 读取表单 → 匹配预览 → 用户确认 → 填写 → 回读校验 → 检查历史。

前置：
  - 后端 API 运行在 127.0.0.1:8000（可用 start-local.cmd）
  - 前端运行在 127.0.0.1:3000（测试页 /webform-test.html 由 next dev 提供）
  - 受控浏览器桥运行在 127.0.0.1:8770（start-browser-bridge.cmd）

用法：
  cd apps/api && PYTHONPATH=. .venv/Scripts/python.exe scripts/e2e_webform.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

API = os.environ.get("AIOS_API", "http://127.0.0.1:8000")
BRIDGE = "http://127.0.0.1:8770"
TEST_PAGE = "http://127.0.0.1:3000/webform-test.html"

PROFILE = {
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
}

APPLICATION = {
    "id_number": "310000000000000000",
    "emergency_contact": "李四",
    "emergency_phone": "13900000000",
    "availability": "一个月内",
    "family_info": "父母均在原籍",
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append((name, ok, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' — ' + note) if note else ''}")


def main() -> int:
    with httpx.Client(timeout=60.0) as client:
        # 0. 服务可达性
        health = client.get(f"{API}/health")
        check("后端 /health 可访问", health.status_code == 200, f"HTTP {health.status_code}")
        bridge = client.get(f"{BRIDGE}/health")
        check("受控浏览器桥可访问", bridge.status_code == 200, f"HTTP {bridge.status_code}")

        # 1. 建档案并写入资料
        created = client.post(f"{API}/api/v1/profiles/draft").json()
        profile_id = created.get("profile_id") or created.get("id")
        check("创建档案", bool(profile_id), profile_id)
        updated = client.put(f"{API}/api/v1/profiles/{profile_id}", json=PROFILE)
        check("写入简历事实", updated.status_code == 200, f"HTTP {updated.status_code}")
        app_saved = client.put(f"{API}/api/v1/profiles/{profile_id}/application-profile", json=APPLICATION)
        check("写入网申资料", app_saved.status_code == 200, f"HTTP {app_saved.status_code}")

        facts = client.get(f"{API}/api/v1/profiles/{profile_id}/application-fill-facts").json()
        check("网申可读事实包含敏感字段", facts.get("application", {}).get("id_number") == APPLICATION["id_number"])

        # 2. 打开受控浏览器到本地测试页
        opened = client.post(f"{API}/api/v1/webform/session/start", json={"url": TEST_PAGE}).json()
        check("打开受控浏览器并加载测试页", TEST_PAGE in (opened.get("pageUrl") or ""), opened.get("pageUrl", ""))
        if TEST_PAGE not in (opened.get("pageUrl") or ""):
            return finish()

        # 3. 读取表单 + 匹配
        read = client.get(f"{API}/api/v1/profiles/{profile_id}/webform/read").json()
        plans = {item["label"]: item for item in read["plans"]}
        check("读取到表单字段", read["summary"]["total"] >= 12, f"字段数 {read['summary']['total']}")

        name_plan = plans.get("姓名")
        check("姓名匹配到资料并标记可填写", bool(name_plan and name_plan["status"] == "READY" and name_plan["value"] == "张三"))
        degree_plan = plans.get("最高学历")
        check("下拉框匹配到「硕士」", bool(degree_plan and degree_plan["status"] == "READY" and degree_plan["value"] == "硕士"))
        date_plan = plans.get("毕业时间")
        check("日期控件支持程度为部分支持", bool(date_plan and date_plan["support"] == "PARTIAL"))
        file_plan = plans.get("简历附件")
        check("文件上传标记为不支持", bool(file_plan and file_plan["status"] == "UNSUPPORTED"))
        pwd_plan = plans.get("登录密码")
        check("密码字段被拦截", bool(pwd_plan and pwd_plan["status"] == "BLOCKED"))
        code_plan = plans.get("短信验证码")
        check("验证码字段被拦截", bool(code_plan and code_plan["status"] == "BLOCKED"))
        unknown_plan = plans.get("求职意向")
        check("单选框支持程度为部分支持", bool(unknown_plan and unknown_plan["support"] == "PARTIAL"))

        # 4. 用户勾选「可填写」的字段并执行填写
        assignments = [
            {
                "index": item["index"],
                "selector": item["selector"],
                "control": item["control"],
                "label": item["label"],
                "value": item["value"],
            }
            for item in read["plans"]
            if item["status"] == "READY"
        ]
        check("存在可填写字段", len(assignments) > 0, f"{len(assignments)} 项")

        filled = client.post(
            f"{API}/api/v1/profiles/{profile_id}/webform/fill",
            json={"page_url": read["page_url"], "page_title": read["page_title"], "assignments": assignments},
        ).json()
        check("填写未触发提交", filled["summary"]["submitted"] is False)
        check(
            "填写成功数 = 提交项数",
            filled["summary"]["filled"] == len(assignments),
            f"成功 {filled['summary']['filled']} / 提交 {len(assignments)}",
        )

        # 5. 回读页面校验真实写入的值
        verify = client.get(f"{API}/api/v1/profiles/{profile_id}/webform/read").json()
        values = {item["label"]: item.get("value", "") for item in verify["fields"]}
        check("页面上的姓名已写入", values.get("姓名") == "张三", repr(values.get("姓名")))
        check("页面上的手机号已写入", values.get("手机号") == "13800000000", repr(values.get("手机号")))
        check("页面上的邮箱已写入", values.get("电子邮箱") == "zhangsan@example.com", repr(values.get("电子邮箱")))
        check("页面上的学校已写入", values.get("毕业院校") == "示例大学", repr(values.get("毕业院校")))
        check("下拉框已选中硕士", values.get("最高学历") == "硕士", repr(values.get("最高学历")))
        check("密码框保持为空", values.get("登录密码", "") == "", repr(values.get("登录密码")))
        check("验证码框保持为空", values.get("短信验证码", "") == "", repr(values.get("短信验证码")))

        # 6. 历史记录
        records = client.get(f"{API}/api/v1/profiles/{profile_id}/webform/records").json()["records"]
        check("写入了一条填写历史", len(records) == 1, f"{len(records)} 条")
        if records:
            blob = json.dumps(records[0], ensure_ascii=False)
            check("历史中不含密码值", "secret" not in blob and '"password"' not in blob)

        # 7. 备份导出 + 恢复
        export = client.get(f"{API}/api/v1/backup/export")
        check("备份导出成功", export.status_code == 200 and len(export.content) > 1000, f"{len(export.content)} bytes")
        inspect = client.post(f"{API}/api/v1/backup/inspect", files={"file": ("backup.zip", export.content, "application/zip")}).json()
        check("备份完整性校验通过", inspect.get("integrity_ok") is True)
        check("备份清单记录了档案数", inspect.get("counts", {}).get("user_profiles", 0) >= 1, str(inspect.get("counts")))
        restored = client.post(
            f"{API}/api/v1/backup/restore",
            files={"file": ("backup.zip", export.content, "application/zip")},
            params={"label": "E2E 恢复数据集"},
        )
        if restored.status_code == 200:
            body = restored.json()
            check("恢复为新数据集", bool(body.get("dataset_id")), body.get("dataset_id", ""))
            check("原数据集未被覆盖", body.get("previous_dataset_id") != body.get("dataset_id"))
            # 切换后回读记录（模拟「重启后核对」）
            time.sleep(0.5)
            switched = client.get(f"{API}/api/v1/backup/summary").json()
            check(
                "恢复后数据可读且记录一致",
                switched.get("counts", {}).get("user_profiles", 0) >= 1,
                str(switched.get("counts", {}).get("user_profiles")),
            )
        else:
            check("恢复为新数据集", False, f"HTTP {restored.status_code}: {restored.text[:160]}")

    return finish()


def finish() -> int:
    passed = sum(1 for _n, ok, _note in results if ok)
    total = len(results)
    print(f"\n===== 网申 E2E 结果：{passed}/{total} 通过 =====")
    for name, ok, note in results:
        if not ok:
            print(f"  未通过：{name} — {note}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
