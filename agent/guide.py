"""AI 游玩攻略生成。"""

import json
import logging
from typing import Any, Dict

from agent.llm_client import chat_text, is_configured
from agent.prompts import GUIDE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def generate_guide(payload: Dict[str, Any]) -> Dict[str, Any]:
    """根据路线上下文生成攻略文案。"""
    if not is_configured():
        return {
            "success": False,
            "source": "error",
            "message": "AI 攻略暂时不可用",
        }

    user_content = _build_guide_user_payload(payload)
    try:
        text = chat_text(GUIDE_SYSTEM_PROMPT, user_content, temperature=0.7)
    except Exception as e:
        logger.error("攻略生成失败: %s", e, exc_info=True)
        return {
            "success": False,
            "source": "error",
            "message": "AI 攻略暂时不可用",
        }

    if not text or len(text) < 50:
        return {
            "success": False,
            "source": "error",
            "message": "生成内容过短",
        }

    return {
        "success": True,
        "source": "llm",
        "guide_text": text,
    }


def _build_guide_user_payload(payload: Dict[str, Any]) -> str:
    ctx = {
        "city": payload.get("city", ""),
        "poi_type": payload.get("poi_type", "无偏好"),
        "plan_time": payload.get("plan_time", ""),
        "distance_km": payload.get("distance_km"),
        "duration_min": payload.get("duration_min"),
        "weather": payload.get("weather"),
        "pois": payload.get("pois") or [],
    }
    return "请根据以下数据撰写 Citywalk 游玩攻略：\n" + json.dumps(ctx, ensure_ascii=False, indent=2)
