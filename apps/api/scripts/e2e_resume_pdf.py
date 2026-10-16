"""端到端生成一份真实 PDF：建档案 → 建岗位 → 定向简历 → Studio → 确认 → 导出 PDF。

前置：后端 API（默认 127.0.0.1:8100）与 Typst 已就绪。

用法：
  cd apps/api && PYTHONPATH=. .venv/Scripts/python.exe scripts/e2e_resume_pdf.py [输出路径]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

API = os.environ.get("AIOS_API", "http://127.0.0.1:8100")

JD = """公司：星野智能
职位：AI 产品经理（校招）
地点：上海
岗位职责：
1. 负责大模型产品的能力定义与需求拆解，输出 PRD 与评测方案；
2. 搭建产品指标体系，推动 RAG / Agent 能力在业务场景落地；
3. 与算法、研发、设计协作，完成从 0 到 1 的功能上线与迭代。
任职要求：
1. 本科及以上学历，2026 届优先；
2. 熟悉大模型基础能力，有 RAG 或 Agent 相关实践；
3. 具备较强的数据分析与跨部门沟通能力。
"""

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
            "dates": "2024.09-2026.06",
            "cet6_score": "520",
            "relevant_courses": ["机器学习", "人机交互"],
            "honors": ["一等学业奖学金"],
        }
    ],
    "skills": [
        {"name": "需求分析", "proficiency": "PROFICIENT"},
        {"name": "数据分析", "proficiency": "PROFICIENT"},
    ],
    "experiences": [
        {
            "title": "AI 产品实习",
            "organization": "示例科技有限公司",
            "dates": "2025.06-2025.12",
            "description": "负责内部知识库问答产品的需求拆解与评测方案设计，主导 3 次功能迭代，输出 12 份评测报告。",
            "experience_type": "INTERNSHIP",
        },
        {
            "title": "科研项目负责人",
            "organization": "示例大学智能计算实验室",
            "dates": "2024.10-2025.06",
            "description": "主导检索增强生成方向的科研项目，完成标注规范与实验设计，成果投稿至学术会议。",
            "experience_type": "PROJECT",
        },
    ],
    "certifications": [],
}

log: list[str] = []


def step(client: httpx.Client, name: str, method: str, path: str, **kwargs) -> httpx.Response | None:
    response = client.request(method, f"{API}{path}", **kwargs)
    ok = response.status_code < 400
    log.append(f"[{'OK ' if ok else 'ERR'}] {name} → HTTP {response.status_code}")
    print(log[-1])
    if not ok:
        print("      ", response.text[:300])
        return None
    return response


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../../.runtime/e2e-resume.pdf")

    with httpx.Client(timeout=180.0) as client:
        created = client.post(f"{API}/api/v1/profiles/draft").json()
        profile_id = created["profile_id"]
        step(client, "写入简历事实", "PUT", f"/api/v1/profiles/{profile_id}", json=PROFILE)

        mission_resp = step(
            client,
            "创建岗位",
            "POST",
            f"/api/v1/profiles/{profile_id}/job-missions",
            json={"raw_text": JD, "source_url": None},
        )
        if mission_resp is None:
            return 1
        mission_id = mission_resp.json()["id"]

        step(client, "绑定简历来源(master)", "POST", f"/api/v1/job-missions/{mission_id}/confirm-resume-source", json={"mode": "master"})
        step(client, "经历四分类生成", "POST", f"/api/v1/job-missions/{mission_id}/experience-selection/generate")
        selections = client.get(f"{API}/api/v1/job-missions/{mission_id}/experience-selection").json()
        items = [
            {
                "experience_id": item["experience_id"],
                "decision": item["decision"],
                "why": item.get("why") or "按岗位相关性保留。",
                "related_capabilities": item.get("related_capabilities") or [],
                "supporting_evidence_refs": item.get("supporting_evidence_refs") or [],
                "confidence": item.get("confidence", 0.8),
            }
            for item in (selections if isinstance(selections, list) else selections.get("selections", []))
        ]
        log.append(f"[OK ] 读取经历筛选 → {len(items)} 条")
        print(log[-1])
        step(
            client,
            "确认经历筛选",
            "PUT",
            f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true",
            json={"selections": items},
        )
        step(client, "简历策略", "POST", f"/api/v1/job-missions/{mission_id}/resume-strategy")
        step(client, "确认简历策略", "POST", f"/api/v1/job-missions/{mission_id}/confirm-strategy")
        step(client, "生成定向简历", "POST", f"/api/v1/job-missions/{mission_id}/target-resumes", content=b"")
        step(client, "确认定向简历", "POST", f"/api/v1/job-missions/{mission_id}/confirm-target-resume")

        studio = step(client, "创建 Studio 文档", "GET", f"/api/v1/job-missions/{mission_id}/resume-studio")
        if studio is None:
            return 1
        studio_body = studio.json()
        revision = studio_body.get("revision", 1)
        print(f"      Studio 修订号 = {revision}，模板 = {studio_body.get('template_id')}")

        confirmed = client.post(
            f"{API}/api/v1/job-missions/{mission_id}/resume-studio/confirm",
            headers={"If-Match": str(revision)},
        )
        log.append(f"[{'OK ' if confirmed.status_code < 400 else 'ERR'}] Studio 确认 → HTTP {confirmed.status_code}")
        print(log[-1])
        if confirmed.status_code >= 400:
            print("      ", confirmed.text[:400])
            # 仍然尝试导出 PDF，以便看到真实阻塞原因
            pdf = client.get(f"{API}/api/v1/job-missions/{mission_id}/resume-studio/pdf")
            log.append(f"[{'OK ' if pdf.status_code < 400 else 'ERR'}] 导出 PDF → HTTP {pdf.status_code}")
            print(log[-1], pdf.text[:300] if pdf.status_code >= 400 else "")
            return 1

        pdf = client.get(f"{API}/api/v1/job-missions/{mission_id}/resume-studio/pdf")
        step(client, "导出 PDF", "GET", f"/api/v1/job-missions/{mission_id}/resume-studio/pdf")
        if pdf.status_code >= 400 or not pdf.content.startswith(b"%PDF"):
            log.append("[ERR] PDF 内容不是有效的 PDF")
            print(log[-1])
            return 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(pdf.content)
        size = len(pdf.content)
        log.append(f"[OK ] PDF 已保存 → {out_path.resolve()} ({size} bytes)")
        print(log[-1])

        # 校验可提取文字
        import fitz

        with fitz.open(stream=pdf.content, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc)
            print(f"      PDF 页数 = {doc.page_count}，可提取文字 = {len(text)} 字符")
            print(f"      包含姓名：{'张三' in text}，包含岗位关键词：{'AI 产品经理' in text}")

    print("\n===== PDF 链路小结 =====")
    for line in log:
        print(" ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
