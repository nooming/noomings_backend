# -*- coding: utf-8 -*-
"""随机到达过程下的滚动 vs 全信息 Monte Carlo。"""
import copy

from parking.core.optimizer.run_optimize import run_optimize
from parking.core.simulator.engine import run_simulation
from parking.core.simulator.rolling import run_rolling_simulation


def _static_reference_cost(static_result):
    if not static_result:
        return None
    comp = static_result.get("composite_cost")
    if comp is not None:
        return float(comp)
    return float(static_result.get("gbest_value") or static_result.get("gbestValue") or 0)


def run_monte_carlo_rolling(scenario, schedule=None, runs=20, base_seed=42, include_static=True, progress_cb=None):
    runs = max(1, min(50, int(runs or 20)))
    base_seed = int(base_seed) if base_seed is not None else 42
    sched_base = dict(schedule or {})
    samples = []
    roll_costs = []
    static_costs = []
    deltas = []
    static_result_once = None

    for r in range(runs):
        if progress_cb:
            pct = r / runs if runs else 0
            progress_cb("monte_carlo", f"Monte Carlo {r + 1}/{runs}", max(0.02, pct))
        sched = copy.deepcopy(sched_base)
        sched["seed"] = base_seed + r
        if schedule and schedule.get("objective_weights"):
            sched["objective_weights"] = copy.deepcopy(schedule["objective_weights"])
        out = run_rolling_simulation(scenario, schedule=sched)
        if not out.get("success"):
            continue
        rc = float(out.get("rolling_total_cost") or 0)
        roll_costs.append(rc)
        arrivals = (out.get("schedule_realized") or {}).get("arrivals_sec")
        samples.append({"run": r, "arrivals_sec": arrivals, "rolling_total_cost": rc})
        sc = out.get("static_reference_value")
        if include_static and sc is None:
            try:
                static_result_once = static_result_once or run_optimize(scenario, method="exact")
                sc = _static_reference_cost(static_result_once)
            except Exception:
                sc = None
        if sc is not None:
            static_costs.append(float(sc))
            deltas.append(rc - float(sc))

    def _p95(vals):
        if not vals:
            return None
        s = sorted(vals)
        return s[int(0.95 * (len(s) - 1))]

    def _mean(vals):
        return sum(vals) / len(vals) if vals else None

    if progress_cb:
        progress_cb("monte_carlo", "Monte Carlo 完成", 1.0)

    return {
        "success": bool(roll_costs),
        "runs_requested": runs,
        "runs_completed": len(roll_costs),
        "base_seed": base_seed,
        "rolling_cost_mean": _mean(roll_costs),
        "rolling_cost_p95": _p95(roll_costs),
        "static_cost": _mean(static_costs) if static_costs else None,
        "delta_mean": _mean(deltas),
        "delta_p95": _p95(deltas),
        "samples": samples[:10],
    }
