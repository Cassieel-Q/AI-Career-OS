"""Build expanded synthetic/public-inspired eval corpus (not consented_real)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
TODAY = "2026-10-09"


def w(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jd(jd_id, company, role_title, role_family, raw_text, expected, source_url, source_type="authored_synthetic"):
    return {
        "jd_id": jd_id,
        "company": company,
        "role_title": role_title,
        "role_family": role_family,
        "source_url": source_url,
        "source_type": source_type,
        "sample_class": "public_jd" if source_type == "public_inspired" else "synthetic",
        "consent_status": "n/a",
        "collected_at": TODAY,
        "raw_text": raw_text,
        "annotation_status": "synthetic_gold",
        "expected": expected,
        # Offline harness mirrors gold (smoke only). Live ignores offline_actual.
        "offline_actual": {
            k: expected[k]
            for k in (
                "company",
                "role_title",
                "location",
                "years_experience",
                "education",
                "responsibilities",
                "must_have",
                "preferred",
            )
            if k in expected
        },
    }


JDS = []

# Keep original 2
JDS.append(
    jd(
        "syn-jd-001",
        "Acme Labs",
        "AI Product Manager",
        "ai_product",
        "Acme Labs is hiring an AI Product Manager in Shanghai. 3+ years product experience required. Bachelor degree preferred. Responsibilities: own LLM evaluation roadmap; define success metrics; partner with engineering on RAG quality. Must-have: shipped an AI feature; experiment design. Preferred: Typst or document tooling familiarity.",
        {
            "company": "Acme Labs",
            "role_title": "AI Product Manager",
            "location": "Shanghai",
            "years_experience": "3+",
            "education": "Bachelor",
            "responsibilities": [
                "own LLM evaluation roadmap",
                "define success metrics",
                "partner with engineering on RAG quality",
            ],
            "must_have": ["shipped an AI feature", "experiment design"],
            "preferred": ["Typst or document tooling familiarity"],
            "requirement_labels": {
                "shipped an AI feature": "required",
                "experiment design": "required",
                "Typst or document tooling familiarity": "preferred",
            },
        },
        "synthetic://authored/acme-ai-pm",
    )
)
JDS.append(
    jd(
        "syn-jd-002",
        "Northstar Media",
        "Technical Product Manager",
        "technical_product",
        "Northstar Media seeks a Technical Product Manager (Hangzhou). 5 years experience. Master preferred. Own creator-tool roadmap; run A/B tests; write PRDs. Required: SQL literacy; cross-functional leadership. Nice to have: short-video domain.",
        {
            "company": "Northstar Media",
            "role_title": "Technical Product Manager",
            "location": "Hangzhou",
            "years_experience": "5",
            "education": "Master",
            "responsibilities": ["Own creator-tool roadmap", "run A/B tests", "write PRDs"],
            "must_have": ["SQL literacy", "cross-functional leadership"],
            "preferred": ["short-video domain"],
            "requirement_labels": {
                "SQL literacy": "required",
                "cross-functional leadership": "required",
                "short-video domain": "preferred",
            },
        },
        "synthetic://authored/northstar-tpm",
    )
)

# Public-inspired (cleaned Chinese JDs; not verbatim full scrape dumps)
PUBLIC = [
    (
        "pub-jd-baidu-001",
        "百度",
        "AI产品经理",
        "ai_product",
        "北京",
        "2+",
        "本科",
        """公司：百度
岗位：AI产品经理
地点：北京
年限：2年以上产品经验
学历：本科

职责：
1. 负责 AI 工具与工作台能力规划、需求拆解和产品落地，建设平台能力
2. 研究并对标行业优秀产品，关注 AI 创作工作台的产品形态，提炼可复用的工作流、资产和协作机制
3. 持续跟踪 AI 发展趋势，重点关注大模型、多模态、Agent、图像/视频/音频生成、自动化工作流、模型路由等方向，输出产品判断和路线图
4. 协同算法、研发、设计和业务团队，推动从 0 到 1 的能力建设和迭代
5. 建立产品指标体系，关注效率、稳定性、成本、成功率、复用率等核心指标

任职要求（必须）：
- 2年以上产品经验
- 有实际 AI 工具使用或产品化经验，能理解模型效果、时延、成本、稳定性和产品体验之间的取舍
- 具备较强的抽象和拆解能力，能把复杂生产流程整理成清晰的产品结构
- 有较强的跨团队协作和推进能力

加分项：
- 有 AI 工具、AIGC 产品、创作工具、工作流平台或 ToB 工具经验
- 结果导向，具备数据意识和迭代意识
""",
        [
            "负责 AI 工具与工作台能力规划",
            "跟踪大模型/多模态/Agent 趋势并输出路线图",
            "协同算法研发推动从0到1",
            "建立产品指标体系",
        ],
        ["2年以上产品经验", "AI工具产品化经验", "跨团队协作推进"],
        ["AIGC/工作流平台经验", "数据意识"],
        "https://watchjobs.net/zh/explore/job/c262-e07b63f8954b5aad/AI%E4%BA%A7%E5%93%81%E7%BB%8F%E7%90%86-J104842-%E7%99%BE%E5%BA%A6",
    ),
    (
        "pub-jd-baidu-002",
        "百度",
        "AI产品经理（企业效能方向）",
        "ai_product",
        "北京",
        "3-5",
        "本科",
        """公司：百度
岗位：AI产品经理（企业效能方向）
地点：北京海淀
年限：3-5年
学历：本科

职责：
1. 负责企业工作流的识别与分析，洞察组织流程与效率痛点
2. 负责 AI Agent 方向探索与落地，推动智能体在工作会议、招聘、数字员工等场景落地
3. 协调技术团队完成智能体设计、开发与沙盒实验，搭建效果指标看板
4. 牵头智能体产品设计、开发、运营全流程，对产品效果负责
5. 结合运营数据与用户反馈持续改善 Agent 效果

