# -*- coding: utf-8 -*-
import math

from .geometry import point_in_polygon, segment_intersects_polygon

NAV_GRID_STEP = 1.2
NAV_GRID_STEP_MAX = 1.8


def nav_grid_idx(i, j, nx):
    return j * nx + i


def recommend_nav_step(lot_w, lot_h, obstacle_count):
    area = max(1, float(lot_w) * float(lot_h))
    obs_factor = max(0, float(obstacle_count or 0))
    dense_penalty = min(0.5, obs_factor * 0.04)
    area_penalty = min(0.4, max(0, area - 12000) / 30000)
    return max(NAV_GRID_STEP, min(NAV_GRID_STEP_MAX, NAV_GRID_STEP + dense_penalty + area_penalty))


def point_inside_any_obstacle(p, obstacles):
    for obs in obstacles:
        if point_in_polygon(p, obs, True):
            return True
    return False


def segment_clear_boxes(p1, p2, boxes):
    for box in boxes:
        if segment_intersects_polygon(p1, p2, box):
            return False
    return True


def build_navigation_grid(obstacles, lot_w, lot_h, step=NAV_GRID_STEP, x_min=0.0, y_min=0.0):
    nx = max(2, int(lot_w / step) + 1)
    ny = max(2, int(lot_h / step) + 1)
    valid = bytearray(nx * ny)
    points = [None] * (nx * ny)
    x_max = x_min + lot_w
    y_max = y_min + lot_h
    for j in range(ny):
        for i in range(nx):
            idx = nav_grid_idx(i, j, nx)
            x = min(x_max, x_min + i * step)
            y = min(y_max, y_min + j * step)
            points[idx] = [x, y]
            valid[idx] = 0 if point_inside_any_obstacle([x, y], obstacles) else 1
    adj = [[] for _ in range(nx * ny)]
    dirs = [
        [1, 0],
        [-1, 0],
        [0, 1],
        [0, -1],
        [1, 1],
        [1, -1],
        [-1, 1],
        [-1, -1],
    ]
    for j in range(ny):
        for i in range(nx):
            idx = nav_grid_idx(i, j, nx)
            if not valid[idx]:
                continue
            p = points[idx]
            for d in dirs:
                ni = i + d[0]
                nj = j + d[1]
                if ni < 0 or nj < 0 or ni >= nx or nj >= ny:
                    continue
                nidx = nav_grid_idx(ni, nj, nx)
                if not valid[nidx]:
                    continue
                q = points[nidx]
                if not segment_clear_boxes(p, q, obstacles):
                    continue
                adj[idx].append([nidx, math.hypot(q[0] - p[0], q[1] - p[1])])
    return {
        "nx": nx,
        "ny": ny,
        "step": step,
        "xMin": x_min,
        "yMin": y_min,
        "lotW": lot_w,
        "lotH": lot_h,
        "valid": valid,
        "points": points,
        "adj": adj,
        "nodeCount": nx * ny,
    }


def nearest_visible_grid_nodes(point, nav, obstacles, max_nodes=6, max_px=6):
    if point_inside_any_obstacle(point, obstacles):
        return []
    px, py = point
    x_min = nav.get("xMin", 0.0)
    y_min = nav.get("yMin", 0.0)
    ci = max(0, min(nav["nx"] - 1, round((px - x_min) / nav["step"])))
    cj = max(0, min(nav["ny"] - 1, round((py - y_min) / nav["step"])))
    cands = []
    for r in range(max_px + 1):
        i0 = max(0, ci - r)
        i1 = min(nav["nx"] - 1, ci + r)
        j0 = max(0, cj - r)
        j1 = min(nav["ny"] - 1, cj + r)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                if r > 0 and i > i0 and i < i1 and j > j0 and j < j1:
                    continue
                idx = nav_grid_idx(i, j, nav["nx"])
                if not nav["valid"][idx]:
                    continue
                q = nav["points"][idx]
                if not segment_clear_boxes(point, q, obstacles):
                    continue
                cands.append([idx, math.hypot(q[0] - px, q[1] - py)])
        if len(cands) >= max_nodes:
            break
    if not cands:
        for idx in range(nav["nodeCount"]):
            if not nav["valid"][idx]:
                continue
            q = nav["points"][idx]
            if not segment_clear_boxes(point, q, obstacles):
                continue
            cands.append([idx, math.hypot(q[0] - px, q[1] - py)])
    cands.sort(key=lambda a: a[1])
    return cands[:max_nodes]
