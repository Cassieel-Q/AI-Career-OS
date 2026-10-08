"""Deterministic, fictional content for actual template gallery renders."""
from uuid import NAMESPACE_URL, uuid5


def sample_document(language: str) -> dict:
    en = language == "en"

    def node(key: str, text: str) -> dict:
        return {
            "id": str(uuid5(NAMESPACE_URL, f"ai-career-gallery/{language}/{key}")),
            "text": text,
            "source_kind": "system",
            "source_id": None,
            "evidence_refs": [],
            "risk_level": "LOW",
            "claim_status": "CONFIRMED",
        }

    def entry(key: str, title: str, subtitle: str, date: str, bullets: list[str]) -> dict:
        return {
            "id": str(uuid5(NAMESPACE_URL, f"ai-career-gallery/{language}/{key}")),
            "status": "INCLUDED",
            "title": node(f"{key}/title", title),
            "subtitle": node(f"{key}/subtitle", subtitle),
            "date": node(f"{key}/date", date),
            "location": node(f"{key}/location", "上海" if not en else "Shanghai"),
            "bullets": [node(f"{key}/bullet/{i}", text) for i, text in enumerate(bullets)],
        }

    def section(key: str, title: str, entries: list[dict]) -> dict:
        return {"id": str(uuid5(NAMESPACE_URL, f"ai-career-gallery/{language}/{key}")), "kind": key, "title": node(f"{key}/title", title), "entries": entries}

    basics = {
        "name": node("name", "Lin Chen" if en else "陈林"),
        "phone": node("phone", "+86 138 0000 0000"),
        "email": node("email", "lin.chen@example.com"),
        "location": node("location", "Shanghai, China" if en else "中国 · 上海"),
    }
    if en:
        sections = [
            section("experience", "EXPERIENCE", [
                entry("exp1", "Product Operations Lead", "Northstar Digital · Fictional company", "2022–Present", ["Built a weekly review process across product and support teams.", "Reduced response time by 24% through clearer ownership and tracking."]),
                entry("exp2", "Operations Analyst", "Harbor Studio · Fictional company", "2019–2022", ["Created an executive dashboard for cross-team planning.", "Coordinated a pilot with 12 partners and documented the rollout."]),
            ]),
            section("education", "EDUCATION", [entry("edu", "Eastlake University", "B.A. · Information Management", "2015–2019", [])]),
            section("skills", "SKILLS", [entry("skill1", "Data analysis", "SQL · spreadsheets · reporting", "", []), entry("skill2", "Cross-team coordination", "Planning · documentation", "", [])]),
        ]
    else:
        sections = [
            section("experience", "工作经历", [
                entry("exp1", "产品运营负责人", "北辰数字 · 虚构企业", "2022—至今", ["建立产品与客服团队的每周复盘机制，明确责任与行动项。", "通过流程优化将响应时间缩短 24%，并建立持续追踪看板。"]),
                entry("exp2", "运营分析师", "港湾工作室 · 虚构企业", "2019—2022", ["搭建面向管理层的业务看板，支持跨团队计划制定。", "协调 12 家合作伙伴开展试点，完成上线文档与反馈整理。"]),
            ]),
            section("education", "教育经历", [entry("edu", "东湖大学", "信息管理 · 本科", "2015—2019", [])]),
            section("skills", "技能", [entry("skill1", "数据分析", "SQL · 电子表格 · 业务报告", "", []), entry("skill2", "跨团队协作", "规划 · 文档协作", "", [])]),
        ]
    return {"schema_version": 1, "basics": basics, "sections": sections}