任职要求（必须）：
- 良好的产品 Sense 与痛点洞察力
- 具备大语言模型应用经验，理解模型能力边界与高质量 Prompt
- 熟悉 Agentic Workflow，有基于 AI 实现至少 1 个提效 Workflow/完整产品的经验

加分项：
- 主导跨部门协作项目
- 能独立完成产品 Demo
""",
        [
            "企业工作流识别与分析",
            "AI Agent 场景落地",
            "搭建效果指标看板",
            "智能体产品全流程管理",
        ],
        ["大语言模型应用经验", "Agentic Workflow 经验", "产品痛点洞察"],
        ["跨部门协作", "独立完成 Demo"],
        "https://www.quanzhi.com/job/6a50a62562f6005b2b0f6d55",
    ),
    (
        "pub-jd-baidu-003",
        "百度",
        "高级AI产品经理（Coding Agent）",
        "ai_product",
        "北京",
        "3+",
        "本科",
        """公司：百度
岗位：高级 AI 产品经理（Coding Agent 方向）
地点：北京
年限：3年以上
学历：本科及以上

职责：
1. 定义 Coding Agent 产品方向，包括能力边界、交互范式与自治等级路线图
2. 设计并维护 Agentic Evals 体系，覆盖准确率、延迟、崩溃恢复等维度
3. 与策略/算法团队合作，通过用户轨迹与竞品 Benchmark 驱动模型能力提升
4. 负责 Agent 模型版本发布规划与 readiness criteria
5. 使用 AI 编程工具亲自搭建原型，在交付工程前验证产品假设

任职要求（必须）：
- Agentic Evals 实战经验
- 深度使用 Claude Code / Cursor / Copilot 等 AI 编程工具
- 能与工程团队对话 Agent orchestration、沙箱、权限模型
- 系统化思考能力

加分项：
- 有开发者工具或 IDE 插件产品经验
""",
        [
            "定义 Coding Agent 产品方向",
            "设计 Agentic Evals",
            "版本发布与 readiness",
            "原型验证",
        ],
        ["Agentic Evals 实战", "AI编程工具深度使用", "系统化思考"],
        ["开发者工具产品经验"],
        "https://www.liepin.com/job/1983826771.shtml",
    ),
]

for row in PUBLIC:
    (
        jid,
        company,
        title,
        family,
        loc,
        years,
        edu,
        raw,
        resp,
        must,
        pref,
        url,
    ) = row
    labels = {m: "required" for m in must}
    labels.update({p: "preferred" for p in pref})
    JDS.append(
        jd(
            jid,
            company,
            title,
            family,
            raw,
            {
                "company": company,
                "role_title": title,
                "location": loc,
                "years_experience": years,
                "education": edu,
                "responsibilities": resp,
                "must_have": must,
                "preferred": pref,
                "requirement_labels": labels,
            },
            url,
            source_type="public_inspired",
        )
    )

AUTHORED = [
    (
        "syn-jd-003",
        "字节跳动",
        "大模型应用产品经理",
        "ai_product",
        "北京/上海",
        "3+",
        "本科",
        """公司：字节跳动
岗位：大模型应用产品经理
地点：北京/上海
年限：3年以上产品经验
学历：本科及以上

职责：
1. 负责面向内容创作者的大模型应用产品规划与落地
2. 定义 Prompt / RAG / Agent 能力在业务场景中的产品形态
3. 建立效果评测与灰度发布机制，推动算法与工程协同迭代
4. 拆解创作者工作流，沉淀可复用的模板与资产

任职要求：
- 3年以上互联网产品经验
- 有大模型或 AIGC 产品落地经验
- 熟悉数据驱动迭代与 A/B 实验
加分：短视频/内容社区经验；SQL
""",
        ["大模型应用产品规划", "定义 RAG/Agent 产品形态", "效果评测与灰度", "创作者工作流拆解"],
        ["3年以上产品经验", "大模型或AIGC落地经验", "A/B实验"],
        ["短视频经验", "SQL"],
    ),
    (
        "syn-jd-004",
        "阿里巴巴",
        "钉钉AI产品经理",
        "ai_product",
        "杭州",
        "3+",
        "本科",
        """公司：阿里巴巴（钉钉）
岗位：AI产品经理
地点：杭州
年限：3年以上
学历：本科

职责：负责钉钉智能助理与企业知识问答产品；设计 ToB 场景下的权限、审计与效果看板；协同算法做评测集与拒答策略。
必须：ToB 产品经验；大模型应用理解；跨团队推进
加分：企业协同/IM 经验；Python 基础
""",
        ["智能助理与企业知识问答", "权限审计与效果看板", "评测集与拒答策略"],
        ["ToB产品经验", "大模型应用理解", "跨团队推进"],
        ["企业协同/IM经验", "Python基础"],
    ),
    (
        "syn-jd-005",
        "腾讯",
        "混元应用产品经理",
        "ai_product",
        "深圳",
        "2+",
        "本科",
        """公司：腾讯
岗位：混元应用产品经理
地点：深圳
年限：2年以上
学历：本科及以上

职责：规划混元大模型在办公与创作场景的应用；定义多模态生成质量标准；推动插件生态与第三方接入。
必须：AI/内容产品经验；指标体系建设；PRD与需求管理
加分：插件平台经验；多模态生成产品经验
""",
        ["混元应用规划", "多模态质量标准", "插件生态"],
        ["AI或内容产品经验", "指标体系建设", "PRD与需求管理"],
        ["插件平台", "多模态生成经验"],
    ),
    (
        "syn-jd-006",
        "美团",
        "技术产品经理（搜索推荐）",
        "technical_product",
        "北京",
        "4+",
        "本科",
        """公司：美团
