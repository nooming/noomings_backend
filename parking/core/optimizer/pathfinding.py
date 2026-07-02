# -*- coding: utf-8 -*-
import math

from .nav_grid import (
    build_navigation_grid,
    recommend_nav_step,
    nearest_visible_grid_nodes,
    segment_clear_boxes,
)

BUILDING_FOOTPRINT_W = 18.0
BUILDING_FOOTPRINT_H = 12.0
UNREACHABLE_WALK_DIST = 1e6


def building_axis_box(cx, cy):
    hw = BUILDING_FOOTPRINT_W / 2
    hh = BUILDING_FOOTPRINT_H / 2
    return [
        [cx - hw, cy - hh],
        [cx + hw, cy - hh],
        [cx + hw, cy + hh],
        [cx - hw, cy + hh],
    ]


def walk_blocking_boxes(obstacles, buildings_pos, dest_bi):
    boxes = []
    for o in (obstacles or []):
        if isinstance(o.get("points"), list):
            pts = [[float(p[0]), float(p[1])] for p in o["points"]]
            if len(pts) >= 3:
                boxes.append(pts)
    for i, pos in enumerate(buildings_pos):
        if i == dest_bi:
            continue
        boxes.append(building_axis_box(pos[0], pos[1]))
    return boxes


def polyline_length(pts):
    d = 0.0
    for i in range(1, len(pts)):
        d += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    return d


def polyline_segments_clear(pts, boxes):
    for i in range(1, len(pts)):
        if not segment_clear_boxes(pts[i - 1], pts[i], boxes):
            return False
    return True


def simplify_colinear_polyline(pts):
    if len(pts) <= 2:
        return pts[:]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a = out[-1]
        b = pts[i]
        c = pts[i + 1]
        v1x = b[0] - a[0]
        v1y = b[1] - a[1]
        v2x = c[0] - b[0]
        v2y = c[1] - b[1]
        cross = v1x * v2y - v1y * v2x
        if abs(cross) > 1e-5:
            out.append(b)
    out.append(pts[-1])
    return out


def min_heap_push(heap, item):
    heap.append(item)
    i = len(heap) - 1
    while i > 0:
        p = (i - 1) // 2
        if heap[p][0] <= heap[i][0]:
            break
        heap[p], heap[i] = heap[i], heap[p]
        i = p


def min_heap_pop(heap):
    if not heap:
        return None
    top = heap[0]
    tail = heap.pop()
    if heap:
        heap[0] = tail
        i = 0
        while True:
            l = i * 2 + 1
            r = l + 1
            m = i
            if l < len(heap) and heap[l][0] < heap[m][0]:
                m = l
            if r < len(heap) and heap[r][0] < heap[m][0]:
                m = r
            if m == i:
                break
            heap[m], heap[i] = heap[i], heap[m]
            i = m
    return top


def a_star_between_nodes(start_idx, goal_idx, grid):
    if start_idx == goal_idx:
        return [0.0, [start_idx]]
    n = grid["nodeCount"]
    g = [float("inf")] * n
    f = [float("inf")] * n
    parent = [-1] * n
    closed = bytearray(n)
    goal_pt = grid["points"][goal_idx]
    g[start_idx] = 0.0
    f[start_idx] = math.hypot(
        grid["points"][start_idx][0] - goal_pt[0],
        grid["points"][start_idx][1] - goal_pt[1],
    )
    heap = []
    min_heap_push(heap, [f[start_idx], start_idx])
    while heap:
        cur = min_heap_pop(heap)
        u = cur[1]
        if closed[u]:
            continue
        closed[u] = 1
        if u == goal_idx:
            break
        for v, w in grid["adj"][u]:
            if closed[v]:
                continue
            ng = g[u] + w
            if ng >= g[v]:
                continue
            g[v] = ng
            parent[v] = u
            f[v] = ng + math.hypot(grid["points"][v][0] - goal_pt[0], grid["points"][v][1] - goal_pt[1])
            min_heap_push(heap, [f[v], v])
    if not math.isfinite(g[goal_idx]):
        return None
    seq = []
    cur = goal_idx
    while cur >= 0:
        seq.append(cur)
        if cur == start_idx:
            break
        cur = parent[cur]
    seq.reverse()
    return [g[goal_idx], seq]


def simplify_path_with_collision(path, obstacles):
    if not isinstance(path, list) or len(path) <= 2:
        return path[:] if path else []
    out = [path[0]]
    anchor = 0
    while anchor < len(path) - 1:
        best = anchor + 1
        for j in range(len(path) - 1, anchor + 1, -1):
            if segment_clear_boxes(path[anchor], path[j], obstacles):
                best = j
                break
        out.append(path[best])
        anchor = best
    return simplify_colinear_polyline(out)


def walking_plan(slot_xy, building_xy, obstacles, buildings_pos, dest_bi, boxes_input=None, nav_input=None, lot_input=None):
    boxes = boxes_input or walk_blocking_boxes(obstacles, buildings_pos, dest_bi)
    s = [float(slot_xy[0]), float(slot_xy[1])]
    t = [float(building_xy[0]), float(building_xy[1])]
    if segment_clear_boxes(s, t, boxes):
        return [math.hypot(s[0] - t[0], s[1] - t[1]), [s, t]]
    lot_w = max(1, float((lot_input or {}).get("width", 100)))
    lot_h = max(1, float((lot_input or {}).get("height", 100)))
    x_min = float((lot_input or {}).get("x_min", 0) or 0)
    y_min = float((lot_input or {}).get("y_min", 0) or 0)
    grid = nav_input or build_navigation_grid(
        boxes, lot_w, lot_h, recommend_nav_step(lot_w, lot_h, len(boxes)), x_min, y_min
    )
    s_nodes = nearest_visible_grid_nodes(s, grid, boxes, 6, 7)
    t_nodes = nearest_visible_grid_nodes(t, grid, boxes, 6, 7)
    if not s_nodes or not t_nodes:
        return [UNREACHABLE_WALK_DIST, [s]]
    best_dist = float("inf")
    best_path = None
    for si, ds in s_nodes:
        for ti, dt in t_nodes:
            ast = a_star_between_nodes(si, ti, grid)
            if not ast:
                continue
            dgrid, idx_seq = ast
            pts = [s] + [grid["points"][idx] for idx in idx_seq] + [t]
            simp = simplify_path_with_collision(pts, boxes)
            if not polyline_segments_clear(simp, boxes):
                continue
            d = ds + dgrid + dt
            if d < best_dist:
                best_dist = d
                best_path = simp
    if not best_path:
        return [UNREACHABLE_WALK_DIST, [s]]
    return [polyline_length(best_path), best_path]
