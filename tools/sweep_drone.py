
#!/usr/bin/env python3
"""
tools/sweep_drone.py

Grid-sweep the drone landing demo over wind parameters and aggregate AF outcomes.

Outputs in runs/:
- drone_sweep_results.csv
- drone_sweep_policy.png           (final chosen policy index per grid cell)
- drone_sweep_success.png          (success=1/0 per grid cell)
- drone_sweep_touchdown_time.png   (touchdown time in seconds; failed runs shown as max_time+1)

Rules:
- matplotlib only
- one chart per figure
- no custom colors/styles
"""

from __future__ import annotations
import argparse, csv, math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

import sys
REPO_ROOT = Path(__file__).resolve().parents[1]  # one level up from tools/
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import core parts from your project
from core.arguments import ArgFramework, Argument, ActionSpec, VerifySpec
from core.af_solver import grounded_extension, filter_attacks_by_priority
from core.planner import order_plan
from domains.drone.model import DroneSim, DroneState, Wind, policy_aggressive, policy_conservative
from domains.drone.rules import generate_landing_AF
from demos.scenario2_landing import verify_after_sim

RUNS = Path("runs")
RUNS.mkdir(parents=True, exist_ok=True)

def simulate(policy_name: str, wind: Wind, seed: int|None=None, dt=0.05, max_time=20.0):
    sim = DroneSim(dt=dt, max_time=max_time, wind=wind)
    if seed is not None:
        import random; random.seed(seed)
    sim.reset(DroneState())
    if policy_name == "aggressive":
        res = sim.run_policy(policy_aggressive)
    else:
        res = sim.run_policy(policy_conservative)
    return res

def choose_policy_via_AF(zone_r: float, max_speed: float, max_time: float):
    af0 = generate_landing_AF(zone_radius=zone_r, max_speed=max_speed, max_time=max_time)
    args = af0.args.copy()
    attacks_eff = filter_attacks_by_priority(args, af0.attacks)
    af = ArgFramework(args=args, attacks=attacks_eff)
    ext = grounded_extension(af)
    steps = order_plan(af.args, ext)
    policy = None
    for s in steps:
        a = af.args[s.arg_id]
        if isinstance(a.action, ActionSpec) and a.action.name == "set_policy":
            policy = a.action.params.get("name")
            break
    return policy, af

def sweep(vx_min, vx_max, vx_n, gust_min, gust_max, gust_n, *, gust_period=5.0, zone_r=1.5, max_speed=0.6, max_time=20.0, seed=42):
    # Setup grids
    vx_vals = np.linspace(vx_min, vx_max, vx_n)
    ga_vals = np.linspace(gust_min, gust_max, gust_n)

    # Storage for plots
    # policy_map: 0 = aggressive, 1 = conservative, -1 = unknown/error
    policy_map = np.full((gust_n, vx_n), -1, dtype=float)
    success_map = np.zeros((gust_n, vx_n), dtype=float)
    ttd_map = np.full((gust_n, vx_n), max_time+1.0, dtype=float)

    rows = []
    csv_path = RUNS/"drone_sweep_results.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        if write_header:
            w.writerow([
                "vx","gust_amp","gust_period",
                "policy_initial","policy_final","success",
                "t_touchdown","vmag","in_zone","speed_ok","time_ok"
            ])

        for j, ga in enumerate(ga_vals):
            for i, vx in enumerate(vx_vals):
                # Choose via AF (priority favors conservative)
                policy, af = choose_policy_via_AF(zone_r, max_speed, max_time)
                if policy is None:  # fallback safe default
                    policy = "conservative"

                # Run once
                res = simulate(policy, Wind(vx=vx, gust_amp=ga, gust_period=gust_period), seed=seed, max_time=max_time)
                ok, detail = verify_after_sim(res, zone_r, max_speed, max_time)
                final_policy = policy

                if not ok:
                    # Simple diagnosis step: switch policy and retry
                    final_policy = "conservative" if policy == "aggressive" else "aggressive"
                    res = simulate(final_policy, Wind(vx=vx, gust_amp=ga, gust_period=gust_period), seed=seed, max_time=max_time)
                    ok, detail = verify_after_sim(res, zone_r, max_speed, max_time)

                # Write CSV row
                w.writerow([
                    f"{vx:.4f}", f"{ga:.4f}", f"{gust_period:.4f}",
                    policy, final_policy, 1 if ok else 0,
                    f"{detail.get('t_touchdown', float('nan')):.4f}",
                    f"{detail.get('vmag', float('nan')):.4f}",
                    detail.get("in_zone", False),
                    detail.get("speed_ok", False),
                    detail.get("time_ok", False),
                ])

                # Update maps
                policy_map[j, i] = 1.0 if final_policy == "conservative" else 0.0
                success_map[j, i] = 1.0 if ok else 0.0
                ttd_map[j, i] = float(detail.get("t_touchdown", max_time+1.0))

    return (vx_vals, ga_vals, policy_map, success_map, ttd_map)

def plot_matrix(x_vals, y_vals, M, title, out_path):
    import matplotlib.pyplot as plt
    plt.figure()
    # imshow expects row=Y, col=X; we pass M indexed [j,i] with y_vals (rows) and x_vals (cols)
    extent = [x_vals[0], x_vals[-1], y_vals[0], y_vals[-1]]
    plt.imshow(M, origin="lower", aspect="auto", extent=extent)
    plt.xlabel("wind vx (m/s)")
    plt.ylabel("gust amplitude (m/s)")
    plt.title(title)
    plt.colorbar()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print("Wrote:", out_path)

def main():
    ap = argparse.ArgumentParser(description="Sweep wind parameters and aggregate drone landing outcomes.")
    ap.add_argument("--vx-min", type=float, default=0.0)
    ap.add_argument("--vx-max", type=float, default=1.4)
    ap.add_argument("--vx-n",   type=int,   default=8)
    ap.add_argument("--gust-min", type=float, default=0.0)
    ap.add_argument("--gust-max", type=float, default=0.6)
    ap.add_argument("--gust-n",   type=int,   default=7)
    ap.add_argument("--gust-period", type=float, default=5.0)
    ap.add_argument("--zone-r", type=float, default=1.5)
    ap.add_argument("--max-speed", type=float, default=0.6)
    ap.add_argument("--max-time", type=float, default=20.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    vx_vals, ga_vals, policy_map, success_map, ttd_map = sweep(
        args.vx_min, args.vx_max, args.vx_n,
        args.gust_min, args.gust_max, args.gust_n,
        gust_period=args.gust_period,
        zone_r=args.zone_r, max_speed=args.max_speed, max_time=args.max_time,
        seed=args.seed
    )

    # Plots (one chart per figure)
    plot_matrix(vx_vals, ga_vals, policy_map, "Final policy (1=conservative, 0=aggressive)", RUNS/"drone_sweep_policy.png")
    plot_matrix(vx_vals, ga_vals, success_map, "Success map (1=pass, 0=fail)", RUNS/"drone_sweep_success.png")
    plot_matrix(vx_vals, ga_vals, ttd_map,    "Touchdown time (s)", RUNS/"drone_sweep_touchdown_time.png")

if __name__ == "__main__":
    main()
