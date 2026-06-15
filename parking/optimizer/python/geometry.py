# -*- coding: utf-8 -*-
import math


def closest_point_on_segment(px, py, x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return [x1, y1]
    t = ((px - x1) * dx + (py - y1) * dy) / l2
    t = max(0, min(1, t))
    return [x1 + t * dx, y1 + t * dy]


def normalize_polyline(points):
    if not isinstance(points, list):
        return []
    out = []
    for p in points:
        x = float(p[0]) if p and len(p) > 0 else float("nan")
        y = float(p[1]) if p and len(p) > 1 else float("nan")
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        if not out or math.hypot(out[-1][0] - x, out[-1][1] - y) > 1e-6:
            out.append([x, y])
    return out


def point_on_segment(p, a, b, eps=1e-6):
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > eps:
        return False
    dot = (p[0] - a[0]) * (p[0] - b[0]) + (p[1] - a[1]) * (p[1] - b[1])
    return dot <= eps


def segments_intersect(a, b, c, d, eps=1e-6):
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = cross(a, b, c)
    o2 = cross(a, b, d)
    o3 = cross(c, d, a)
    o4 = cross(c, d, b)
    if (o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps):
        if (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps):
            return True
    if abs(o1) <= eps and point_on_segment(c, a, b, eps):
        return True
    if abs(o2) <= eps and point_on_segment(d, a, b, eps):
        return True
    if abs(o3) <= eps and point_on_segment(a, c, d, eps):
        return True
    if abs(o4) <= eps and point_on_segment(b, c, d, eps):
        return True
    return False


def polygon_self_intersects(poly):
    if not isinstance(poly, list) or len(poly) < 4:
        return False
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        for j in range(i + 1, n):
            if i == j:
                continue
            if (i + 1) % n == j or (j + 1) % n == i:
                continue
            c = poly[j]
            d = poly[(j + 1) % n]
            if segments_intersect(a, b, c, d):
                return True
    return False


def point_in_polygon(p, poly, include_boundary=True):
    with_boundary = include_boundary is not False
    if not isinstance(poly, list) or len(poly) < 3:
        return False
    if with_boundary:
        for i in range(len(poly)):
            a = poly[i]
            b = poly[(i + 1) % len(poly)]
            if point_on_segment(p, a, b):
                return True
    inside = False
    px = float(p[0])
    py = float(p[1])
    j = len(poly) - 1
    for i in range(len(poly)):
        xi = float(poly[i][0])
        yi = float(poly[i][1])
        xj = float(poly[j][0])
        yj = float(poly[j][1])
        cross = (yi > py) != (yj > py) and px < ((xj - xi) * (py - yi)) / ((yj - yi) or 1e-12) + xi
        if cross:
            inside = not inside
        j = i
    return inside


def segment_intersects_polygon(p1, p2, poly):
    if point_in_polygon(p1, poly, True) or point_in_polygon(p2, poly, True):
        return True
    for i in range(len(poly)):
        a = poly[i]
        b = poly[(i + 1) % len(poly)]
        if segments_intersect(p1, p2, a, b):
            return True
    return False


def to_road_segments_from_centerline(centerline):
    pts = normalize_polyline(centerline)
    segs = []
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]
        if math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6:
            continue
        segs.append([a, b])
    return segs


def build_road_segments(source):
    if not source or not isinstance(source, dict):
        return []
    road = source.get("road") if isinstance(source.get("road"), dict) else source
    if isinstance(road.get("centerline"), list):
        by_centerline = to_road_segments_from_centerline(road["centerline"])
        if by_centerline:
            return by_centerline
    inner = source.get("inner") if isinstance(source.get("inner"), dict) else source
    ix0 = float(inner.get("x_min", float("nan")))
    ix1 = float(inner.get("x_max", float("nan")))
    iy0 = float(inner.get("y_min", float("nan")))
    iy1 = float(inner.get("y_max", float("nan")))
    if not all(math.isfinite(v) for v in [ix0, ix1, iy0, iy1]):
        return []
    return [
        [[ix0, iy0], [ix1, iy0]],
        [[ix1, iy0], [ix1, iy1]],
        [[ix1, iy1], [ix0, iy1]],
        [[ix0, iy1], [ix0, iy0]],
    ]


def polyline_length(points):
    pts = normalize_polyline(points)
    total = 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return total


def nearest_point_on_polyline(px, py, polyline):
    pts = normalize_polyline(polyline)
    if len(pts) < 2:
        return None
    best = None
    best_d2 = float("inf")
    prefix = 0.0
    best_along = 0.0
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]
        q = closest_point_on_segment(px, py, a[0], a[1], b[0], b[1])
        d2 = (px - q[0]) ** 2 + (py - q[1]) ** 2
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        proj_len = math.hypot(q[0] - a[0], q[1] - a[1])
        if d2 < best_d2:
            best_d2 = d2
            best_along = prefix + proj_len
            best = {
                "point": [q[0], q[1]],
                "segmentIndex": i,
                "distance": math.sqrt(d2),
                "distanceSquared": d2,
                "along": best_along,
                "totalLength": polyline_length(pts),
                "segmentLength": seg_len,
            }
        prefix += seg_len
    return best


