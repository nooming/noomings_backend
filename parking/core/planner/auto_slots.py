# -*- coding: utf-8 -*-
"""沿道路泊位带均匀生成车位（含生成阶段碰撞避让）。"""

import math

SLOT_W = 5.3
SLOT_H = 2.6
BUILDING_W = 18.0
BUILDING_H = 12.0
DEFAULT_ROAD_W = 6.0
OVERLAP_EPS = 0.2


def _road_segments(centerline, closed=True):
    pts = centerline or []
    if len(pts) < 2:
        return []
    segs = []
    n = len(pts)
    limit = n if closed else n - 1
    for i in range(limit):
        j = (i + 1) % n
        if not closed and j == 0:
            break
        segs.append((pts[i], pts[j]))
    return segs


def _strip_defs(road, slot_w=SLOT_W, slot_h=SLOT_H, road_w=DEFAULT_ROAD_W):
    centerline = (road or {}).get("centerline") or []
    closed = (road or {}).get("closed", True) is not False
    half_rw = float((road or {}).get("width") or road_w) / 2.0
    offset = half_rw + slot_h / 2.0 + 0.35
    strips = []
    for i, (a, b) in enumerate(_road_segments(centerline, closed)):
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = -dy / length, dx / length
        theta = math.atan2(dy, dx)
        strips.append(
            {
                "id": f"strip-{i}",
                "a": [ax, ay],
                "b": [bx, by],
                "length": length,
                "theta": theta,
                "left_offset": [nx * offset, ny * offset],
                "right_offset": [-nx * offset, -ny * offset],
                "slot_w": slot_w,
            }
        )
    return strips


def _slot_polygon(cx, cy, theta):
    ct = math.cos(theta)
    st = math.sin(theta)
    half_l = SLOT_W / 2
    half_w = SLOT_H / 2
    local = [
        (-half_l, -half_w),
        (half_l, -half_w),
        (half_l, half_w),
        (-half_l, half_w),
    ]
    return [[cx + lx * ct - ly * st, cy + lx * st + ly * ct] for lx, ly in local]


