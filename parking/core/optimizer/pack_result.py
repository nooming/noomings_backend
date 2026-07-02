# -*- coding: utf-8 -*-

from .geometry import road_polyline_between_points
from .pathfinding import walking_plan
from .road_model import build_road_segments_from_road


def pack_result(s, opts):
    paths = []
    drive_paths = []
    entrances = s.get("entrances") if isinstance(s.get("entrances"), list) else []
    road_source = {"road": opts.get("road") or s.get("road") or {}}
    for i in range(len(opts["bestAssign"])):
        ti = opts["vehTargets"][i]
        slot_xy = opts["slotsPos"][opts["bestAssign"][i]]
        bxy = opts["buildingsPos"][ti]
        poly = walking_plan(
            slot_xy,
            bxy,
            opts["obstacles"],
            opts["buildingsPos"],
            ti,
            opts["boxesByBi"][ti],
            opts.get("navByBi")[ti] if opts.get("navByBi") else None,
            opts.get("lot"),
        )[1]
        paths.append([[float(p[0]), float(p[1])] for p in poly])
        ei = opts["bestEntrances"][i]
        ent = entrances[ei] if ei < len(entrances) else None
        if ent:
            drive_poly = road_polyline_between_points(ent, slot_xy, road_source)
            drive_paths.append([[float(p[0]), float(p[1])] for p in drive_poly])
        else:
            drive_paths.append([])
    return {
        "scenario": s,
        "gbest_value": float(opts["gbestValue"]),
        "history_best": [float(v) for v in opts["historyBest"]],
        "assign": [int(v) for v in opts["bestAssign"]],
        "veh_targets": [int(v) for v in opts["vehTargets"]],
        "veh_entrances": [int(v) for v in opts["bestEntrances"]],
        "vehicle_breakdown": [
            {
                "vehicle_index": int(it["vehicle_index"]),
                "slot_index": int(it["slot_index"]),
                "destination_index": int(it["destination_index"]),
                "entrance_index": int(it["entrance_index"]),
                "drive_time": float(it["drive_time"]),
                "walk_time": float(it["walk_time"]),
                "penalty": float(it["penalty"]),
                "total_time": float(it["total_time"]),
            }
            for it in opts["vehicleBreakdown"]
        ],
        "paths": paths,
        "drive_paths": drive_paths,
        "road_segments": [
            [[float(seg[0][0]), float(seg[0][1])], [float(seg[1][0]), float(seg[1][1])]]
            for seg in build_road_segments_from_road(opts.get("road") or {})
        ],
        "optimizer": opts["optimizer"],
    }
