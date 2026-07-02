# -*- coding: utf-8 -*-
"""规划常量、POI 权重与路线风格配置。"""
import os

from citywalk.core.geo.geo_utils import MAX_CITYWALK_SPAN_M  # noqa: F401  # 起终点最大直线跨度（米），单源在 geo_utils
ROUTE_SAMPLE_INTERVAL = 500  # 每500米在最短路线上取1个采样点
MAX_SAMPLE_POINTS = 12  # 最多12个采样点（提升大城市长路线覆盖）
POI_SEARCH_RADIUS = 1000  # 每个采样点搜索周边1000米（提升召回）
POI_PER_SAMPLE = 5  # 每个采样点取5个POI（提升可用候选）
# 种草/灵感点离最短主线的最大直线距离（米）：超过则丢弃，避免离群点把路线撑到几十公里。
# 正常沿途采样点都在 POI_SEARCH_RADIUS(1000m) 内，故给灵感点留约 3 倍裕度。
MAX_SEED_DIST_TO_ROUTE_M = 3000
# 种草点地理编码结果距路线参考点的最大直线距离（米），超过则视为异地误匹配
MAX_SEED_GEO_BIAS_M = 50000
# 注意：选定POI后会重新规划路线经过这些POI，所以不需要严格的距离限制
DEBUG_PLAN_LOG = os.environ.get("CITYWALK_DEBUG_PLAN", "false").lower() == "true"

# POI类型图标映射
POI_TYPE_ICONS = {
    "咖啡": "☕",
    "咖啡馆": "☕",
    "咖啡店": "☕",
    "咖啡屋": "☕",
    "甜品": "🍰",
    "甜品店": "🍰",
    "奶茶": "🧋",
    "奶茶店": "🧋",
    "饮品店": "🥤",
    "面包": "🥐",
    "面包店": "🥐",
    "烘焙": "🥐",
    "蛋糕": "🎂",
    "蛋糕店": "🎂",
    "花店": "💐",
    "花艺": "💐",
    "鲜花": "💐",
    "公园": "🌳",
    "景区": "🏞️",
    "绿地": "🌿",
    "博物馆": "🏛️",
    "纪念馆": "🏛️",
    "美术馆": "🎨",
    "艺术": "🎨",
    "展览": "🖼️",
    "文创": "✨",
    "创意": "✨",
    "商场": "🛍️",
    "购物": "🛍️",
    "书店": "📚",
    "图书": "📚",
    "餐厅": "🍽️",
    "餐饮": "🍴",
    "酒吧": "🍸",
    "历史": "🏯",
    "古迹": "🏯",
    "故居": "🏠",
}

# 核心：无效/低价值POI过滤规则（分维度）
# 1. 完全排除的POI类型（关键词匹配）
EXCLUDE_POI_TYPES = [
    # 住宅类
    "住宅", "小区", "公寓", "别墅", "商住楼", "保障房", "安置房",
    # 工业/仓储类
    "工厂", "仓库", "物流园", "产业园", "工业园", "加工", "制造",
    # 汽修/加油类
    "加油站", "汽修", "汽配", "洗车", "轮胎", "保养",
    # 医疗/康养类（非景点）
    "医院", "诊所", "药店", "养老院", "康复中心", "体检中心",
    # 生活服务（低价值）
    "家政", "保洁", "搬家", "快递", "干洗", "理发", "美容", "足疗", "按摩", "SPA", "便利店",
    # 金融/政务类
    "银行", "ATM", "营业厅", "邮局", "派出所", "政务中心", "税务局",
    # 其他低价值
    "彩票", "烟酒行", "充电站", "收费站", "停车场", "施工", "围挡","厕所","公共厕所"
]

# 2. 低匹配度POI关键词（即使命中目标类型，也排除）
LOW_VALUE_KEYWORDS = [
    "办公", "写字楼", "招商", "出租", "售房", "中介", "装修", "建材",
    "批发", "仓储", "配送", "后厨", "员工通道", "内部", "临时"
]

