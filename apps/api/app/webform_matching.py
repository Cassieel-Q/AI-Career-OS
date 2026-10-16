"""网申填表：字段目录 + 取值匹配引擎（纯函数，可离线单测）。

职责边界：
- 输入「页面字段清单 + 网申可读事实」，输出「逐字段的填写计划」；
- **不接触**密码、验证码、提交按钮：这些控件在读取阶段就被标记为不可填；
- 只做「值从哪来 + 该不该填」的判断，不做任何网络或浏览器副作用。

控件支持程度（对齐需求「明确区分支持程度」）：
- ``FULL``  文本框 / 多行文本 / 邮箱 / 电话 / 数字
- ``FULL``  下拉框（选项能匹配到值时）
- ``PARTIAL`` 单选框（仅当选项文本能匹配）
- ``PARTIAL`` 日期（仅当值能标准化成可填格式）
- ``LIMITED`` 复选框（仅单选型的「确认」类）
- ``UNSUPPORTED`` 文件上传、富文本、自定义控件
- ``BLOCKED`` 密码、验证码、隐藏域、提交按钮（永不填写、永不记录）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- 控件类型 → 支持程度 -----------------------------------------------------
CONTROL_SUPPORT = {
    "text": "FULL",
    "textarea": "FULL",
    "email": "FULL",
    "tel": "FULL",
    "number": "FULL",
    "url": "FULL",
    "select": "FULL",
    "radio": "PARTIAL",
    "date": "PARTIAL",
    "month": "PARTIAL",
    "checkbox": "LIMITED",
    "file": "UNSUPPORTED",
    "password": "BLOCKED",
    "hidden": "BLOCKED",
    "submit": "BLOCKED",
    "button": "BLOCKED",
    "captcha": "BLOCKED",
    "unknown": "UNSUPPORTED",
}

BLOCKED_TYPES = {"password", "hidden", "submit", "button", "captcha"}

#: 登录/验证码相关的关键词：命中即视为不可自动化处理。
_CAPTCHA_HINTS = ("验证码", "captcha", "verification code", "短信码")

# --- 字段生命周期六态（M4 对齐） ---------------------------------------------
# READ       已读取页面字段，但规则没有把握（低置信）——等用户确认或模型辅助（模型不可用也不影响其它字段）
# MATCHED    规则匹配成功、资料里有值（高置信，可直接执行）
# CONFIRMED  用户在预览里确认过（执行层把用户确认的 assignment 视为 CONFIRMED 再写入）
# FILLED     已写入页面
# SKIPPED    不填（不支持/被封锁/用户跳过/禁用控件）
# FAILED     执行写入失败
FIELD_STATES = ("READ", "MATCHED", "CONFIRMED", "FILLED", "SKIPPED", "FAILED")

#: 规则层状态 → 六态（执行层 FILLED/FAILED 由 fill 结果决定，CONFIRMED 由用户确认决定）
_PLAN_STATE = {
    "READY": "MATCHED",
    "NEEDS_CONFIRM": "READ",
    "UNSUPPORTED": "SKIPPED",
    "BLOCKED": "SKIPPED",
}


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    keywords: tuple[str, ...]
    priority: int = 50
    control_types: tuple[str, ...] = ()


#: 字段目录：key → 标签 + 中英文同义词。顺序即匹配优先级参考。
FIELD_CATALOG: tuple[FieldSpec, ...] = (
    FieldSpec("full_name", "姓名", ("姓名", "名字", "姓名（中文）", "name", "full name", "yourname", "realname", "candidate name"), 10),
    FieldSpec("phone", "手机号", ("手机", "手机号", "联系电话", "电话", "手机号码", "phone", "mobile", "tel", "telephone", "cell"), 11),
    FieldSpec("email", "邮箱", ("邮箱", "电子邮箱", "邮件", "email", "e-mail", "mail"), 12),
    FieldSpec("id_number", "身份证号", ("身份证", "身份证号", "证件号码", "id number", "id card", "identity"), 20, ("text",)),
    FieldSpec("city", "现居城市", ("现居", "城市", "所在城市", "现居住地", "city", "location", "current city"), 13),
    FieldSpec("school", "毕业院校", ("学校", "毕业院校", "院校", "学校名称", "school", "university", "college", "institution"), 30),
    FieldSpec("degree", "学历", ("学历", "最高学历", "学位", "degree", "education", "qualification"), 31),
    FieldSpec("major", "专业", ("专业", "所学专业", "major", "field of study", "discipline"), 32),
    FieldSpec("graduation", "毕业时间", ("毕业时间", "毕业年月", "graduation", "graduate date", "graduation date"), 33, ("text", "date", "month", "select")),
    FieldSpec("cet4", "CET-4 成绩", ("四级", "cet4", "cet-4", "cet 4"), 34),
    FieldSpec("cet6", "CET-6 成绩", ("六级", "cet6", "cet-6", "cet 6"), 35),
    FieldSpec("emergency_contact", "紧急联系人", ("紧急联系人", "紧急联络人", "emergency contact"), 40, ("text",)),
    FieldSpec("emergency_phone", "紧急联系电话", ("紧急联系电话", "紧急电话", "emergency phone"), 41, ("text", "tel")),
    FieldSpec("availability", "到岗时间", ("到岗", "入职时间", "可到岗", "availability", "available from", "start date"), 42),
    FieldSpec("archive_location", "档案所在地", ("档案", "档案所在地", "archive"), 43, ("text",)),
    FieldSpec("health_status", "健康状况", ("健康", "健康状况", "health"), 44, ("text", "textarea", "select")),
    FieldSpec("family_info", "家庭情况", ("家庭", "家庭情况", "family"), 45, ("textarea", "text")),
)

#: 敏感 / 永不填写的字段关键词（即使被误判为普通文本框也拒绝）。
_FORBIDDEN_LABEL_HINTS = ("密码", "password", "passwd", "验证码", "captcha", "短信码")

_LABEL_CLEAN_RE = re.compile(r"[\s\*＊:：()（）\[\]【】]+")


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    lowered = _LABEL_CLEAN_RE.sub("", str(text)).lower()
    return lowered


def build_fact_values(facts: dict) -> dict[str, str]:
    """把网申可读事实摊平成 key → 文本值。"""
    education = facts.get("education") or []
    edu = education[0] if education else {}
    application = facts.get("application") or {}
    values = {
        "full_name": facts.get("full_name"),
        "phone": facts.get("phone"),
        "email": facts.get("email"),
        "city": facts.get("city"),
        "school": edu.get("institution"),
        "degree": edu.get("degree"),
        "major": edu.get("field_of_study"),
        "graduation": edu.get("dates"),
        "cet4": edu.get("cet4_score"),
        "cet6": edu.get("cet6_score"),
        "id_number": application.get("id_number"),
        "family_info": application.get("family_info"),
        "health_status": application.get("health_status"),
        "archive_location": application.get("archive_location"),
        "emergency_contact": application.get("emergency_contact"),
        "emergency_phone": application.get("emergency_phone"),
        "availability": application.get("availability"),
    }
    return {key: (str(value).strip() if value not in (None, "") else "") for key, value in values.items()}


def _match_spec(haystack: str) -> FieldSpec | None:
    best: tuple[int, FieldSpec] | None = None
    for spec in FIELD_CATALOG:
        for keyword in spec.keywords:
            if keyword in haystack:
                # 关键词越长越具体，越优先；其次看字段自身的 priority。
                score = len(keyword) * 100 - spec.priority
                if best is None or score > best[0]:
                    best = (score, spec)
    return best[1] if best else None


def _control_type(raw: dict) -> str:
    tag = (raw.get("tag") or "").lower()
    input_type = (raw.get("type") or "text").lower()
    if tag == "textarea":
        return "textarea"
    if tag == "select":
        return "select"
    if input_type in {"email", "tel", "number", "url", "date", "month", "password", "file", "hidden", "submit", "button", "checkbox", "radio"}:
        return input_type
    return "text"


def _is_captcha(raw: dict, haystack: str) -> bool:
    if any(hint in haystack for hint in _CAPTCHA_HINTS):
        return True
    name = ((raw.get("name") or "") + " " + (raw.get("id") or "")).lower()
    # 明确的验证码命名；裸「code」太宽（ref_code/promo_code 是普通业务字段），必须同时出现验证词。
    if any(hint in name for hint in ("captcha", "verify", "vcode")):
        return True
    has_code_token = "code" in name.replace("_", " ").split() or name.endswith("code")
    return has_code_token and any(hint in haystack for hint in _CAPTCHA_HINTS)


def _value_fits_control(value: str, control: str, options: list[str] | None) -> tuple[bool, str]:
    if control == "select":
        if not options:
            return False, "下拉框没有可读选项，无法确认目标值"
        for option in options:
            if value.strip().lower() in str(option).strip().lower() or str(option).strip().lower() in value.strip().lower():
                return True, ""
        return False, "下拉选项里没有与资料匹配的值，需人工选择"
    if control in {"date", "month"}:
        if re.match(r"^\d{4}[-/年.]?\d{0,2}", value.strip()):
            return True, ""
        return False, "日期控件需要标准日期，资料中的时间不是可解析格式"
    return True, ""


def plan_field(raw: dict, facts: dict, values: dict[str, str]) -> dict:
    """为单个页面字段生成填写计划。"""
    control = _control_type(raw)
    support = CONTROL_SUPPORT.get(control, "UNSUPPORTED")
    label = (raw.get("label") or raw.get("placeholder") or raw.get("name") or raw.get("id") or "").strip()
    haystack = _normalize(" ".join([label, raw.get("name") or "", raw.get("id") or "", raw.get("placeholder") or ""]))

    base = {
        "index": raw.get("index"),
        "label": label,
        "control": control,
        "support": support,
        "required": bool(raw.get("required")),
        "selector": raw.get("selector") or "",
    }

    # 隐藏 / 禁用控件：如实标为 SKIPPED（页面上用户也看不到或改不了）。
    if raw.get("disabled") or raw.get("readonly") is True:
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "SKIPPED", "state": "SKIPPED", "reason": "控件被禁用/只读，跳过"}
    if raw.get("hidden"):
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "SKIPPED", "state": "SKIPPED", "reason": "隐藏控件，跳过"}
    # 确认类勾选（隐私政策 / 同意条款）永远由人工完成：勾选即法律确认，系统不代劳。
    # 桥的 label 启发式对 checkbox 可能取错标题（比如把页面文案当成字段名），更不能替用户勾。
    if control == "checkbox":
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "SKIPPED", "state": "SKIPPED", "reason": "确认类勾选由人工完成，系统不代劳"}

    if _is_captcha(raw, haystack):
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "BLOCKED", "state": "SKIPPED", "reason": "验证码类字段，永不自动填写"}
    if control in BLOCKED_TYPES:
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "BLOCKED", "state": "SKIPPED", "reason": "密码/隐藏/按钮类控件，永不自动填写"}
    if any(hint in haystack for hint in _FORBIDDEN_LABEL_HINTS):
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "BLOCKED", "state": "SKIPPED", "reason": "疑似密码字段，已拒绝填写"}
    if control == "file":
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "UNSUPPORTED", "state": "SKIPPED", "reason": "文件上传控件，请手动选择文件"}
    if support == "UNSUPPORTED":
        return {**base, "match_key": None, "match_label": None, "value": "", "status": "UNSUPPORTED", "state": "SKIPPED", "reason": "暂不支持的控件类型"}

    spec = _match_spec(haystack)
    if spec is None:
        return {
            **base,
            "match_key": None,
            "match_label": None,
            "value": "",
            "status": "NEEDS_CONFIRM",
            "state": "READ",
            "reason": "未匹配到已知字段（规则置信度低），请人工确认；模型不可用不影响其它字段",
        }

    value = values.get(spec.key, "")
    if not value:
        state = "READ"
        reason = f"匹配到「{spec.label}」，但资料里没有该字段的值"
        if base["required"]:
            reason = f"必填字段「{spec.label}」在资料里没有值，请人工补充"
        return {
            **base,
            "match_key": spec.key,
            "match_label": spec.label,
            "value": "",
            "status": "NEEDS_CONFIRM",
            "state": state,
            "reason": reason,
        }

    fits, why = _value_fits_control(value, control, raw.get("options"))
    if not fits:
        return {
            **base,
            "match_key": spec.key,
            "match_label": spec.label,
            "value": "",
            "status": "NEEDS_CONFIRM",
            "state": "READ",
            "reason": why,
        }

    return {
        **base,
        "match_key": spec.key,
        "match_label": spec.label,
        "value": value,
        "status": "READY",
        "state": "MATCHED",
        "reason": f"来自已保存资料「{spec.label}」",
    }


def build_plan(fields: list[dict], facts: dict) -> dict:
    """为整页字段生成填写计划 + 统计（纯规则，不依赖任何模型服务）。"""
    values = build_fact_values(facts)
    plans = [plan_field(raw, facts, values) for raw in fields]
    summary = {
        "total": len(plans),
        "ready": sum(1 for item in plans if item["status"] == "READY"),
        "needs_confirm": sum(1 for item in plans if item["status"] == "NEEDS_CONFIRM"),
        "unsupported": sum(1 for item in plans if item["status"] == "UNSUPPORTED"),
        "blocked": sum(1 for item in plans if item["status"] == "BLOCKED"),
        # 六态统计（M4）
        "matched": sum(1 for item in plans if item.get("state") == "MATCHED"),
        "read": sum(1 for item in plans if item.get("state") == "READ"),
        "skipped": sum(1 for item in plans if item.get("state") == "SKIPPED"),
        "required_missing": sum(1 for item in plans if item.get("required") and not item.get("value") and item.get("state") != "SKIPPED"),
    }
    by_support: dict[str, int] = {}
    for item in plans:
        by_support[item["support"]] = by_support.get(item["support"], 0) + 1
    summary["by_support"] = by_support
    return {"plans": plans, "summary": summary, "fact_keys_available": sorted(k for k, v in values.items() if v)}


__all__ = [
    "CONTROL_SUPPORT",
    "FIELD_CATALOG",
    "build_fact_values",
    "build_plan",
    "plan_field",
]