岗位：技术产品经理（搜索推荐）
地点：北京
年限：4年以上
学历：本科

职责：负责到店搜索与推荐策略产品；与算法定义排序目标与评估指标；推动实验平台与特征需求。
必须：搜索或推荐产品经验；SQL；实验设计
加分：本地生活业务理解；机器学习基础
""",
        ["搜索推荐策略产品", "排序目标与评估指标", "实验平台与特征需求"],
        ["搜索或推荐产品经验", "SQL", "实验设计"],
        ["本地生活业务", "机器学习基础"],
    ),
    (
        "syn-jd-007",
        "MiniMax",
        "AI产品经理",
        "ai_product",
        "上海",
        "2+",
        "本科",
        """公司：MiniMax
岗位：AI产品经理
地点：上海
年限：2年以上
学历：本科

职责：负责对话 Agent 与语音交互产品；设计评测集与人工标注流程；平衡时延、成本与效果。
必须：对话/Agent 产品经验；评测与标注流程；用户研究基础
加分：语音交互；开源模型调优经验
""",
        ["对话Agent与语音交互", "评测集与标注流程", "时延成本效果平衡"],
        ["对话或Agent产品经验", "评测与标注流程", "用户研究基础"],
        ["语音交互", "开源模型调优"],
    ),
    (
        "syn-jd-008",
        "OPPO",
        "AI产品经理（端侧）",
        "ai_product",
        "深圳",
        "3+",
        "本科",
        """公司：OPPO
岗位：AI产品经理（端侧智能）
地点：深圳
年限：3年以上
学历：本科

职责：规划手机端侧大模型能力；定义端云协同策略；推动影像/助手场景落地与功耗体验权衡。
必须：消费电子或 OS 产品经验；AI 功能落地经验；跨硬件软件协作
加分：端侧推理；影像算法产品经验
""",
        ["端侧大模型能力规划", "端云协同策略", "影像/助手场景落地"],
        ["消费电子或OS产品经验", "AI功能落地", "软硬件协作"],
        ["端侧推理", "影像算法产品"],
    ),
    (
        "syn-jd-009",
        "小米",
        "产品经理（车载智能助手）",
        "product_manager",
        "北京",
        "3+",
        "本科",
        """公司：小米
岗位：产品经理（车载智能助手）
地点：北京
年限：3年以上
学历：本科

职责：负责车载语音助手与多模态交互；定义车内场景话术与安全策略；协同座舱软件与云端大模型。
必须：智能硬件或车载产品经验；语音交互；需求分析与原型
加分：座舱 HMI；大模型 Prompt 设计
""",
        ["车载语音助手与多模态交互", "场景话术与安全策略", "协同座舱与云端大模型"],
        ["智能硬件或车载产品经验", "语音交互", "需求分析与原型"],
        ["座舱HMI", "Prompt设计"],
    ),
    (
        "syn-jd-010",
        "商汤科技",
        "AI产品经理（视觉）",
        "ai_product",
        "上海",
        "3+",
        "硕士",
        """公司：商汤科技
岗位：AI产品经理（计算机视觉）
地点：上海
年限：3年以上
学历：硕士优先

职责：负责视觉大模型行业解决方案产品化；定义交付指标与验收标准；支持售前与标杆客户落地。
必须：CV 或视觉产品经验；ToB 交付；客户需求转化
加分：智慧城市/制造场景；英文沟通
""",
        ["视觉大模型方案产品化", "交付指标与验收", "售前与标杆客户"],
        ["CV或视觉产品经验", "ToB交付", "客户需求转化"],
        ["智慧城市或制造", "英文沟通"],
    ),
    (
        "syn-jd-011",
        "智谱AI",
        "大模型产品经理",
        "ai_product",
        "北京",
        "2+",
        "本科",
        """公司：智谱AI
岗位：大模型产品经理
地点：北京
年限：2年以上
学历：本科及以上

职责：负责 GLM 应用与 API 产品体验；设计开发者文档与配额策略；建设模型能力评测与案例库。
必须：开发者产品或 API 产品经验；大模型理解；文档与社区运营意识
加分：开源社区；Python
""",
        ["GLM应用与API产品体验", "开发者文档与配额", "能力评测与案例库"],
        ["开发者或API产品经验", "大模型理解", "文档与社区意识"],
        ["开源社区", "Python"],
    ),
    (
        "syn-jd-012",
        "快手",
        "产品经理（创作者工具）",
        "product_manager",
        "北京",
        "3+",
        "本科",
        """公司：快手
岗位：产品经理（创作者工具）
地点：北京
年限：3年以上
学历：本科

职责：负责短视频创作与剪辑工具；用 A/B 实验优化转化；沉淀模板与素材市场。
必须：内容/创作者产品经验；A/B 实验；数据分析
加分：剪辑工具；增长经验
""",
        ["短视频创作剪辑工具", "A/B实验优化转化", "模板与素材市场"],
        ["创作者产品经验", "A/B实验", "数据分析"],
        ["剪辑工具", "增长经验"],
    ),
    (
        "syn-jd-013",
        "网易",
        "技术产品经理（游戏AI）",
        "technical_product",
        "杭州",
        "4+",
        "本科",
        """公司：网易
岗位：技术产品经理（游戏AI）
地点：杭州
年限：4年以上
学历：本科

