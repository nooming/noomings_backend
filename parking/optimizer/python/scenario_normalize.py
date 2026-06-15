# -*- coding: utf-8 -*-
import math

from .geometry import polygon_self_intersects
from .road_model import clone_json, normalize_road, inner_from_road, DEFAULT_ROAD_WIDTH
from .road_snap import snap_point_to_inner_perimeter, snap_slot_to_road, normalize_angle

N_PARTICLES_DEFAULT = 40
N_ITER_DEFAULT = 600
W_DEFAULT = 0.7
C1_DEFAULT = 1.5
C2_DEFAULT = 1.5
V_MAX_DEFAULT = 0.25


def default_scenario():
    lot_w = 140.0
    lot_h = 100.0
    n_veh = 12
    lane_rows = max(1, math.ceil(n_veh / 2))
    slots = []
    for i in range(n_veh):
        row = i // 2
        t = 0.5 if lane_rows <= 1 else row / (lane_rows - 1)
        slots.append([23.25 + (i % 2) * 93.5, 24 + t * 52, 0])
    buildings = [
        [28.0, 90.0],
        [56.0, 90.0],
        [84.0, 90.0],
        [112.0, 90.0],
        [28.0, 10.0],
        [56.0, 10.0],
        [84.0, 10.0],
        [112.0, 10.0],
    ]
    inner = {"x_min": 28.0, "x_max": 112.0, "y_min": 18.0, "y_max": 82.0}
    return {
        "lot": {"width": lot_w, "height": lot_h},
        "entrance": [28.0, 18.0],
        "entrances": [[28.0, 18.0], [112.0, 82.0]],
        "inner": inner,
        "road": {
            "centerline": [
                [inner["x_min"], inner["y_min"]],
                [inner["x_max"], inner["y_min"]],
                [inner["x_max"], inner["y_max"]],
                [inner["x_min"], inner["y_max"]],
                [inner["x_min"], inner["y_min"]],
            ],
            "width": DEFAULT_ROAD_WIDTH,
            "closed": True,
        },
        "obstacle": {"x_min": 64.0, "x_max": 76.0, "y_min": 30.0, "y_max": 70.0},
        "obstacles": [
            {
                "points": [
                    [64.0, 30.0],
                    [76.0, 30.0],
                    [76.0, 70.0],
                    [64.0, 70.0],
                ],
            },
        ],
        "buildings": buildings,
        "slots": slots,
        "n_veh": n_veh,
        "vehicle_destinations": [i % len(buildings) for i in range(n_veh)],
        "vehicle_entrances": [0 if i < n_veh / 2 else 1 for i in range(n_veh)],
        "entrance_mode": "auto",
        "pso": {
            "n_particles": N_PARTICLES_DEFAULT,
            "n_iter": N_ITER_DEFAULT,
            "w": W_DEFAULT,
            "c1": C1_DEFAULT,
            "c2": C2_DEFAULT,
            "v_max": V_MAX_DEFAULT,
        },
        "constraints": {"snap_slots_to_inner_road": True, "snap_entrance_to_inner": True},
        "slot_types": ["normal"] * len(slots),
        "vehicle_requirements": ["normal"] * n_veh,
        "soft_constraints": {"type_mismatch_penalty": 0},
        "display": {
            "length_unit": "m",
            "time_unit": "s",
            "meters_per_unit": 2,
            "scale_bar_m": 20.0,
            "coord_note": "平面坐标 1 单位 = 2 m",
        },
    }


def normalize_slot_entry(raw_slot):
    x = float(raw_slot[0]) if raw_slot and len(raw_slot) > 0 else float("nan")
    y = float(raw_slot[1]) if raw_slot and len(raw_slot) > 1 else float("nan")
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    theta = raw_slot[2] if raw_slot and len(raw_slot) > 2 else 0
    return [x, y, normalize_angle(theta)]


def normalize_vehicle_destinations(s):
    n_b = len(s.get("buildings") or [])
    n_veh = max(0, int(s.get("n_veh", 0) or 0))
    if n_b <= 0 or n_veh <= 0:
        s["vehicle_destinations"] = []
        return
    raw = s.get("vehicle_destinations") if isinstance(s.get("vehicle_destinations"), list) else []
    out = []
    for i in range(n_veh):
        v = int(raw[i] if i < len(raw) else i % n_b)
        bi = v if math.isfinite(float(v)) else i % n_b
        out.append(max(0, min(n_b - 1, bi)))
    s["vehicle_destinations"] = out


