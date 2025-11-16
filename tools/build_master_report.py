#!/usr/bin/env python3
from __future__ import annotations
"""
tools/build_master_report.py

One-click builder for Scenario 2 (Drone Landing) report.
Steps:
1) Run scenario: python -m demos.scenario2_landing
2) Plot trajectory metrics: python tools/plot_drone_metrics.py
3) Optional sweep: python tools/sweep_drone.py [grid]
4) Aggregate sweep: python tools/sweep_aggregate.py
5) Build AF summary HTML: python tools/af_summarize.py --run runs/isl_nano_run_drone_landing.jsonl
"""

# --- UTF-8 Console Safety for Windows ---
import sys, io, os
if os.name == "nt":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
# ----------------------------------------

import argparse, subprocess
from pathlib import Path

# --- repo-root import shim ---
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# ------------------------------

RUNS = REPO_ROOT / "runs"

def run_cmd(cmd, cwd=None):
    print(">>", " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
    return proc.returncode == 0

def main():
    ap = argparse.ArgumentParser(description="Build Scenario 2 master report.")
    ap.add_argument("--no-sweep", action="store_true", help="Skip the parameter sweep step.")
    # Sweep customizations
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

    py = sys.executable

    # 1) Scenario run
    if not run_cmd([py, "-m", "demos.scenario2_landing"], cwd=str(REPO_ROOT)):
        sys.exit(1)

    # 2) Trajectory plots
    if not run_cmd([py, "tools/plot_drone_metrics.py"], cwd=str(REPO_ROOT)):
        sys.exit(1)

    # 3) Sweep (optional)
    if not args.no_sweep:
        sweep_cmd = [
            py, "tools/sweep_drone.py",
            "--vx-min", str(args.vx_min),
            "--vx-max", str(args.vx_max),
            "--vx-n",   str(args.vx_n),
            "--gust-min", str(args.gust_min),
            "--gust-max", str(args.gust_max),
            "--gust-n",   str(args.gust_n),
            "--gust-period", str(args.gust_period),
            "--zone-r", str(args.zone_r),
            "--max-speed", str(args.max_speed),
            "--max-time", str(args.max_time),
            "--seed", str(args.seed),
        ]
        if not run_cmd(sweep_cmd, cwd=str(REPO_ROOT)):
            sys.exit(1)

        # 4) Aggregate
        if not run_cmd([py, "tools/sweep_aggregate.py"], cwd=str(REPO_ROOT)):
            sys.exit(1)

    # 5) Summary HTML
    run_jsonl = REPO_ROOT / "runs" / "isl_nano_run_drone_landing.jsonl"
    if not run_jsonl.exists():
        print("Missing run JSONL:", run_jsonl)
        sys.exit(1)
    if not run_cmd([py, "tools/af_summarize.py", "--run", str(run_jsonl)], cwd=str(REPO_ROOT)):
        sys.exit(1)

    print("\n✅ All done! Open runs/af_summary.html in your browser.")
    print("Artifacts directory:", RUNS)

if __name__ == "__main__":
    main()