职责：负责游戏内 NPC / 剧情生成 AI 能力产品化；定义安全与合规策略；协同引擎与算法团队。
必须：游戏或互动娱乐产品经验；AI 功能落地；跨团队项目管理
加分：剧情系统；LLM 安全
""",
        ["NPC/剧情生成AI产品化", "安全与合规策略", "协同引擎与算法"],
        ["游戏或互动娱乐产品经验", "AI功能落地", "跨团队项目管理"],
        ["剧情系统", "LLM安全"],
    ),
]

for row in AUTHORED:
    jid, company, title, family, loc, years, edu, raw, resp, must, pref = row
    labels = {m: "required" for m in must}
    labels.update({p: "preferred" for p in pref})
    JDS.append(
        jd(
            jid,
            company,
            title,
            family,
            raw,
            {
                "company": company,
                "role_title": title,
                "location": loc,
                "years_experience": years,
                "education": edu,
                "responsibilities": resp,
                "must_have": must,
                "preferred": pref,
                "requirement_labels": labels,
            },
            f"synthetic://authored/{jid}",
            source_type="authored_synthetic",
        )
    )

assert len(JDS) >= 15, len(JDS)

# --- Resumes (synthetic only) ---
RESUMES = [
    {
        "resume_id": "syn-resume-001",
        "sample_class": "synthetic",
        "consent_status": "n/a",
        "source_type": "synthetic",
        "display_name": "Syn Candidate A",
        "raw_text": """Syn Candidate A — AI / Technical Product Manager
Email: syn.candidate.a@example.com | Shanghai

EXPERIENCE

LLM Evaluation Internship | University Lab | 2024.01 - 2024.06
- Built an offline LLM judge set with 120 labeled prompts and tracked agreement versus human raters.
- Partnered with two engineers on RAG quality metrics for an internal demo.

Campus Bookstore Cashier | University Store | 2023.01 - 2023.12
- Operated the cash register and restocked shelves during peak campus hours.

RAG Prototype Project | Personal / Lab | 2024.07 - 2024.09
- Shipped an internal RAG demo used by 3 product managers for evidence lookup.
- Documented failure modes and evaluation criteria for retrieval quality.

Creator A/B Test Lead | Campus Media Club | 2023.06 - 2023.12
- Ran A/B tests on creator-tool onboarding copy and wrote short PRDs for the club product.

EDUCATION
B.S. Computer Science, Example University, 2024

SKILLS
LLM evaluation, experiment design, RAG, SQL literacy, product metrics, PRD writing, cross-functional leadership
""",
        "experiences": [
            {"experience_id": "syn-resume-001-exp-001", "title": "LLM Evaluation Internship"},
            {"experience_id": "syn-resume-001-exp-002", "title": "Campus Bookstore Cashier"},
            {"experience_id": "syn-resume-001-exp-003", "title": "RAG Prototype Project"},
            {"experience_id": "syn-resume-001-exp-004", "title": "Creator A/B Test Lead"},
        ],
    },
    {
        "resume_id": "syn-resume-002",
        "sample_class": "synthetic",
        "consent_status": "n/a",
        "source_type": "synthetic",
        "display_name": "Syn Candidate B",
        "raw_text": """Syn Candidate B — AI Product Manager
Email: syn.candidate.b@example.com | Beijing

EXPERIENCE

Agent Workflow Platform PM | Orion SaaS | 2022.03 - 2025.08
- Shipped an internal Agent workflow builder used by 40 ops specialists; cut ticket handling time 18%.
- Designed prompt templates, human-in-the-loop review, and weekly quality dashboards with engineering.

Food Delivery Courier Part-time | City Express | 2019.06 - 2019.09
- Delivered meals across three districts during summer peak; no product ownership.

Multimodal Demo Lab | Open Source Weekend | 2024.01 - 2024.04
- Prototyped image+text generation demo and wrote eval checklist for latency and refusal cases.

EDUCATION
M.S. HCI, Northern Institute, 2022

SKILLS
Agent workflows, Prompt design, product metrics, ToB collaboration, A/B tests, PRD
""",
        "experiences": [
            {"experience_id": "syn-resume-002-exp-001", "title": "Agent Workflow Platform PM"},
            {"experience_id": "syn-resume-002-exp-002", "title": "Food Delivery Courier Part-time"},
            {"experience_id": "syn-resume-002-exp-003", "title": "Multimodal Demo Lab"},
        ],
    },
    {
        "resume_id": "syn-resume-003",
        "sample_class": "synthetic",
        "consent_status": "n/a",
        "source_type": "synthetic",
        "display_name": "Syn Candidate C",
        "raw_text": """Syn Candidate C — Technical Product Manager
Email: syn.candidate.c@example.com | Hangzhou

EXPERIENCE

Search Ranking TPM | River Retail | 2020.01 - 2025.06
- Owned search ranking product requirements; defined NDCG and offline/online evaluation with ML team.
- Ran 30+ A/B experiments on recall and ranking features using SQL-heavy analysis.

Coffee Shop Barista | Neighborhood Cafe | 2018.01 - 2018.12
- Prepared drinks and managed inventory; unrelated to product work.

Creator Tool Growth PM | ShortClip Studio | 2018.06 - 2019.12
- Launched template marketplace and measured creator retention with cohort dashboards.

EDUCATION
B.S. Statistics, East Lake University, 2018

SKILLS
SQL, A/B experiments, search/recommendation product, PRD, cross-functional leadership
""",
        "experiences": [
            {"experience_id": "syn-resume-003-exp-001", "title": "Search Ranking TPM"},
            {"experience_id": "syn-resume-003-exp-002", "title": "Coffee Shop Barista"},
            {"experience_id": "syn-resume-003-exp-003", "title": "Creator Tool Growth PM"},
        ],
    },
    {
        "resume_id": "syn-resume-004",
        "sample_class": "synthetic",
        "consent_status": "n/a",
        "source_type": "synthetic",
        "display_name": "Syn Candidate D",
        "raw_text": """Syn Candidate D — AI Product (Developer Tools)