# 打卡偏好关键词权重（筛选 + 氛围评分共用，避免双表漂移）
POI_PROFILE_WEIGHTS = {
    "无偏好": {"咖啡馆": 6, "甜品店": 6, "花店": 6, "公园": 6, "商场": 5, "面包店": 5},
    "自然": {"公园": 10, "景区": 10, "绿地": 8, "湿地公园": 9, "森林公园": 9},
    "历史": {"纪念馆": 10, "博物馆": 10, "历史古迹": 10, "名人故居": 9, "文博馆": 8},
    "文创": {"美术馆": 10, "创意园区": 10, "艺术中心": 8, "文创空间": 8, "展览馆": 8},
    "花店": {"花店": 10, "花艺店": 9, "鲜花店": 9, "花艺馆": 8},
    "咖啡甜品": {
        "咖啡馆": 10, "咖啡屋": 9, "咖啡店": 9, "咖啡体验馆": 8,
        "甜品店": 10, "奶茶店": 9, "糖水铺": 8, "饮品店": 7,
        "面包店": 10, "烘焙店": 9, "蛋糕店": 9, "西点店": 8,
    },
    "商场": {"商场": 10, "购物中心": 9, "购物广场": 8, "商业中心": 7},
}

# 兼容旧引用
VALID_POI_WEIGHT = POI_PROFILE_WEIGHTS
AMBIENCE_PROFILE_WEIGHTS = POI_PROFILE_WEIGHTS

POI_TYPE_ALIASES = {
    "咖啡": "咖啡甜品",
    "甜品": "咖啡甜品",
    "烘焙": "咖啡甜品",
}


def normalize_poi_type(poi_type: str) -> str:
    """统一打卡偏好枚举（含 Agent/旧版别名）。"""
    t = (poi_type or "无偏好").strip()
    return POI_TYPE_ALIASES.get(t, t)

# 停留节奏：打卡高密度 vs 深度逛（默认 checkin）
MAX_POI_COUNT_CAP_CHECKIN = 15
MAX_POI_COUNT_CAP_RELAXED = 12
POI_PER_KM_CHECKIN = 1.0
OPTIONAL_SCORE_PERCENTILE = 0.5
MIN_REQUIRED_NON_OPTIONAL_POIS = 3
# 末站允许距地理终点的最大直线距离（米）；checkin 下另见 poi_selection 按路长动态放宽
END_TAIL_MAX_DIST_M_CHECKIN = 1500

VISIT_PACE_CONFIG = {
    "checkin": {
        "stay_estimate_m": 3,
        "stay_cap_m": 10,
        "stay_cap_history_m": 12,
        "min_spacing_m": 110,
        "max_poi_cap": MAX_POI_COUNT_CAP_CHECKIN,
        "pois_per_km": POI_PER_KM_CHECKIN,
        "use_max_buckets": True,
        "fill_until_max": True,
        "segment_min_candidates_for_two": 2,
    },
    "relaxed": {
        "stay_estimate_m": 5,
        "stay_cap_m": 25,
        "stay_cap_history_m": 30,
        "min_spacing_m": None,
        "max_poi_cap": MAX_POI_COUNT_CAP_RELAXED,
        "pois_per_km": 0.0,
        "use_max_buckets": False,
        "fill_until_max": False,
        "segment_min_candidates_for_two": 3,
    },
}


def normalize_visit_pace(visit_pace: str = "") -> str:
    p = (visit_pace or "checkin").strip().lower()
    if p in VISIT_PACE_CONFIG:
        return p
    return "checkin"


# 路线风格权重：语义与绕路的平衡配置
ROUTE_STYLE_CONFIG = {
    "balanced": {
        "semantic_weight": 1.0,
        "detour_weight": 0.45,
        "max_detour_cost": 20.0,  # 距离惩罚上限，避免远点吞噬分数
        "min_spacing_m": 180,  # 全局筛选时相邻POI最小间距
        "backtrack_slack_m": 200,  # 沿最短路 progress 允许回退（米）
        "toward_end_slack_m": 80,  # 相对已选最近终点距离允许略变远（米）
    },
    "atmosphere_first": {
        "semantic_weight": 1.2,
        "detour_weight": 0.25,
        "max_detour_cost": 26.0,
        "min_spacing_m": 140,
        "min_spacing_detour_m": 110,
        "backtrack_slack_m": 250,
        "backtrack_slack_detour_m": 320,
        "toward_end_slack_m": 120,
    },
    "efficiency_first": {
        "semantic_weight": 0.8,
        "detour_weight": 0.7,
        "max_detour_cost": 14.0,
        "min_spacing_m": 220,
        "backtrack_slack_m": 120,
        "toward_end_slack_m": 50,
    }
}

