"""DeepSeek（OpenAI 兼容）客户端。"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _api_key() -> Optional[str]:
    return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")


def _base_url() -> str:
    return os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get(
        "LLM_BASE_URL", "https://api.deepseek.com"
    )


def _model() -> str:
    return os.environ.get("DEEPSEEK_MODEL") or os.environ.get("LLM_MODEL", "deepseek-chat")


def is_configured() -> bool:
    return bool(_api_key())


def chat_json(system: str, user: str, temperature: float = 0.3) -> dict:
    """调用 LLM 并解析为 JSON 对象。"""
    if not is_configured():
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY 或 LLM_API_KEY，请在环境变量或 .env 中设置"
        )

    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("请安装 openai：pip install openai") from e

    client = OpenAI(api_key=_api_key(), base_url=_base_url())
    resp = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = (resp.choices[0].message.content or "").strip()
    return _parse_json_content(content)


def _parse_json_content(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            return json.loads(match.group(0))
        logger.warning("LLM 返回非 JSON: %s", content[:200])
        raise ValueError("智能体返回格式无效，请重试")


def chat_text(system: str, user: str, temperature: float = 0.65) -> str:
    """调用 LLM 返回纯文本。"""
    if not is_configured():
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY 或 LLM_API_KEY，请在环境变量或 .env 中设置"
        )

    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("请安装 openai：pip install openai") from e

    client = OpenAI(api_key=_api_key(), base_url=_base_url())
    resp = client.chat.completions.create(
        model=_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()
