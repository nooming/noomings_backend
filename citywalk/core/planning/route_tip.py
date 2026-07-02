# -*- coding: utf-8 -*-
"""路线说明 route_tip 用户向文案。"""
import re
from typing import List

_COORD_ADDRESS_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")


def _destination_label_for_tip(address: str) -> str:
    """路线说明用：坐标串不展示给用户。"""
    addr = (address or "").strip()
    if not addr or _COORD_ADDRESS_RE.match(addr):
        return ""
    return addr


def build_user_route_tip(
        *,
        mode: str,
        poi_count: int,
        end_address: str = "",
        start_address: str = "",
        detour_mode: bool = False,
        route_style: str = "balanced",
        route_waypoints_truncated: bool = False,
        degraded_route: bool = False,
        stay_hint: str = "",
        optional_poi_count: int = 0,
        plan_time_min: int = 0,
        activity_total_min: int = 0,
        free_time_min: int = 0) -> str:
    """生成面向用户的路线说明，不含算法/性能内部表述。"""
    parts: List[str] = []

    if mode == "loop":
        center = _destination_label_for_tip(start_address)
        if center:
            parts.append(f"探索模式：以「{center}」为中心环形漫步；")
        else:
            parts.append("探索模式：以地图中心为起点环形漫步；")
        if poi_count > 0:
            parts.append(f"编号 1–{poi_count} 为沿途打卡，最后回到中心附近。")
    elif poi_count > 0:
        dest = _destination_label_for_tip(end_address)
        if dest:
            parts.append(f"地图「终」为「{dest}」；")
        else:
            parts.append("地图「终」为目的地；")
        parts.append(f"编号 1–{poi_count} 为沿途打卡，请按顺序前往并在终点结束。")

    if detour_mode:
        if route_style == "atmosphere_first":
            parts.append("已按「氛围优先」串联沿途，尽量避免绕远。")
        elif route_style == "efficiency_first":
            parts.append("已按「省力直达」优化顺序。")
        else:
            parts.append("已均衡串联沿途打卡。")

    if stay_hint:
        parts.append(stay_hint.strip())

    if free_time_min >= 15 and plan_time_min > 0 and activity_total_min > 0:
        parts.append(
            f"预计 {int(activity_total_min)} 分钟为步行与打卡，"
            f"约 {int(free_time_min)} 分钟为途中自由安排，与计划 {int(plan_time_min)} 分钟一致。"
        )

    if optional_poi_count > 0:
        parts.append(f"其中 {optional_poi_count} 处标为「可选」，可按体力跳过。")

    if route_waypoints_truncated:
        parts.append("打卡点较多，地图上步行线展示其中一段；完整顺序见下方列表。")

    if degraded_route:
        parts.append("当前为起终点示意路线；打卡顺序请参考下方列表，稍后可重新规划。")

    return " ".join(p for p in parts if p).strip()