def _point_in_polygon(px, py, poly, include_boundary=True):
    if not poly or len(poly) < 3:
        return False
    if include_boundary:
        for i in range(len(poly)):
            a = poly[i]
            b = poly[(i + 1) % len(poly)]
            ax, ay = float(a[0]), float(a[1])
            bx, by = float(b[0]), float(b[1])
            cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            if abs(cross) <= 1e-6:
                dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
                if dot <= 1e-6:
                    return True
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if (yi > py) != (yj > py):
            xinters = (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
            if px < xinters:
                inside = not inside
        j = i
    return inside


def _polygons_overlap(poly_a, poly_b):
    for poly in (poly_a, poly_b):
        for p in poly:
            if _point_in_polygon(p[0], p[1], poly_a if poly is poly_b else poly_b, True):
                return True
    for i in range(len(poly_a)):
        a1, a2 = poly_a[i], poly_a[(i + 1) % len(poly_a)]
        for j in range(len(poly_b)):
            b1, b2 = poly_b[j], poly_b[(j + 1) % len(poly_b)]
            if _segments_intersect(a1, a2, b1, b2):
                return True
    return False


def _segments_intersect(a, b, c, d, eps=1e-6):
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = cross(a, b, c)
    o2 = cross(a, b, d)
    o3 = cross(c, d, a)
    o4 = cross(c, d, b)
    if (o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps):
        if (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps):
            return True
    if abs(o1) <= eps and _point_on_segment(c, a, b, eps):
        return True
    if abs(o2) <= eps and _point_on_segment(d, a, b, eps):
        return True
    if abs(o3) <= eps and _point_on_segment(a, c, d, eps):
        return True
    if abs(o4) <= eps and _point_on_segment(b, c, d, eps):
        return True
    return False


def _point_on_segment(p, a, b, eps=1e-6):
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > eps:
        return False
    dot = (p[0] - a[0]) * (p[0] - b[0]) + (p[1] - a[1]) * (p[1] - b[1])
    return dot <= eps


def _dist_point_to_seg(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    qx = x1 + t * dx
    qy = y1 + t * dy
    return math.hypot(px - qx, py - qy)


def _inner_boundary_segments(scenario):
    road = scenario.get("road") or {}
    inner = scenario.get("inner") or {}
    centerline = road.get("centerline") or []
    closed = road.get("closed", True) is not False
    road_w = float(road.get("width") or DEFAULT_ROAD_W)
    if centerline and len(centerline) >= 2:
        segs = _road_segments(centerline, closed)
        half = road_w / 2.0
        out = []
        for a, b in segs:
            ax, ay = float(a[0]), float(a[1])
            bx, by = float(b[0]), float(b[1])
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            nx, ny = -dy / length, dx / length
            out.append([ax + nx * half, ay + ny * half, bx + nx * half, by + ny * half])
            out.append([ax - nx * half, ay - ny * half, bx - nx * half, by - ny * half])
        return out
    ix0 = float(inner.get("x_min", 0))
    ix1 = float(inner.get("x_max", 0))
    iy0 = float(inner.get("y_min", 0))
    iy1 = float(inner.get("y_max", 0))
    if ix1 <= ix0 or iy1 <= iy0:
        return []
    return [
        [ix0, iy0, ix1, iy0],
        [ix1, iy0, ix1, iy1],
        [ix1, iy1, ix0, iy1],
        [ix0, iy1, ix0, iy0],
    ]


def _polygon_overlaps_inner_road(poly, scenario, clearance=1.05):
    road = scenario.get("road") or {}
    eff = max(clearance, float(road.get("width") or DEFAULT_ROAD_W) / 2.0)
    for seg in _inner_boundary_segments(scenario):
        x1, y1, x2, y2 = seg
        for p in poly:
            if _dist_point_to_seg(p[0], p[1], x1, y1, x2, y2) <= eff:
                return True
    return False


def _building_rect(cx, cy):
    return {
        "xmin": cx - BUILDING_W / 2,
        "ymin": cy - BUILDING_H / 2,
        "w": BUILDING_W,
        "h": BUILDING_H,
    }


def _rect_to_polygon(rect):
    x0, y0 = rect["xmin"], rect["ymin"]
    w, h = rect["w"], rect["h"]
    return [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]


def _can_place_slot(scenario, cx, cy, theta, ignore_index=-1):
    slot_poly = _slot_polygon(cx, cy, theta)
    road = scenario.get("road") or {}
    clearance = float(road.get("width") or DEFAULT_ROAD_W) / 2.0 - 0.05
    if _polygon_overlaps_inner_road(slot_poly, scenario, clearance):
        return False
    for obs in scenario.get("obstacles") or []:
        pts = (obs or {}).get("points") or []
        if len(pts) >= 3 and _polygons_overlap(slot_poly, pts):
            return False
    for bx, by in scenario.get("buildings") or []:
        if _polygons_overlap(slot_poly, _rect_to_polygon(_building_rect(float(bx), float(by)))):
            return False
    for i, slot in enumerate(scenario.get("slots") or []):
        if i == ignore_index:
            continue
        if len(slot) < 2:
            continue
        sx, sy = float(slot[0]), float(slot[1])
        st = float(slot[2]) if len(slot) > 2 else 0.0
        if _polygons_overlap(slot_poly, _slot_polygon(sx, sy, st)):
            return False
    for ent in scenario.get("entrances") or []:
        if len(ent) >= 2 and _point_in_polygon(float(ent[0]), float(ent[1]), slot_poly, True):
            return False
    return True


def _try_place_on_strip(scenario, strip, t, ox, oy, theta, placed_slots):
    ax, ay = strip["a"]
    bx, by = strip["b"]
    cx = ax + (bx - ax) * t + ox
    cy = ay + (by - ay) * t + oy
    scenario["slots"] = placed_slots
    if _can_place_slot(scenario, cx, cy, theta, -1):
        return [round(cx, 2), round(cy, 2), round(theta, 4)]
    pitch = SLOT_W + 0.4
    length = strip["length"]
    step = pitch / max(1e-9, length)
    for delta in (step, -step, 2 * step, -2 * step, 3 * step, -3 * step):
        t2 = max(0.08, min(0.92, t + delta))
        cx2 = ax + (bx - ax) * t2 + ox
        cy2 = ay + (by - ay) * t2 + oy
        if _can_place_slot(scenario, cx2, cy2, theta, -1):
            return [round(cx2, 2), round(cy2, 2), round(theta, 4)]
    return None


def suggest_slots(scenario, count=None):
    road = scenario.get("road") or {}
    strips = _strip_defs(road)
    if not strips:
        n = count or max(1, int(scenario.get("n_veh") or 12))
        return [], {"requested": n, "placed": 0, "skipped": n}
    n = count or max(1, int(scenario.get("n_veh") or 12))
    per = max(1, math.ceil(n / len(strips)))
    placed_slots = []
    skipped = 0
    work = dict(scenario)
    work["slots"] = []

    for strip in strips:
        length = strip["length"]
        slot_w = strip["slot_w"]
        fit = max(1, int(length // (slot_w + 0.4)))
        use = min(per, fit)
        for off_key, theta_add in (("left_offset", 0.0), ("right_offset", math.pi)):
            ox, oy = strip[off_key]
            theta = strip["theta"] + theta_add
            for k in range(use):
                if len(placed_slots) >= n:
                    meta = {
                        "requested": n,
                        "placed": len(placed_slots),
                        "skipped": skipped + max(0, n - len(placed_slots)),
                    }
                    return placed_slots[:n], meta
                t = (k + 0.5) / use
                slot = _try_place_on_strip(work, strip, t, ox, oy, theta, placed_slots)
                if slot:
                    placed_slots.append(slot)
                else:
                    skipped += 1

    meta = {"requested": n, "placed": len(placed_slots), "skipped": skipped + max(0, n - len(placed_slots))}
    return placed_slots[:n], meta


def suggest_plans(scenario, optimize_fn):
    """返回三套候选方案说明 + 场景副本。"""
    base = dict(scenario)
    plans = []

    min_time = dict(base)
    r1 = optimize_fn(min_time, "exact")
    plans.append(
        {
            "id": "min_total_time",
            "title": "最小总时间",
            "description": "在当前布局下匈牙利全局最优分配",
            "scenario": r1.get("scenario") or min_time,
            "result": r1,
            "metrics": None,
        }
    )

    fair = dict(base)
    slots = list(fair.get("slots") or [])
    if slots:
        mid_y = sum(s[1] for s in slots) / len(slots)
        for s in slots:
            if s[1] < mid_y and len(s) > 2:
                s[2] = 0
            elif len(s) > 2:
                s[2] = 3.14159
        fair["slots"] = slots
    r2 = optimize_fn(fair, "exact")
    plans.append(
        {
            "id": "balanced_walk",
            "title": "均衡步行",
            "description": "调整车位朝向以平衡南北侧步行距离",
            "scenario": r2.get("scenario") or fair,
            "result": r2,
        }
    )

    expanded = dict(base)
    auto, _meta = suggest_slots(
        expanded, count=max(len(expanded.get("slots") or []), int(expanded.get("n_veh") or 12) + 2)
    )
    if auto:
        expanded["slots"] = auto
        expanded["slot_types"] = ["normal"] * len(auto)
    r3 = optimize_fn(expanded, "exact")
    plans.append(
        {
            "id": "max_utilization",
            "title": "提高利用率",
            "description": "沿道路自动补全车位后重新优化",
            "scenario": r3.get("scenario") or expanded,
            "result": r3,
        }
    )
    return plans