Email: syn.candidate.d@example.com | Shenzhen

EXPERIENCE

Coding Agent Eval Lead | DevForge | 2023.02 - 2025.09
- Built Agentic Evals covering task success, latency, and crash recovery for an IDE coding agent.
- Daily user of Cursor and Copilot; wrote readiness criteria before model releases.

Supermarket Cashier Weekend | FreshMart | 2017.03 - 2017.10
- Weekend cashier shifts; no software product relevance.

API Developer Portal PM | CloudNode | 2021.01 - 2023.01
- Owned developer docs, quota UX, and example galleries for an LLM API product.

EDUCATION
B.Eng. Software Engineering, South Harbor University, 2017

SKILLS
Agentic Evals, developer products, API UX, documentation, release readiness
""",
        "experiences": [
            {"experience_id": "syn-resume-004-exp-001", "title": "Coding Agent Eval Lead"},
            {"experience_id": "syn-resume-004-exp-002", "title": "Supermarket Cashier Weekend"},
            {"experience_id": "syn-resume-004-exp-003", "title": "API Developer Portal PM"},
        ],
    },
    {
        "resume_id": "syn-resume-005",
        "sample_class": "synthetic",
        "consent_status": "n/a",
        "source_type": "synthetic",
        "display_name": "Syn Candidate E",
        "raw_text": """Syn Candidate E — Hardware / Voice Product
Email: syn.candidate.e@example.com | Beijing

EXPERIENCE

In-Car Voice Assistant PM | AutoNova | 2021.05 - 2025.07
- Defined car voice scenes, safety refusal policy, and multi-turn dialog metrics with cockpit software.
- Partnered with cloud LLM vendors on latency and wake-word tradeoffs.

Campus Library Shelving Aide | Uni Library | 2016.09 - 2017.06
- Shelved books; no PM ownership.

Smartphone Assistant Feature PM | Handset Co | 2018.07 - 2021.04
- Shipped on-device assistant features balancing power, privacy, and accuracy.

EDUCATION
B.S. Industrial Design, Capital Design College, 2016

SKILLS
voice interaction, smart hardware, HMI, on-device AI tradeoffs, requirements & prototypes
""",
        "experiences": [
            {"experience_id": "syn-resume-005-exp-001", "title": "In-Car Voice Assistant PM"},
            {"experience_id": "syn-resume-005-exp-002", "title": "Campus Library Shelving Aide"},
            {"experience_id": "syn-resume-005-exp-003", "title": "Smartphone Assistant Feature PM"},
        ],
    },
    {
        "resume_id": "syn-resume-006",
        "sample_class": "synthetic",
        "consent_status": "n/a",
        "source_type": "synthetic",
        "display_name": "Syn Candidate F",
        "raw_text": """Syn Candidate F — Vision / ToB AI Product
Email: syn.candidate.f@example.com | Shanghai

EXPERIENCE

Vision Solution PM | SightWorks | 2019.04 - 2025.05
- Productized computer-vision solutions for manufacturing QA; defined acceptance metrics with customers.
- Led pre-sales workshops and converted three lighthouse accounts.

Wedding Photographer Side Gig | Freelance | 2018.01 - 2018.12
- Weekend photography gigs; not AI product work.

Knowledge Base RAG PM | Enterprise Wiki | 2025.06 - 2025.09
- Shipped enterprise knowledge QA with permissions, audit logs, and refusal evaluation set.

EDUCATION
M.S. Computer Vision, East China Tech, 2019