def normalize_vehicle_entrances(s):
    n_veh = max(0, int(s.get("n_veh", 0) or 0))
    entrances = s.get("entrances")
    n_e = len(entrances) if isinstance(entrances, list) and entrances else 1
    raw = s.get("vehicle_entrances") if isinstance(s.get("vehicle_entrances"), list) else []
    out = []
    for i in range(n_veh):
        v = int(raw[i] if i < len(raw) else 0)
        out.append(max(0, min(n_e - 1, v)) if math.isfinite(float(v)) else 0)
    s["vehicle_entrances"] = out
    s["entrance_mode"] = "fixed" if str(s.get("entrance_mode") or "auto").lower() == "fixed" else "auto"


def normalize_slot_and_vehicle_types(s):
    n_slot = len(s.get("slots") or [])
    n_veh = max(0, int(s.get("n_veh", 0) or 0))
    slot_types_raw = s.get("slot_types") if isinstance(s.get("slot_types"), list) else []
    req_raw = s.get("vehicle_requirements") if isinstance(s.get("vehicle_requirements"), list) else []
    s["slot_types"] = [
        (str(slot_types_raw[i] if i < len(slot_types_raw) else "normal").strip().lower() or "normal")
        for i in range(n_slot)
    ]
    s["vehicle_requirements"] = [
        (str(req_raw[i] if i < len(req_raw) else "normal").strip().lower() or "normal")
        for i in range(n_veh)
    ]
    soft = s.get("soft_constraints") or {}
    s["soft_constraints"] = {
        "type_mismatch_penalty": max(0, float(soft.get("type_mismatch_penalty") or 0)),
    }


