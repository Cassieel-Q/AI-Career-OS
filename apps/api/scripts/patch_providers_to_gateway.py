"""一次性脚本：把各 provider 的环境变量读取替换为统一模型网关调用。

保留每个 provider 自己的 NotConfiguredError 类型，避免破坏既有测试。
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

MODULES = {
    "mission_provider.py": "mission",
    "jd_analysis_provider.py": "mission",
    "job_insight_provider.py": "insight",
    "question_provider.py": "question",
    "interview_provider.py": "interview",
    "claim_provider.py": "claim",
    "gap_provider.py": "other",
    "proof_action_provider.py": "other",
    "role_exploration_provider.py": "other",
    "roadmap_provider.py": "other",
}

BLOCK = re.compile(
    r"(?P<ind>[ \t]*)api_key = os\.getenv\(\"OPENAI_API_KEY\", \"\"\)\.strip\(\)\n"
    r"(?:[ \t]*#[^\n]*\n)*"
    r"[ \t]*if not api_key(?P<cond>[^:\n]*):\n"
    r"[ \t]*raise (?P<err>\w+)\((?P<msg>[^\n]*)\)\n"
    r"[ \t]*base_url = os\.getenv\(\"OPENAI_BASE_URL\"\)\n"
    r"[ \t]*(?P<target>self\.model|model) = [^\n]*\n"
)

IMPORT_LINE = "from .model_config_service import ModelNotConfiguredError, ModelUnusableError, llm_settings, try_llm_settings\n"

DEEPSEEK_HELPER = '''

def _deepseek_enabled(module: str = "{module}") -> bool:
    """当前生效配置是否是 DeepSeek（用户配置或旧环境变量）。"""
    settings = try_llm_settings(module)
    return bool(settings and settings.is_deepseek)
'''


def _replacement(match: re.Match, module: str) -> str:
    ind = match.group("ind")
    err = match.group("err")
    target = match.group("target")
    cond = match.group("cond")
    if "client is None" in cond:
        raise_block = (
            f"{ind}    if client is None:\n"
            f"{ind}        raise {err}(str(_model_exc)) from _model_exc\n"
            f"{ind}    _settings = None\n"
        )
    else:
        raise_block = f"{ind}    raise {err}(str(_model_exc)) from _model_exc\n"
    return (
        f"{ind}try:\n"
        f"{ind}    _settings = llm_settings(\"{module}\")\n"
        f"{ind}except (ModelNotConfiguredError, ModelUnusableError) as _model_exc:\n"
        f"{raise_block}"
        f"{ind}api_key = _settings.api_key if _settings else \"\"\n"
        f"{ind}base_url = _settings.base_url if _settings else None\n"
        f"{ind}{target} = _settings.model if _settings else \"gpt-4o-mini\"\n"
    )


def _add_import(text: str) -> str:
    if "model_config_service" in text:
        return text
    lines = text.splitlines(keepends=True)
    last_import = 0
    for index, line in enumerate(lines[:60]):
        if line.startswith(("import ", "from ")):
            last_import = index
    lines.insert(last_import + 1, IMPORT_LINE)
    return "".join(lines)


def main() -> None:
    for filename, module in MODULES.items():
        path = APP / filename
        text = path.read_text(encoding="utf-8")
        original = text

        def _sub(match: re.Match) -> str:
            return _replacement(match, module)

        text, count = BLOCK.subn(_sub, text)
        if count == 0:
            print(f"[skip] {filename}: 未匹配到环境变量块")
            continue
        text = _add_import(text)

        # 超时：用户配置优先，否则沿用各 provider 原来的环境变量逻辑
        text = text.replace(
            '"timeout": _timeout_seconds()',
            '"timeout": (_settings.timeout if _settings and _settings.source == "user" else _timeout_seconds())',
        )
        text = text.replace(
            "timeout=_timeout_seconds()",
            "timeout=(_settings.timeout if _settings and _settings.source == \"user\" else _timeout_seconds())",
        )

        # 深seek 判定：改为读当前生效配置
        if "_is_deepseek(os.getenv(\"OPENAI_BASE_URL\"))" in text:
            text = text.replace(
                "_is_deepseek(os.getenv(\"OPENAI_BASE_URL\"))",
                "_deepseek_enabled()",
            )
            # 在第一个 def/class 之前插入 helper
            match = re.search(r"^(def |class )", text, flags=re.MULTILINE)
            if match:
                text = text[: match.start()] + DEEPSEEK_HELPER.format(module=module).lstrip("\n") + "\n\n" + text[match.start():]

        path.write_text(text, encoding="utf-8")
        print(f"[ok] {filename}: {count} 处接入 {module} 模块（{len(original)} → {len(text)} 字符）")


if __name__ == "__main__":
    main()