def project_point_to_road(px, py, source):
    if not source or not isinstance(source, dict):
        return None
    road = source.get("road") if isinstance(source.get("road"), dict) else source
    if isinstance(road.get("centerline"), list) and len(road["centerline"]) >= 2:
        return nearest_point_on_polyline(px, py, road["centerline"])
    segs = build_road_segments(source)
    best = None
    best_d2 = float("inf")
    prefix = 0.0
    total_length = 0.0
    for a, b in segs:
        total_length += math.hypot(b[0] - a[0], b[1] - a[1])
    for i, (a, b) in enumerate(segs):
        q = closest_point_on_segment(px, py, a[0], a[1], b[0], b[1])
        d2 = (px - q[0]) ** 2 + (py - q[1]) ** 2
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        proj_len = math.hypot(q[0] - a[0], q[1] - a[1])
        if d2 < best_d2:
            best_d2 = d2
            best = {
                "point": [q[0], q[1]],
                "segmentIndex": i,
                "distance": math.sqrt(d2),
                "distanceSquared": d2,
                "along": prefix + proj_len,
                "totalLength": total_length,
                "segmentLength": seg_len,
            }
        prefix += seg_len
    return best


def road_distance_between_points(a, b, source):
    pa = project_point_to_road(float(a[0]), float(a[1]), source)
    pb = project_point_to_road(float(b[0]), float(b[1]), source)
    if not pa or not pb:
        return 0.0
    L = max(1e-9, float(pa.get("totalLength") or pb.get("totalLength") or 0))
    d = abs(pa["along"] - pb["along"])
    road = source.get("road") if isinstance(source.get("road"), dict) else source
    closed = road.get("closed") is not False
    if closed:
        d = min(d, L - d)
    return d


def centerline_along_meta(centerline):
    pts = normalize_polyline(centerline)
    if len(pts) < 2:
        return {"pts": pts, "cumAlong": [0.0], "total": 0.0}
    cum_along = [0.0]
    for i in range(len(pts) - 1):
        cum_along.append(
            cum_along[-1] + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        )
    return {"pts": pts, "cumAlong": cum_along, "total": cum_along[-1]}


def point_at_along(pts, cum_along, along, closed):
    L = cum_along[-1]
    if L < 1e-9:
        return [pts[0][0], pts[0][1]] if pts else [0.0, 0.0]
    t = along
    if closed:
        t = ((t % L) + L) % L
    else:
        t = max(0, min(L, t))
    for i in range(len(cum_along) - 1):
        if t <= cum_along[i + 1] + 1e-9:
            a = pts[i]
            b = pts[i + 1]
            seg_len = cum_along[i + 1] - cum_along[i]
            u = 0.0 if seg_len < 1e-9 else (t - cum_along[i]) / seg_len
            return [a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1])]
    last = pts[-1]
    return [last[0], last[1]]


def append_unique_point(out, p):
    x = float(p[0]) if p and len(p) > 0 else float("nan")
    y = float(p[1]) if p and len(p) > 1 else float("nan")
    if not math.isfinite(x) or not math.isfinite(y):
        return
    if out:
        last = out[-1]
        if math.hypot(last[0] - x, last[1] - y) < 1e-6:
            return
    out.append([x, y])


def sample_centerline_arc(pts, cum_along, along_start, along_end, closed):
    L = cum_along[-1]
    if L < 1e-9:
        return []
    a0 = along_start
    a1 = along_end
    forward = (a1 - a0) if a1 >= a0 else (L - a0 + a1 if closed else a0 - a1)
    backward = (L - forward) if closed else float("inf")
    use_forward = forward <= backward if closed else True
    dist = min(forward, backward) if closed else forward
    if dist < 1e-6:
        return [point_at_along(pts, cum_along, a0, closed)]
    step = max(0.35, L / 90)
    n_steps = max(1, math.ceil(dist / step))
    out = []
    for i in range(n_steps + 1):
        frac = i / n_steps
        if use_forward:
            along = a0 + dist * frac
            if closed:
                along = ((along % L) + L) % L
        else:
            along = a0 - dist * frac
            if closed:
                along = ((along % L) + L) % L
        append_unique_point(out, point_at_along(pts, cum_along, along, closed))
    return out


def road_polyline_between_points(a, b, source):
    entrance = [float(a[0]), float(a[1])]
    slot = [float(b[0]), float(b[1])]
    if not math.isfinite(entrance[0]) or not math.isfinite(entrance[1]):
        return normalize_polyline([slot])
    if not math.isfinite(slot[0]) or not math.isfinite(slot[1]):
        return normalize_polyline([entrance])

    road = source.get("road") if isinstance(source.get("road"), dict) else source
    if not road or not isinstance(road, dict):
        return normalize_polyline([entrance, slot])

    centerline = road.get("centerline") if isinstance(road.get("centerline"), list) else None
    closed = road.get("closed") is not False
    if not centerline or len(centerline) < 2:
        segs = build_road_segments(source)
        if not segs:
            return normalize_polyline([entrance, slot])
        centerline = [segs[0][0]]
        for seg in segs:
            centerline.append(seg[1])

    pa = project_point_to_road(entrance[0], entrance[1], source)
    pb = project_point_to_road(slot[0], slot[1], source)
    if not pa or not pb:
        return normalize_polyline([entrance, slot])

    meta = centerline_along_meta(centerline)
    arc_pts = sample_centerline_arc(meta["pts"], meta["cumAlong"], pa["along"], pb["along"], closed)
    out = []
    append_unique_point(out, entrance)
    append_unique_point(out, pa["point"])
    for p in arc_pts:
        append_unique_point(out, p)
    append_unique_point(out, pb["point"])
    append_unique_point(out, slot)
    return out