def normalize_scenario(raw):
    s = clone_json(raw or {})
    def_scenario = default_scenario()
    lot = s.get("lot") or {}
    x_min = float(lot.get("x_min", 0) or 0)
    y_min = float(lot.get("y_min", 0) or 0)
    lw = float(lot.get("width", 100))
    lh = float(lot.get("height", 100))
    s["lot"] = {
        "x_min": x_min if math.isfinite(x_min) else 0.0,
        "y_min": y_min if math.isfinite(y_min) else 0.0,
        "width": lw,
        "height": lh,
    }
    if isinstance(s.get("entrance"), list):
        s["entrance"] = [float(s["entrance"][0] or 0), float(s["entrance"][1] or 0)]
    else:
        s["entrance"] = clone_json(def_scenario["entrance"])
    s["inner"] = s.get("inner") or clone_json(def_scenario["inner"])
    s["road"] = normalize_road(s.get("road"), s["inner"], lambda: def_scenario["road"])
    s["inner"] = inner_from_road(s["road"]) or clone_json(def_scenario["inner"])
    s["obstacle"] = s.get("obstacle") or None
    raw_entrances = s.get("entrances") if isinstance(s.get("entrances"), list) and s["entrances"] else [s["entrance"]]
    s["entrances"] = [[float(p[0] or 0), float(p[1] or 0)] for p in raw_entrances]

    def normalize_obstacle(o):
        if not o or not isinstance(o, dict):
            return None
        pts = []
        if isinstance(o.get("points"), list) and o["points"]:
            pts = [[float(p[0]), float(p[1])] for p in o["points"]]
        elif all(
            math.isfinite(float(o.get(k, float("nan"))))
            for k in ("x_min", "x_max", "y_min", "y_max")
        ):
            x0 = min(float(o["x_min"]), float(o["x_max"]))
            x1 = max(float(o["x_min"]), float(o["x_max"]))
            y0 = min(float(o["y_min"]), float(o["y_max"]))
            y1 = max(float(o["y_min"]), float(o["y_max"]))
            pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        out = []
        for pt in pts:
            x = float(pt[0]) if pt and len(pt) > 0 else float("nan")
            y = float(pt[1]) if pt and len(pt) > 1 else float("nan")
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            if not out or math.hypot(out[-1][0] - x, out[-1][1] - y) > 1e-6:
                out.append([x, y])
        if len(out) >= 2:
            f0 = out[0]
            fn = out[-1]
            if math.hypot(f0[0] - fn[0], f0[1] - fn[1]) < 1e-6:
                out.pop()
        if len(out) < 3:
            return None
        if polygon_self_intersects(out):
            return None
        area = 0.0
        for i in range(len(out)):
            a = out[i]
            b = out[(i + 1) % len(out)]
            area += a[0] * b[1] - b[0] * a[1]
        if abs(area) < 0.1:
            return None
        return {"points": out}

    raw_obstacles = s.get("obstacles") if isinstance(s.get("obstacles"), list) and s["obstacles"] else [s.get("obstacle")]
    s["obstacles"] = [o for o in (normalize_obstacle(o) for o in raw_obstacles) if o]
    s["buildings"] = [[float(p[0]), float(p[1])] for p in (s.get("buildings") or [])]
    s["slots"] = [p for p in (normalize_slot_entry(p) for p in (s.get("slots") or [])) if p]
    s["constraints"] = {
        "snap_slots_to_inner_road": True,
        "snap_entrance_to_inner": True,
    }
    if s["constraints"]["snap_entrance_to_inner"]:
        s["entrances"] = [
            snap_point_to_inner_perimeter(float(p[0]), float(p[1]), s["road"], s["lot"])
            for p in s["entrances"]
        ]
    s["entrance"] = s["entrances"][0] if s["entrances"] else clone_json(def_scenario["entrance"])
    p0 = (s["obstacles"][0].get("points") or []) if s["obstacles"] else []
    xmin = float("inf")
    xmax = float("-inf")
    ymin = float("inf")
    ymax = float("-inf")
    for pt in p0:
        xmin = min(xmin, float(pt[0]))
        xmax = max(xmax, float(pt[0]))
        ymin = min(ymin, float(pt[1]))
        ymax = max(ymax, float(pt[1]))
    s["obstacle"] = (
        {"x_min": xmin, "x_max": xmax, "y_min": ymin, "y_max": ymax}
        if all(math.isfinite(v) for v in [xmin, xmax, ymin, ymax])
        else None
    )
    if s["constraints"]["snap_slots_to_inner_road"] and s["slots"]:
        s["slots"] = [
            [
                snapped[0],
                snapped[1],
                normalize_angle(snapped[2] if len(snapped) > 2 else (p[2] if len(p) > 2 else 0)),
            ]
            for p, snapped in zip(
                s["slots"],
                [snap_slot_to_road(float(p[0]), float(p[1]), s["road"], s["lot"]) for p in s["slots"]],
            )
        ]
    n_veh_raw = int(s.get("n_veh", 0) or 0) or 12
    if not s["slots"]:
        s["n_veh"] = 0
    else:
        s["n_veh"] = max(1, min(n_veh_raw, len(s["slots"])))
    pso = s.get("pso") or {}
    s["pso"] = {
        "n_particles": int(pso.get("n_particles", 0) or 0) or N_PARTICLES_DEFAULT,
        "n_iter": int(pso.get("n_iter", 0) or 0) or N_ITER_DEFAULT,
        "w": float(pso.get("w", W_DEFAULT) if pso.get("w") is not None else W_DEFAULT),
        "c1": float(pso.get("c1", C1_DEFAULT) if pso.get("c1") is not None else C1_DEFAULT),
        "c2": float(pso.get("c2", C2_DEFAULT) if pso.get("c2") is not None else C2_DEFAULT),
        "v_max": float(pso.get("v_max", V_MAX_DEFAULT) if pso.get("v_max") is not None else V_MAX_DEFAULT),
    }
    disp = s.get("display") or {}
    meters_per_unit = float(disp.get("meters_per_unit", 2))
    raw_underlay = disp.get("underlay") if isinstance(disp.get("underlay"), dict) else {}

    def norm_pt(arr):
        if isinstance(arr, list) and len(arr) >= 2:
            return [float(arr[0]) if math.isfinite(float(arr[0])) else 0, float(arr[1]) if math.isfinite(float(arr[1])) else 0]
        return None

    opacity = float(raw_underlay.get("opacity", float("nan")))
    image_size = None
    if isinstance(raw_underlay.get("imageSize"), list) and len(raw_underlay["imageSize"]) >= 2:
        image_size = [
            max(1, float(raw_underlay["imageSize"][0]) or 1),
            max(1, float(raw_underlay["imageSize"][1]) or 1),
        ]
    s["display"] = {
        "length_unit": str(disp.get("length_unit") or "m"),
        "time_unit": str(disp.get("time_unit") or "s"),
        "meters_per_unit": meters_per_unit if math.isfinite(meters_per_unit) and meters_per_unit > 0 else 2,
        "scale_bar_m": float(disp.get("scale_bar_m", 20)),
        "coord_note": str(disp.get("coord_note") or "平面坐标 1 单位 = 2 m"),
        "underlay": {
            "dataUrl": raw_underlay.get("dataUrl") if isinstance(raw_underlay.get("dataUrl"), str) else "",
            "opacity": max(0.05, min(1, opacity)) if math.isfinite(opacity) else 0.55,
            "imageSize": image_size,
            "worldA": norm_pt(raw_underlay.get("worldA")),
            "worldB": norm_pt(raw_underlay.get("worldB")),
            "imageA": norm_pt(raw_underlay.get("imageA")),
            "imageB": norm_pt(raw_underlay.get("imageB")),
        },
    }
    normalize_vehicle_destinations(s)
    normalize_vehicle_entrances(s)
    normalize_slot_and_vehicle_types(s)
    return s