SKILLS
CV products, ToB delivery, customer discovery, RAG permissions, acceptance metrics
""",
        "experiences": [
            {"experience_id": "syn-resume-006-exp-001", "title": "Vision Solution PM"},
            {"experience_id": "syn-resume-006-exp-002", "title": "Wedding Photographer Side Gig"},
            {"experience_id": "syn-resume-006-exp-003", "title": "Knowledge Base RAG PM"},
        ],
    },
]

# --- Match cases ---
MATCH = []

def match_case(cid, jd_id, resume_id, labels, high_priority):
    resume = next(r for r in RESUMES if r["resume_id"] == resume_id)
    exps = [{"experience_id": e["experience_id"], "title": e["title"]} for e in resume["experiences"]]
    # Only include experiences that have labels
    exps = [e for e in exps if e["experience_id"] in labels]
    offline = dict(labels)
    return {
        "case_id": cid,
        "jd_id": jd_id,
        "resume_id": resume_id,
        "sample_class": "synthetic",
        "experiences": exps,
        "expected_labels": labels,
        "expected_high_priority_experience_ids": high_priority,
        "offline_actual_labels": offline,
    }

# resume-001
MATCH.append(match_case("syn-match-001", "syn-jd-001", "syn-resume-001", {
    "syn-resume-001-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-001-exp-002": "OMIT",
    "syn-resume-001-exp-003": "KEEP",
}, ["syn-resume-001-exp-001", "syn-resume-001-exp-003"]))
MATCH.append(match_case("syn-match-002", "syn-jd-002", "syn-resume-001", {
    "syn-resume-001-exp-001": "KEEP",
    "syn-resume-001-exp-002": "OMIT",
    "syn-resume-001-exp-003": "DEEMPHASIZE",
    "syn-resume-001-exp-004": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-001-exp-004"]))
MATCH.append(match_case("syn-match-003", "pub-jd-baidu-001", "syn-resume-001", {
    "syn-resume-001-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-001-exp-002": "OMIT",
    "syn-resume-001-exp-003": "KEEP_AND_HIGHLIGHT",
    "syn-resume-001-exp-004": "KEEP",
}, ["syn-resume-001-exp-001", "syn-resume-001-exp-003"]))

# resume-002
MATCH.append(match_case("syn-match-004", "pub-jd-baidu-002", "syn-resume-002", {
    "syn-resume-002-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-002-exp-002": "OMIT",
    "syn-resume-002-exp-003": "KEEP",
}, ["syn-resume-002-exp-001"]))
MATCH.append(match_case("syn-match-005", "syn-jd-003", "syn-resume-002", {
    "syn-resume-002-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-002-exp-002": "OMIT",
    "syn-resume-002-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-002-exp-001", "syn-resume-002-exp-003"]))
MATCH.append(match_case("syn-match-006", "syn-jd-007", "syn-resume-002", {
    "syn-resume-002-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-002-exp-002": "OMIT",
    "syn-resume-002-exp-003": "KEEP",
}, ["syn-resume-002-exp-001"]))

# resume-003
MATCH.append(match_case("syn-match-007", "syn-jd-006", "syn-resume-003", {
    "syn-resume-003-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-003-exp-002": "OMIT",
    "syn-resume-003-exp-003": "KEEP",
}, ["syn-resume-003-exp-001"]))
MATCH.append(match_case("syn-match-008", "syn-jd-002", "syn-resume-003", {
    "syn-resume-003-exp-001": "KEEP",
    "syn-resume-003-exp-002": "OMIT",
    "syn-resume-003-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-003-exp-003"]))
MATCH.append(match_case("syn-match-009", "syn-jd-012", "syn-resume-003", {
    "syn-resume-003-exp-001": "DEEMPHASIZE",
    "syn-resume-003-exp-002": "OMIT",
    "syn-resume-003-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-003-exp-003"]))

# resume-004
MATCH.append(match_case("syn-match-010", "pub-jd-baidu-003", "syn-resume-004", {
    "syn-resume-004-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-004-exp-002": "OMIT",
    "syn-resume-004-exp-003": "KEEP",
}, ["syn-resume-004-exp-001"]))
MATCH.append(match_case("syn-match-011", "syn-jd-011", "syn-resume-004", {
    "syn-resume-004-exp-001": "KEEP",
    "syn-resume-004-exp-002": "OMIT",
    "syn-resume-004-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-004-exp-003"]))
MATCH.append(match_case("syn-match-012", "syn-jd-005", "syn-resume-004", {
    "syn-resume-004-exp-001": "KEEP",
    "syn-resume-004-exp-002": "OMIT",
    "syn-resume-004-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-004-exp-003"]))

# resume-005
MATCH.append(match_case("syn-match-013", "syn-jd-009", "syn-resume-005", {
    "syn-resume-005-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-005-exp-002": "OMIT",
    "syn-resume-005-exp-003": "KEEP",
}, ["syn-resume-005-exp-001"]))
MATCH.append(match_case("syn-match-014", "syn-jd-008", "syn-resume-005", {
    "syn-resume-005-exp-001": "KEEP",
    "syn-resume-005-exp-002": "OMIT",
    "syn-resume-005-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-005-exp-003"]))

# resume-006
MATCH.append(match_case("syn-match-015", "syn-jd-010", "syn-resume-006", {
    "syn-resume-006-exp-001": "KEEP_AND_HIGHLIGHT",
    "syn-resume-006-exp-002": "OMIT",
    "syn-resume-006-exp-003": "KEEP",
}, ["syn-resume-006-exp-001"]))
MATCH.append(match_case("syn-match-016", "syn-jd-004", "syn-resume-006", {
    "syn-resume-006-exp-001": "KEEP",
    "syn-resume-006-exp-002": "OMIT",
    "syn-resume-006-exp-003": "KEEP_AND_HIGHLIGHT",
}, ["syn-resume-006-exp-003"]))
MATCH.append(match_case("syn-match-017", "syn-jd-013", "syn-resume-006", {
    "syn-resume-006-exp-001": "KEEP",
    "syn-resume-006-exp-002": "OMIT",
    "syn-resume-006-exp-003": "DEEMPHASIZE",
}, ["syn-resume-006-exp-001"]))

assert len(MATCH) >= 15

# --- Rewrite units (≥15); human scores left as placeholders for offline only; live = UNRATED ---
REWRITE = []
# Keep original two
REWRITE.extend(
    [
        {
            "unit_id": "syn-rewrite-001",
            "case_id": "syn-match-001",
            "jd_id": "syn-jd-001",
            "resume_id": "syn-resume-001",
            "experience_id": "syn-resume-001-exp-001",
            "source_facts": ["Built offline LLM judge set with 120 labeled prompts"],
            "suggestion_text": "Built an offline LLM evaluation set with 120 labeled prompts and tracked agreement vs human raters.",
            "bullet_count": 1,
            "expected_scores": {"factuality": 5, "jd_fit": 5, "completeness": 4, "clarity": 5, "adoptable": 5},
            "critical_fact_error": False,
            "offline_actual": {
                "suggestion_text": "Built an offline LLM evaluation set with 120 labeled prompts and tracked agreement vs human raters.",
                "bullet_count": 1,
                "critical_fact_error": False,
                "unsupported_number": False,
            },
        },
        {
            "unit_id": "syn-rewrite-002",
            "case_id": "syn-match-001",
            "jd_id": "syn-jd-001",
            "resume_id": "syn-resume-001",
            "experience_id": "syn-resume-001-exp-003",
            "source_facts": ["Shipped internal RAG demo used by 3 PMs"],
            "suggestion_text": "Interviewed 50 creators about RAG quality and improved conversion by 28%.",
            "bullet_count": 1,
            "expected_scores": {"factuality": 1, "jd_fit": 2, "completeness": 2, "clarity": 3, "adoptable": 1},
            "critical_fact_error": True,
            "notes": "Synthetic negative: fabricates interviews and conversion metric not in source_facts.",
            "offline_actual": {
                "suggestion_text": "Interviewed 50 creators about RAG quality and improved conversion by 28%.",
                "bullet_count": 1,
                "critical_fact_error": True,
                "unsupported_number": True,
            },
        },
    ]
)

extra_rewrite = [
    ("syn-rewrite-003", "syn-match-004", "pub-jd-baidu-002", "syn-resume-002", "syn-resume-002-exp-001",
     ["Shipped Agent workflow builder used by 40 ops specialists"], False),
    ("syn-rewrite-004", "syn-match-004", "pub-jd-baidu-002", "syn-resume-002", "syn-resume-002-exp-002",
     ["Delivered meals across three districts"], False),
    ("syn-rewrite-005", "syn-match-007", "syn-jd-006", "syn-resume-003", "syn-resume-003-exp-001",
     ["Owned search ranking requirements; NDCG with ML team"], False),
    ("syn-rewrite-006", "syn-match-007", "syn-jd-006", "syn-resume-003", "syn-resume-003-exp-002",
     ["Prepared drinks and managed inventory"], False),
    ("syn-rewrite-007", "syn-match-010", "pub-jd-baidu-003", "syn-resume-004", "syn-resume-004-exp-001",
     ["Built Agentic Evals for IDE coding agent"], False),
    ("syn-rewrite-008", "syn-match-010", "pub-jd-baidu-003", "syn-resume-004", "syn-resume-004-exp-002",
     ["Weekend cashier shifts"], False),
    ("syn-rewrite-009", "syn-match-011", "syn-jd-011", "syn-resume-004", "syn-resume-004-exp-003",
     ["Owned developer docs and quota UX for LLM API"], False),
    ("syn-rewrite-010", "syn-match-013", "syn-jd-009", "syn-resume-005", "syn-resume-005-exp-001",
     ["Defined car voice scenes and safety refusal policy"], False),
    ("syn-rewrite-011", "syn-match-014", "syn-jd-008", "syn-resume-005", "syn-resume-005-exp-003",
     ["Shipped on-device assistant features"], False),
    ("syn-rewrite-012", "syn-match-015", "syn-jd-010", "syn-resume-006", "syn-resume-006-exp-001",
     ["Productized CV solutions for manufacturing QA"], False),
    ("syn-rewrite-013", "syn-match-016", "syn-jd-004", "syn-resume-006", "syn-resume-006-exp-003",
     ["Shipped enterprise knowledge QA with permissions"], False),
    ("syn-rewrite-014", "syn-match-005", "syn-jd-003", "syn-resume-002", "syn-resume-002-exp-003",
     ["Prototyped image+text generation demo"], False),
    ("syn-rewrite-015", "syn-match-003", "pub-jd-baidu-001", "syn-resume-001", "syn-resume-001-exp-001",
     ["Built offline LLM judge set with 120 labeled prompts"], False),
    ("syn-rewrite-016", "syn-match-008", "syn-jd-002", "syn-resume-003", "syn-resume-003-exp-003",
     ["Launched template marketplace; measured creator retention"], False),
    ("syn-rewrite-017", "syn-match-012", "syn-jd-005", "syn-resume-004", "syn-resume-004-exp-003",
     ["Example galleries for LLM API product"], False),
]

for uid, cid, jid, rid, eid, facts, bad in extra_rewrite:
    suggestion = facts[0] if not bad else "Grew MAU by 300% after interviewing 50 creators (fabricated)."
    REWRITE.append(
        {
            "unit_id": uid,
            "case_id": cid,
            "jd_id": jid,
            "resume_id": rid,
            "experience_id": eid,
            "source_facts": facts,
            "suggestion_text": suggestion,
            "bullet_count": 1,
            "expected_scores": {
                "factuality": 1 if bad else 4,
                "jd_fit": 2 if bad else 4,
                "completeness": 2 if bad else 4,
                "clarity": 3 if bad else 4,
                "adoptable": 1 if bad else 4,
            },
            "critical_fact_error": bad,
            "human_scores_status": "UNRATED",
            "offline_actual": {
                "suggestion_text": suggestion,
                "bullet_count": 1,
                "critical_fact_error": bad,
                "unsupported_number": bad,
            },
        }
    )

assert len(REWRITE) >= 15

# --- Interview (≥5 packs / ≥15 questions) ---
INTERVIEW = []
packs = [
    ("syn-interview-001", "syn-jd-001", "syn-resume-001", [
        ("q1", "How did you design the LLM evaluation set for Acme-like AI PM work?", True, True, False),
        ("q2", "Tell me about a time you interviewed 50 creators for content analysis.", True, False, True),
        ("q3", "How would you partner with engineering on RAG quality metrics?", True, True, False),
    ]),
    ("syn-interview-002", "pub-jd-baidu-002", "syn-resume-002", [
        ("q1", "Describe an Agent workflow you shipped and how you measured effect.", True, True, False),
        ("q2", "How do you design sandbox experiments for enterprise agents?", True, True, False),
        ("q3", "Walk through a courier logistics optimization you led at Baidu.", False, False, True),
    ]),
    ("syn-interview-003", "pub-jd-baidu-003", "syn-resume-004", [
        ("q1", "How did you build Agentic Evals for coding agents?", True, True, False),
        ("q2", "What readiness criteria do you use before releasing an agent model?", True, True, False),
        ("q3", "Explain how you optimized supermarket POS conversion with LLMs.", False, False, True),
    ]),
    ("syn-interview-004", "syn-jd-009", "syn-resume-005", [
        ("q1", "How did you define safety refusal for in-car voice?", True, True, False),
        ("q2", "How do you balance latency and wake-word accuracy with vendors?", True, True, False),
        ("q3", "Describe library shelving automation you productized.", False, False, True),
    ]),
    ("syn-interview-005", "syn-jd-010", "syn-resume-006", [
        ("q1", "How did you set acceptance metrics for manufacturing CV QA?", True, True, False),
        ("q2", "How do you run ToB lighthouse customer discovery?", True, True, False),
        ("q3", "Tell me about wedding photo RAG search product you shipped for SenseTime.", False, False, True),
    ]),
]

for case_id, jd_id, resume_id, qs in packs:
    for qid, question, jd_g, res_g, fact_err in qs:
        INTERVIEW.append(
            {
                "case_id": case_id,
                "jd_id": jd_id,
                "resume_id": resume_id,
                "question_id": f"{case_id}-{qid}",
                "question": question,
                "sample_class": "synthetic",
                "expected": {
                    "jd_grounded": jd_g,
                    "resume_grounded": res_g,
                    "uses_target_company_intel_only": True,
                    "synthetic_demo_forbidden": True,
                    "duplicate": False,
                    **({"reference_answer_fact_error": True} if fact_err else {}),
                },
                "offline_actual": {
                    "jd_grounded": jd_g,
                    "resume_grounded": res_g,
                    "uses_target_company_intel_only": True,
                    "synthetic_demo_forbidden": True,
                    "duplicate": False,
                    **({"reference_answer_fact_error": True} if fact_err else {}),
                    "cited_skill_ids": [],
                },
            }
        )

assert len({r["case_id"] for r in INTERVIEW}) >= 5
assert len(INTERVIEW) >= 15

# Write fixtures
w(FIX / "jd" / "synthetic_offline.json", JDS)
w(FIX / "resume" / "synthetic_expanded.json", RESUMES)
w(FIX / "match" / "synthetic_offline.json", MATCH)
w(FIX / "rewrite" / "synthetic_offline.json", REWRITE)
w(FIX / "interview" / "synthetic_offline.json", INTERVIEW)

manifest = {
    "manifest_id": "expanded-synthetic-public-v1",
    "created_at": TODAY,
    "git_baseline_note": "Local feature/eval-benchmark-v1; integration still not pushed.",
    "disclaimer": "Corpus is public_inspired JD + authored synthetic JD + fully synthetic resumes. NOT consented_real. Live metrics != real-user study.",
    "collection": {
        "jd_total": len(JDS),
        "jd_public_inspired": sum(1 for j in JDS if j.get("source_type") == "public_inspired"),
        "jd_authored_synthetic": sum(1 for j in JDS if j.get("source_type") != "public_inspired"),
        "resume_total": len(RESUMES),
        "resume_all_synthetic": True,
        "match_cases": len(MATCH),
        "rewrite_units": len(REWRITE),
        "interview_questions": len(INTERVIEW),
        "interview_packs": len({r["case_id"] for r in INTERVIEW}),
        "companies": sorted({j["company"] for j in JDS}),
        "role_families": sorted({j["role_family"] for j in JDS}),
    },
    "plan_vs_actual": {
        "EVAL-JD": {"planned": 30, "actual_fixtures": len(JDS), "note": "synthetic/public_inspired; not consented_real"},
        "EVAL-MATCH": {"planned": 30, "actual_fixtures": len(MATCH), "note": "synthetic resume x JD pairs"},
        "EVAL-REWRITE": {"planned": 90, "actual_fixtures": len(REWRITE), "note": "human 1-5 UNRATED on live"},
        "EVAL-INTERVIEW": {
            "planned_cases": 10,
            "planned_questions": 50,
            "actual_packs": len({r["case_id"] for r in INTERVIEW}),
            "actual_fixtures": len(INTERVIEW),
            "note": "structural live checks; grounding UNRATED",
        },
        "consented_real_resumes": {"planned": 10, "actual": 0, "note": "still NOT_RUN"},
    },
    "suites": {
        "jd": {"fixture": "fixtures/jd/synthetic_offline.json", "count": len(JDS)},
        "match": {"fixture": "fixtures/match/synthetic_offline.json", "count": len(MATCH)},
        "rewrite": {"fixture": "fixtures/rewrite/synthetic_offline.json", "count": len(REWRITE)},
        "interview": {"fixture": "fixtures/interview/synthetic_offline.json", "count": len(INTERVIEW)},
        "resume": {"fixture": "fixtures/resume/synthetic_expanded.json", "count": len(RESUMES)},
    },
    "privacy": {
        "synthetic_only_resumes": True,
        "no_consented_real": True,
        "private_dir": "evals/benchmark/private/",
        "runs_dir": "evals/benchmark/runs/",
    },
}
w(ROOT / "manifests" / "offline_fixture_manifest.json", manifest)

# Collection log (git-safe metadata)
w(
    ROOT / "manifests" / "corpus_collection_log.json",
    {
        "collected_at": TODAY,
        "public_inspired_jds": [
            {"jd_id": j["jd_id"], "source_url": j["source_url"], "company": j["company"]}
            for j in JDS
            if j.get("source_type") == "public_inspired"
        ],
        "authored_jds": [j["jd_id"] for j in JDS if j.get("source_type") != "public_inspired"],
        "note": "Public pages used as inspiration; cleaned Chinese text stored. Resumes are fictional.",
    },
)

print(
    json.dumps(
        {
            "jd": len(JDS),
            "resume": len(RESUMES),
            "match": len(MATCH),
            "rewrite": len(REWRITE),
            "interview_q": len(INTERVIEW),
            "interview_packs": len({r["case_id"] for r in INTERVIEW}),
            "public_inspired": sum(1 for j in JDS if j.get("source_type") == "public_inspired"),
        },
        indent=2,
    )
)
