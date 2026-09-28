"""DeepSeek smoke: one parse_jd or what_matters call with synthetic JD.
Never prints secrets. Exit 0=PASS, 2=SKIP no key, 1=FAIL.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else r"G:\myself\ai-career-OS-v0.2-full-intelligence")
API = REPO / "apps" / "api"
sys.path.insert(0, str(API))

SYN_JD = """公司：百度
职位：AI产品经理
职责：负责文心大模型相关产品的需求分析、评测体系建设与跨部门协作。
要求：熟悉RAG/Agent；有ToB或平台产品经验；能设计指标体系。
"""


def load_user_env_windows():
    """Load User-scope env into process without printing values."""
    if sys.platform != "win32":
        return
    try:
        import winreg
    except ImportError:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    except OSError:
        return
    i = 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
        except OSError:
            break
        if name and name not in os.environ:
            os.environ[name] = value
        i += 1


def main() -> int:
    load_user_env_windows()
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("DEEPSEEK_SMOKE: SKIP (no OPENAI_API_KEY/DEEPSEEK_API_KEY in User env)")
        return 2

    # Never print key
    print("DEEPSEEK_SMOKE: key_present=yes")

    # Try project helpers in preference order
    errors = []
    for mod_name, fn_name in [
        ("app.jd_parser", "parse_jd"),
        ("app.services.jd_parser", "parse_jd"),
        ("app.mission_provider", "parse_jd"),
        ("app.mission_provider", "what_matters"),
        ("app.providers.mission_provider", "what_matters"),
        ("app.what_matters", "what_matters"),
    ]:
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name)
        except Exception as e:
            errors.append(f"import {mod_name}.{fn_name}: {type(e).__name__}")
            continue
        try:
            result = fn(SYN_JD)
            # Don't dump full LLM payload; just category
            ok = result is not None
            print(f"DEEPSEEK_SMOKE: PASS via {mod_name}.{fn_name} result_type={type(result).__name__} ok={ok}")
            return 0 if ok else 1
        except Exception as e:
            errors.append(f"call {mod_name}.{fn_name}: {type(e).__name__}: {e}")
            continue

    # Fallback: raw OpenAI-compatible chat if base URL configured
    try:
        import urllib.request
        import json

        base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        url = base.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {
                "model": os.environ.get("OPENAI_MODEL") or "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "Extract company and role from JD as JSON keys company,role. No secrets."},
                    {"role": "user", "content": SYN_JD},
                ],
                "temperature": 0,
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        if "百度" in content or "Baidu" in content or "AI" in content:
            print("DEEPSEEK_SMOKE: PASS via raw chat.completions")
            return 0
        print("DEEPSEEK_SMOKE: FAIL unexpected content category")
        return 1
    except Exception as e:
        errors.append(f"raw chat: {type(e).__name__}: {e}")

    print("DEEPSEEK_SMOKE: FAIL")
    for e in errors[-6:]:
        print(" ", e)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
