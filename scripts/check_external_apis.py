#!/usr/bin/env python3
"""一次性探测 DeepSeek / Bocha / 高德 Web 服务（从 .env 读 Key，不打印密钥）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def mask(s: str | None) -> str:
    if not s:
        return "(empty)"
    s = str(s).strip()
    if len(s) <= 8:
        return "***"
    return s[:4] + "…" + s[-4:]


def check_deepseek() -> tuple[bool, str]:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")
    base = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"
    if not key:
        return False, "DEEPSEEK_API_KEY 未设置"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=base)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "回复 OK"}],
            max_tokens=8,
        )
        text = (resp.choices[0].message.content or "").strip()
        safe = text.encode("ascii", "replace").decode("ascii")
        return True, f"model {model} reply: {safe[:60]!r}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_bocha() -> tuple[bool, str]:
    key = os.environ.get("BOCHA_API_KEY")
    if not key:
        return False, "BOCHA_API_KEY 未设置（灵感 web_search 会降级 LLM）"
    try:
        r = requests.post(
            "https://api.bochaai.com/v1/web-search",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"query": "上海 静安寺 咖啡", "count": 2, "summary": True},
            timeout=20,
        )
        if not r.ok:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        # 粗判是否有结果结构
        snippet = json.dumps(data, ensure_ascii=False)[:120]
        return True, f"HTTP 200，响应片段: {snippet}…"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_amap_web() -> tuple[bool, str]:
    key = os.environ.get("AMAP_KEY", "").strip()
    if not key:
        return False, "AMAP_KEY 未设置"
    try:
        r = requests.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": key, "address": "上海市静安区静安寺", "city": "上海"},
            timeout=15,
        )
        data = r.json()
        status = data.get("status")
        info = data.get("info") or data.get("infocode")
        if str(status) != "1":
            return False, f"status={status} info={info}"
        geos = data.get("geocodes") or []
        loc = geos[0].get("location") if geos else None
        return True, f"地理编码 OK location={loc}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_amap_js_config() -> tuple[bool, str]:
    js = os.environ.get("AMAP_JS_KEY", "").strip()
    sec = os.environ.get("AMAP_JS_SECURITY_CODE", "").strip()
    if not js or not sec:
        return False, "AMAP_JS_KEY 或 AMAP_JS_SECURITY_CODE 缺失（前端地图靠 /config/public）"
    return True, f"JS Key {mask(js)} + 安全码已配置（须在浏览器验证白名单）"


def main() -> int:
    print("=== 环境 Key 摘要（脱敏）===")
    print(f"DEEPSEEK_API_KEY: {mask(os.environ.get('DEEPSEEK_API_KEY'))}")
    print(f"BOCHA_API_KEY: {mask(os.environ.get('BOCHA_API_KEY'))}")
    print(f"AMAP_KEY: {mask(os.environ.get('AMAP_KEY'))}")
    print(f"CW_INSPIRATION_PROVIDER: {os.environ.get('CW_INSPIRATION_PROVIDER', '(default llm)')}")
    print()

    checks = [
        ("DeepSeek", check_deepseek),
        ("博查 Bocha", check_bocha),
        ("高德 Web 地理编码", check_amap_web),
        ("高德 JS 配置项", check_amap_js_config),
    ]
    failed = 0
    for name, fn in checks:
        ok, msg = fn()
        tag = "OK" if ok else "FAIL"
        print(f"[{tag}] {name}: {msg}")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
